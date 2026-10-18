package com.machinist.todoro

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Все списки с задачами — копия с компьютера (с правками телефона поверх). */
data class SyncData(
    val lists: List<TaskList>,
    val views: Map<String, ListView>,
    val sharedOffline: Boolean,
    val user: String,
    val syncedAt: Long,
    val pcVersion: String = "",  // версия ToDoro на компьютере («О приложении»)
)

/**
 * Правка, сделанная на телефоне: ждёт отправки на компьютер.
 * kind: "create" (id — временный, отрицательный), "patch" (fields — что поменять;
 * version — какую версию задачи видел телефон, null — не проверять), "delete".
 */
data class Op(
    val kind: String,
    val list: String,
    val id: Long,
    val fields: JSONObject,
    val version: Int?,
    val title: String,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("kind", kind).put("list", list).put("id", id).put("fields", fields)
        .put("version", version ?: JSONObject.NULL).put("title", title)

    companion object {
        fun fromJson(o: JSONObject) = Op(
            o.getString("kind"), o.getString("list"), o.getLong("id"),
            o.optJSONObject("fields") ?: JSONObject(),
            if (o.isNull("version")) null else o.getInt("version"), o.optString("title"),
        )
    }
}

/** Правку не отправили: задачу на компьютере успели изменить. current — как она выглядит там. */
data class ConflictItem(val op: Op, val current: Task, val currentJson: JSONObject)

/**
 * Хранилище приложения — одно на весь процесс (окно, фоновая синхронизация, напоминания).
 *
 * Как устроено: server — последняя копия с компьютера, queue — правки телефона, которые ещё
 * не дошли до компьютера. На экране — server с применёнными поверх правками (data), поэтому
 * без связи всё работает так же, а когда связь появится — очередь отправится по порядку.
 * Всё хранится в файлах приложения и переживает перезапуск телефона.
 */
object Repo {
    private lateinit var app: Context
    private val mutex = Mutex()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    var pairing by mutableStateOf<Pairing?>(null)
        private set
    private var api: Api? = null

    private var server: JSONObject? = null           // ответ /sync (с прежними общими списками, если нет связи)
    private val queue = mutableListOf<Op>()
    private val conflictList = mutableListOf<ConflictItem>()
    private val tempIds = mutableMapOf<Long, Long>()   // временный номер задачи -> настоящий

    // --- то, что видит экран ---
    var data by mutableStateOf<SyncData?>(null)
        private set
    var online by mutableStateOf<Boolean?>(null)      // null — ещё не пробовали
        private set
    var problem by mutableStateOf<String?>(null)
        private set
    var keyRejected by mutableStateOf(false)
        private set
    var pendingTasks by mutableStateOf<Set<Pair<String, Long>>>(emptySet())
        private set
    var pendingCount by mutableStateOf(0)
        private set
    var conflict by mutableStateOf<ConflictItem?>(null)
        private set
    var syncing by mutableStateOf(false)
        private set
    /** Короткое сообщение для экрана (берёт и обнуляет экран). */
    var message by mutableStateOf<String?>(null)

    private val dir get() = File(app.filesDir, "sync").apply { mkdirs() }

    fun init(context: Context) {
        if (::app.isInitialized) return
        app = context.applicationContext
        pairing = Pairing.load(app)
        api = pairing?.let { Api(it) }
        server = readJson("server.json")?.let { JSONObject(it) }
        readJson("queue.json")?.let { text ->
            JSONArray(text).let { a -> (0 until a.length()).forEach { queue += Op.fromJson(a.getJSONObject(it)) } }
        }
        readJson("conflicts.json")?.let { text ->
            val a = JSONArray(text)
            for (i in 0 until a.length()) {
                val o = a.getJSONObject(i)
                val current = o.getJSONObject("current")
                conflictList += ConflictItem(Op.fromJson(o.getJSONObject("op")), parseTask(current), current)
            }
        }
        publish()
        SyncWorker.schedulePeriodic(app)
    }

    // --- подключение ---

