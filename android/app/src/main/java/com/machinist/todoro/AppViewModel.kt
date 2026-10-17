package com.machinist.todoro

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import org.json.JSONObject

enum class Filter(val label: String) { ACTIVE("Активные"), ALL("Все"), DONE("Выполненные") }

/** Задача в форме правки. task == null — новая задача. */
data class Draft(
    val task: Task?,
    val title: String = task?.title.orEmpty(),
    val body: String = task?.body.orEmpty(),
    val statusId: Long? = task?.statusId,
    val dueAt: String? = task?.dueAt,
    val remindBefore: Int? = task?.remindBefore,
    val urgent: Boolean = task?.urgent ?: false,
    val important: Boolean = task?.important ?: false,
    val assignee: String? = task?.assignee,
) {
    val changed: Boolean
        get() = if (task == null) title.isNotBlank() || body.isNotBlank() else this != Draft(task)
}

/** Пока правили задачу на телефоне, её изменили на компьютере (или другой участник). */
data class Conflict(val draft: Draft, val current: Task)

class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("app", Context.MODE_PRIVATE)

    var pairing by mutableStateOf(Pairing.load(app))
        private set
    private var api: Api? = pairing?.let { Api(it) }

    var lists by mutableStateOf<List<TaskList>>(emptyList())
        private set
    var sharedOffline by mutableStateOf(false)
        private set
    var listId by mutableStateOf(prefs.getString("list", "personal") ?: "personal")
        private set
    var view by mutableStateOf<ListView?>(null)
        private set
    var loading by mutableStateOf(false)
        private set
    /** Почему не удалось связаться с компьютером (полоса вверху). */
    var problem by mutableStateOf<String?>(null)
        private set
    /** Ключ больше не действует — нужно подключить телефон заново. */
    var keyRejected by mutableStateOf(false)
        private set
    /** Короткое сообщение внизу экрана. */
    var message by mutableStateOf<String?>(null)

    var filter by mutableStateOf(Filter.ACTIVE)
    var onlyMine by mutableStateOf(false)

    var draft by mutableStateOf<Draft?>(null)
    var conflict by mutableStateOf<Conflict?>(null)
        private set
    var saving by mutableStateOf(false)
        private set

    private var refreshJob: Job? = null

    // --- подключение ---

    /** Отсканирован QR-код. Возвращает текст ошибки или null. */
    fun pair(text: String): String? {
        val parsed = Pairing.parse(text)
            ?: return "Это не QR-код ToDoro. Откройте на компьютере ☰ Меню → Подключить телефон."
        parsed.save(getApplication())
        pairing = parsed
        api = Api(parsed)
        keyRejected = false
        problem = null
        view = null
        lists = emptyList()
        refresh()
        return null
    }

    fun unpair() {
        Pairing.clear(getApplication())
        pairing = null
        api = null
        view = null
        lists = emptyList()
        problem = null
        keyRejected = false
        draft = null
    }

    // --- чтение ---

    /** Перечитать списки и открытый список. quiet — без крутилки (фоновое обновление). */
    fun refresh(quiet: Boolean = false) {
        val api = api ?: return
        if (refreshJob?.isActive == true) return
        refreshJob = viewModelScope.launch {
            if (!quiet) loading = true
            try {
                val answer = api.get("/lists")
                lists = parseLists(answer)
                sharedOffline = answer.optBoolean("shared_offline")
                if (lists.none { it.id == listId }) {
                    if (!(sharedOffline && listId.startsWith("t"))) selectStored("personal")
                }
                if (lists.any { it.id == listId }) {
                    view = parseListView(api.get(Api.listPath(listId)))
                } else {
                    view = null
                }
                problem = null
            } catch (e: Exception) {
                handle(e)
            } finally {
                loading = false
            }
        }
    }

    fun selectList(id: String) {
        if (id == listId) return
        selectStored(id)
        view = null
        onlyMine = false
        refreshJob?.cancel()
        refresh()
    }

    private fun selectStored(id: String) {
        listId = id
        prefs.edit().putString("list", id).apply()
    }

    private fun handle(e: Exception) {
        when (e) {
            is OfflineException -> problem = e.message
            is ApiException -> when (e.status) {
                401 -> keyRejected = true
                503 -> problem = e.message
                else -> message = e.message
            }
            is kotlinx.coroutines.CancellationException -> throw e
            else -> message = "Не получилось: ${e.message}"
        }
    }

    fun visibleTasks(): List<Task> {
        val v = view ?: return emptyList()
        var tasks = when (filter) {
            Filter.ACTIVE -> v.tasks.filter { !it.done }
            Filter.DONE -> v.tasks.filter { it.done }
            Filter.ALL -> v.tasks
        }
        if (v.list.shared && onlyMine) tasks = tasks.filter { it.assignee == v.user }
        // невыполненные сверху; среди них — по сроку (без срока — в конце), затем по номеру
        return tasks.sortedWith(
            compareBy<Task> { it.done }
                .thenBy { it.dueAt == null }
                .thenBy { it.dueAt }
                .thenByDescending { if (it.done) it.id else -it.id }
        )
    }

    // --- изменения ---

    fun toggleDone(task: Task) {
        val api = api ?: return
        val v = view ?: return
        // сразу показываем галочку, не дожидаясь компьютера
        view = v.copy(tasks = v.tasks.map { if (it.id == task.id) it.copy(done = !task.done) else it })
        viewModelScope.launch {
            try {
                api.patch("${Api.listPath(v.list.id)}/tasks/${task.id}", JSONObject().put("done", !task.done))
                if (!task.done) message = "Выполнено: ${task.title}"
            } catch (e: Exception) {
                handle(e)
            }
            refreshJob?.cancel()
            refresh(quiet = true)
        }
    }

    fun openTask(task: Task?) {
        draft = Draft(task, statusId = task?.statusId ?: view?.statuses?.firstOrNull { !it.done }?.id)
    }

    /** force — «Сохранить мой вариант» после конфликта: поверх версии current. */
    fun save(d: Draft, over: Task? = null) {
        val api = api ?: return
        val v = view ?: return
        if (d.title.isBlank()) {
            message = "Напишите, что нужно сделать"
            return
        }
        saving = true
        viewModelScope.launch {
            try {
                val json = JSONObject()
                    .put("title", d.title.trim())
                    .put("body", d.body)
                    .put("due_at", d.dueAt ?: JSONObject.NULL)
                    .put("remind_before", d.remindBefore ?: JSONObject.NULL)
                    .put("urgent", d.urgent)
                    .put("important", d.important)
                if (v.list.shared) json.put("assignee", d.assignee ?: JSONObject.NULL)
                val base = d.task
                if (base == null) {
                    d.statusId?.let { json.put("status_id", it) }
                    api.post("${Api.listPath(v.list.id)}/tasks", json)
                } else {
                    if (d.statusId != null && d.statusId != base.statusId) json.put("status_id", d.statusId)
                    json.put("version", (over ?: base).version)
                    api.patch("${Api.listPath(v.list.id)}/tasks/${base.id}", json)
                }
                draft = null
                conflict = null
            } catch (e: ApiException) {
                val current = e.body?.optJSONObject("task")
                if (e.status == 409 && current != null) {
                    conflict = Conflict(d, parseTask(current))
                } else {
                    handle(e)
                }
            } catch (e: Exception) {
                handle(e)
            } finally {
                saving = false
            }
            refreshJob?.cancel()
            refresh(quiet = true)
        }
    }

    fun keepTheirs() {
        conflict = null
        draft = null
    }

    fun delete(task: Task) {
        val api = api ?: return
        val v = view ?: return
        viewModelScope.launch {
            try {
                api.delete("${Api.listPath(v.list.id)}/tasks/${task.id}")
                draft = null
                message = "Задача удалена"
            } catch (e: Exception) {
                handle(e)
            }
            refreshJob?.cancel()
            refresh(quiet = true)
        }
    }
}