    /** Это компьютер, к которому телефон уже подключён (тот же ключ или тот же адрес)? */
    fun samePc(p: Pairing) =
        pairing?.let { it.key == p.key || it.hosts.intersect(p.hosts.toSet()).isNotEmpty() } == true

    fun pair(p: Pairing) {
        p.save(app)
        scope.launch {
            mutex.withLock {
                if (!samePc(p)) clearData()  // другой компьютер — старые задачи и правки не к нему
                pairing = p
                api = Api(p)
                keyRejected = false
                problem = null
            }
            sync()
        }
    }

    fun unpair() {
        Pairing.clear(app)
        scope.launch {
            mutex.withLock {
                pairing = null
                api = null
                clearData()
            }
            Reminders.update(app, null)
        }
    }

    private fun clearData() {
        server = null
        queue.clear()
        conflictList.clear()
        tempIds.clear()
        dir.listFiles()?.forEach { it.delete() }
        online = null
        problem = null
        keyRejected = false
        publish()
    }

    // --- связь с компьютером ---

    /** Отправить очередь правок и забрать свежую копию. Возвращает true, если связь была. */
    suspend fun sync(): Boolean {
        val api = api ?: return false
        syncing = true
        try {
            return mutex.withLock {
                if (!flushLocked(api)) return@withLock false
                try {
                    val fresh = api.get("/sync")
                    server = merge(server, fresh)
                    writeJson("server.json", server.toString())
                    online = true
                    problem = null
                    publish()
                    true
                } catch (e: Exception) {
                    fail(e)
                    false
                }
            }
        } finally {
            syncing = false
            Reminders.update(app, data)
        }
    }

    /** Отправляет очередь по порядку. false — дальше нельзя (нет связи, ключ не принят). */
    private suspend fun flushLocked(api: Api): Boolean {
        while (queue.isNotEmpty()) {
            val op = queue.first()
            try {
                send(api, op)
            } catch (e: ApiException) {
                when (e.status) {
                    409 -> e.body?.optJSONObject("task")?.let { current ->
                        conflictList += ConflictItem(op, parseTask(current), current)
                        Reminders.notifyConflict(app, op.title)
                    }
                    404 -> message = "«${op.title}»: задачи или списка уже нет на компьютере — правка не нужна"
                    401, 503 -> return fail(e)
                    else -> message = "«${op.title}»: ${e.message}"
                }
            } catch (e: Exception) {
                return fail(e)
            }
            queue.removeAt(0)
            saveQueue()
            publish()
        }
        return true
    }

    private suspend fun send(api: Api, op: Op) {
        val path = Api.listPath(op.list) + "/tasks"
        when (op.kind) {
            "create" -> {
                val task = api.post(path, op.fields).getJSONObject("task")
                val realId = task.getLong("id")
                tempIds[op.id] = realId
                // задачу уже правили на телефоне, пока она ехала на компьютер, — исправляем номер
                for (i in 1 until queue.size) {
                    val next = queue[i]
                    if (next.list == op.list && next.id == op.id) queue[i] = next.copy(id = realId)
                }
                // в копии с компьютера её ещё нет — добавим, чтобы она не мигнула до следующей загрузки
                addToServer(op.list, task)
            }
            "patch" -> {
                val json = JSONObject(op.fields.toString())
                op.version?.let { json.put("version", it) }
                val task = api.patch("$path/${op.id}", json).getJSONObject("task")
                replaceInServer(op.list, task)
            }
            "delete" -> {
                api.delete("$path/${op.id}")
                removeFromServer(op.list, op.id)
            }
        }
    }

    private fun fail(e: Exception): Boolean {
        when (e) {
            is OfflineException -> {
                online = false
                problem = e.message
            }
            is ApiException -> if (e.status == 401) keyRejected = true else problem = e.message
            else -> problem = e.message
        }
        return false
    }

    // --- правки с телефона ---

    /** Применить правку сразу на экране и поставить в очередь на отправку. */
    fun enqueue(op: Op) {
        scope.launch {
            add(op)
            if (!sync()) SyncWorker.scheduleFlush(app)
        }
    }

    /** Только записать правку (без отправки) — для кнопки в уведомлении: отправит фоновая работа. */
    suspend fun add(op: Op) {
        mutex.withLock {
            val fixed = tempIds[op.id]?.let { op.copy(id = it) } ?: op
            queue += fixed
            saveQueue()
            publish()
        }
        Reminders.update(app, data)
    }

    fun launch(block: suspend () -> Unit) = scope.launch { block() }

    // --- комментарии: только при связи с компьютером (в копии на телефоне их нет) ---

    private fun taskPath(list: String, id: Long) = Api.listPath(list) + "/tasks/$id"

    private fun online(): Api = api ?: throw OfflineException("Телефон не подключён к компьютеру")

    /** Задача с комментариями (файлы телефону не передаются — только их число). */
    suspend fun details(list: String, id: Long): JSONObject =
        online().get(taskPath(list, id)).getJSONObject("task")

    suspend fun addComment(list: String, id: Long, text: String): JSONObject =
        online().post(taskPath(list, id) + "/comments", JSONObject().put("text", text)).getJSONObject("task")

    suspend fun deleteComment(list: String, id: Long, commentId: Long) {
        online().delete(taskPath(list, id) + "/comments/$commentId")
    }

    fun create(list: String, fields: JSONObject, title: String): Long {
        val id = -System.currentTimeMillis()
        // Метка задачи: если ответ компьютера потеряется и задача уйдёт ещё раз, компьютер
        // узнает её и не создаст вторую такую же (phone.py, add_task)
        fields.put("client_id", java.util.UUID.randomUUID().toString())
        enqueue(Op("create", list, id, fields, null, title))
        return id
    }

    fun patch(list: String, task: Task, fields: JSONObject, checkVersion: Boolean) =
        enqueue(Op("patch", list, task.id, fields,
            if (checkVersion && task.id > 0) task.version else null, task.title))

    fun delete(list: String, task: Task) = enqueue(Op("delete", list, task.id, JSONObject(), null, task.title))

    /** «Сохранить мой вариант» / «Оставить их вариант» после конфликта. */
    fun resolve(item: ConflictItem, mine: Boolean) {
        scope.launch {
            mutex.withLock {
                conflictList.remove(item)
                if (!mine) replaceInServer(item.op.list, item.currentJson)
                saveQueue()
                publish()
            }
            if (mine) enqueue(item.op.copy(version = item.current.version)) else Reminders.update(app, data)
        }
    }

    // --- копия с компьютера ---

    /** Новая копия; если компьютер сейчас не видит общую папку — общие списки берём из прежней. */
    private fun merge(old: JSONObject?, fresh: JSONObject): JSONObject {
        val result = JSONObject(fresh.toString()).put("synced_at", System.currentTimeMillis())
        if (old == null || !fresh.optBoolean("shared_offline")) return result
        val lists = result.getJSONArray("lists")
        val views = result.getJSONObject("views")
        val have = (0 until lists.length()).map { lists.getJSONObject(it).getString("id") }.toSet()
        val oldLists = old.getJSONArray("lists")
        for (i in 0 until oldLists.length()) {
            val item = oldLists.getJSONObject(i)
            val id = item.getString("id")
            if (item.optBoolean("shared") && id !in have && old.getJSONObject("views").has(id)) {
                lists.put(item)
                views.put(id, old.getJSONObject("views").getJSONObject(id))
            }
        }
        return result
    }

    private fun tasksOf(list: String): JSONArray? =
        server?.optJSONObject("views")?.optJSONObject(list)?.optJSONArray("tasks")

    private fun addToServer(list: String, task: JSONObject) {
        tasksOf(list)?.put(task)
        writeJson("server.json", server.toString())
    }

    private fun replaceInServer(list: String, task: JSONObject) {
        val tasks = tasksOf(list) ?: return
        for (i in 0 until tasks.length()) {
            if (tasks.getJSONObject(i).getLong("id") == task.getLong("id")) tasks.put(i, task)
        }
        writeJson("server.json", server.toString())
    }

    private fun removeFromServer(list: String, id: Long) {
        val tasks = tasksOf(list) ?: return
        for (i in tasks.length() - 1 downTo 0) {
            if (tasks.getJSONObject(i).getLong("id") == id) tasks.remove(i)
        }
        writeJson("server.json", server.toString())
    }

    // --- что показать: копия + правки поверх ---

    private fun publish() {
        val base = server?.let { parseSync(it) }
        data = base?.let { applyQueue(it, queue) }
        pendingTasks = queue.map { it.list to it.id }.toSet()
        pendingCount = queue.size
        conflict = conflictList.firstOrNull()
    }

    private fun applyQueue(base: SyncData, ops: List<Op>): SyncData {
        val views = base.views.toMutableMap()
        for (op in ops) {
            val view = views[op.list] ?: continue
            views[op.list] = when (op.kind) {
                "create" -> view.copy(tasks = view.tasks + newTask(view, op))
                "delete" -> view.copy(tasks = view.tasks.filter { it.id != op.id })
                else -> view.copy(tasks = view.tasks.map { if (it.id == op.id) patched(view, it, op.fields) else it })
            }
        }
        return base.copy(views = views)
    }

    private fun newTask(view: ListView, op: Op): Task {
        val blank = Task(op.id, "", "", false, view.statuses.firstOrNull { !it.done }?.id, false, false,
            null, null, null, if (view.list.shared) view.user else null, null, null, null, 0, 0, 0)
        return patched(view, blank, op.fields)
    }

    private fun patched(view: ListView, task: Task, f: JSONObject): Task {
        var t = task
        if (f.has("title")) t = t.copy(title = f.getString("title"))
        if (f.has("body")) t = t.copy(body = f.optString("body"))
        if (f.has("due_at")) t = t.copy(dueAt = if (f.isNull("due_at")) null else f.getString("due_at"))
        if (f.has("remind_before")) t = t.copy(remindBefore = if (f.isNull("remind_before")) null else f.getInt("remind_before"))
        if (f.has("urgent")) t = t.copy(urgent = f.getBoolean("urgent"))
        if (f.has("important")) t = t.copy(important = f.getBoolean("important"))
        if (f.has("assignee")) t = t.copy(assignee = if (f.isNull("assignee")) null else f.getString("assignee").ifEmpty { null })
        if (f.has("status_id")) {
            val status = view.statuses.firstOrNull { it.id == f.getLong("status_id") }
            if (status != null) t = t.copy(statusId = status.id, done = status.done)
        } else if (f.has("done") && f.getBoolean("done") != t.done) {
            val status = view.statuses.firstOrNull { it.done == f.getBoolean("done") }
            if (status != null) t = t.copy(statusId = status.id, done = status.done)
        }
        // время выполнения — как на компьютере: ставится, когда задача стала выполненной
        if (t.done != task.done) t = t.copy(doneAt = if (t.done) nowStamp() else null)
        return t
    }

    // --- файлы ---

    private fun saveQueue() {
        writeJson("queue.json", JSONArray(queue.map { it.toJson() }).toString())
        writeJson("conflicts.json", JSONArray(conflictList.map {
            JSONObject().put("op", it.op.toJson()).put("current", it.currentJson)
        }).toString())
    }

    private fun readJson(name: String): String? = try {
        File(dir, name).takeIf { it.exists() }?.readText()
    } catch (e: Exception) {
        null
    }

    /** Пишем во временный файл и подменяем — чтобы при выключении телефона не остался половинчатый. */
    private fun writeJson(name: String, text: String) {
        val tmp = File(dir, "$name.tmp")
        tmp.writeText(text)
        tmp.renameTo(File(dir, name))
    }

}

fun parseSync(o: JSONObject): SyncData {
    val views = o.getJSONObject("views")
    return SyncData(
        lists = parseLists(o),
        views = views.keys().asSequence().associateWith { parseListView(views.getJSONObject(it)) },
        sharedOffline = o.optBoolean("shared_offline"),
        user = o.optString("user"),
        syncedAt = o.optLong("synced_at"),
        pcVersion = o.optString("version"),
    )
}
