package com.machinist.todoro

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Тема приложения: как в телефоне, всегда светлая или всегда тёмная (☰ Меню → Тема). */
enum class ThemeMode(val label: String) { SYSTEM("Как в телефоне"), LIGHT("Светлая"), DARK("Тёмная") }

enum class Filter(val label: String) { ALL("Все"), ACTIVE("Активные"), DONE("Выполненные"), OVERDUE("Просроченные") }

/** Что говорит Тоторо (как update_buddy в todoro.py). mood: normal, alert, sleep. */
data class Buddy(val lead: String, val tasks: List<Task>, val tail: String, val mood: String, val stats: String)

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

/** Состояние экрана. Сами задачи, связь и очередь правок — в Repo. */
class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("app", Context.MODE_PRIVATE)

    init {
        Repo.init(app)
    }

    var listId by mutableStateOf(prefs.getString("list", "personal") ?: "personal")
        private set
    var filter by mutableStateOf(Filter.ALL)
    var onlyMine by mutableStateOf(false)
    var draft by mutableStateOf<Draft?>(null)
    /** Открыто окно «О приложении». */
    var about by mutableStateOf(false)
    /** Открытая карточка задачи (номер задачи в открытом списке). */
    var cardId by mutableStateOf<Long?>(null)
    var buddyOn by mutableStateOf(prefs.getBoolean("buddy", false))
        private set
    var remindersOn by mutableStateOf(Reminders.enabled(app))
        private set
    var theme by mutableStateOf(ThemeMode.entries.firstOrNull { it.name == prefs.getString("theme", null) } ?: ThemeMode.SYSTEM)
        private set

    val lists: List<TaskList> get() = Repo.data?.lists.orEmpty()

    /** Открытый список; если его больше нет — личный. */
    val view: ListView?
        get() {
            val data = Repo.data ?: return null
            return data.views[listId] ?: data.views["personal"]
        }

    /** Подключение, которое ждёт «Подключить» в окне-вопросе (см. PairingDialog). */
    var pendingPairing by mutableStateOf<Pairing?>(null)
        private set

    /**
     * fromLink — пришла ссылка todoro://connect (камера телефона, но так же её может открыть
     * любой сайт или письмо): тогда сначала спрашиваем, чтобы чужая ссылка не подключила
     * телефон к чужому компьютеру. Спрашиваем и когда смена компьютера сотрёт неотправленные правки.
     */
    fun pair(text: String, fromLink: Boolean = false): String? {
        val parsed = Pairing.parse(text)
            ?: return "Это не QR-код ToDoro. Откройте на компьютере ☰ Меню → Подключить телефон."
        val unknownLink = fromLink && Repo.pairing?.key != parsed.key
        val losesEdits = !Repo.samePc(parsed) && Repo.pendingCount > 0
        if (unknownLink || losesEdits) pendingPairing = parsed else Repo.pair(parsed)
        return null
    }

    fun answerPairing(connect: Boolean) {
        val p = pendingPairing ?: return
        pendingPairing = null
        if (connect) Repo.pair(p)
    }

    fun unpair() {
        draft = null
        Repo.unpair()
    }

    fun refresh() {
        Repo.launch { Repo.sync() }
    }

    fun selectList(id: String) {
        if (id != listId) cardId = null
        listId = id
        prefs.edit().putString("list", id).apply()
        onlyMine = false
    }

    fun setReminders(on: Boolean) {
        remindersOn = on
        Reminders.setEnabled(getApplication(), on)
    }

    fun chooseTheme(mode: ThemeMode) {
        theme = mode
        prefs.edit().putString("theme", mode.name).apply()
    }

    fun setBuddy(on: Boolean) {
        buddyOn = on
        prefs.edit().putBoolean("buddy", on).apply()
    }

    fun visibleTasks(): List<Task> {
        val v = view ?: return emptyList()
        var tasks = when (filter) {
            Filter.ACTIVE -> v.tasks.filter { !it.done }
            Filter.DONE -> v.tasks.filter { it.done }
            Filter.OVERDUE -> v.tasks.filter { it.overdue }
            Filter.ALL -> v.tasks
        }
        if (v.list.shared && onlyMine) tasks = tasks.filter { it.assignee == v.user }
        // «По приоритету», как на компьютере: невыполненные сверху, затем срочно и важно → важно →
        // срочно → обычные, внутри — по сроку (без срока — в конце), затем по номеру
        return tasks.sortedWith(
            compareBy<Task> { it.done }
                .thenBy { it.level }
                .thenBy { it.dueAt == null }
                .thenBy { it.dueAt }
                .thenBy { if (it.id < 0) Long.MAX_VALUE else it.id }
        )
    }

    /** Что сказать Тоторо — как на компьютере: о просроченных, о сроке сегодня, о самом важном. */
    fun buddy(): Buddy? {
        val v = view ?: return null
        val now = java.time.LocalDateTime.now()
        val active = v.tasks.filter { !it.done }
        val overdue = active.filter { it.overdue }.sortedWith(compareBy({ it.level }, { it.dueAt }, { it.id }))
        val today = active.filter { t -> t.due?.let { !it.isBefore(now) && it.toLocalDate() == now.toLocalDate() } == true }
        val doneToday = v.tasks.count { it.doneToday }
        val stats = listOfNotNull(
            if (overdue.isNotEmpty()) "Просрочено: ${overdue.size}" else null,
            if (today.isNotEmpty()) "На сегодня: ${today.size}" else null,
            if (doneToday > 0) "Сегодня выполнено: $doneToday" else null,
        ).joinToString(" · ")
        return when {
            v.tasks.isEmpty() -> Buddy("Привет! Я Тоторо.", emptyList(),
                "Добавь первую задачу — я присмотрю за ней.", "normal", stats)
            overdue.isNotEmpty() -> {
                val n = overdue.size
                val word = if (n % 10 == 1 && n % 100 != 11) "задачи" else "задач"
                val shown = overdue.take(3)
                val tail = when {
                    n == 1 -> "Давай сделаем её первой?"
                    n > shown.size -> "И ещё ${n - shown.size}. Все — кнопка «Просроченные»."
                    else -> "Давай начнём с первой?"
                }
                Buddy(if (n == 1) "Ой! Срок уже прошёл:" else "Ой! Срок прошёл у $n $word:", shown, tail, "alert", stats)
            }
            today.isNotEmpty() -> {
                val task = today.minBy { it.dueAt.orEmpty() }
                val more = if (today.size > 1) " Всего на сегодня: ${today.size}." else ""
                Buddy("Сегодня срок:", listOf(task), "до ${task.due!!.toLocalTime()}.$more", "normal", stats)
            }
            active.isNotEmpty() -> {
                val task = active.minWith(compareBy({ it.level }, { it.dueAt ?: "9" }, { it.id }))
                Buddy("Начни с самого важного:", listOf(task),
                    "Активных задач: ${active.size}. Ты справишься!", "normal", stats)
            }
            else -> Buddy("Все задачи выполнены!", emptyList(),
                "Можно отдохнуть под камфорным деревом.", "sleep", stats)
        }
    }

    /** Строка «Заголовок новой задачи…» + «Добавить»: задача в первую колонку, без срока. */
    fun quickAdd(title: String): Boolean {
        val v = view ?: return false
        if (title.isBlank()) return false
        val fields = org.json.JSONObject().put("title", title.trim())
        Repo.create(v.list.id, fields, title.trim())
        if (filter == Filter.DONE || filter == Filter.OVERDUE) filter = Filter.ALL
        return true
    }

    fun card(): Task? = cardId?.let { id -> view?.tasks?.firstOrNull { it.id == id } }

    // --- комментарии открытой карточки (нужна связь с компьютером) ---

    var comments by mutableStateOf<TaskComments?>(null)
        private set
    var commentsProblem by mutableStateOf<String?>(null)
        private set
    var sending by mutableStateOf(false)
        private set

    /** Записать состояние после ответа компьютера одним «снимком» Compose — экран гарантированно
     *  узнает об изменении (без этого в проверке снимков экрана карточка не перерисовывалась). */
    private fun applied(block: () -> Unit) = androidx.compose.runtime.snapshots.Snapshot.withMutableSnapshot(block)

    private fun problemText(e: Exception) = when (e) {
        is OfflineException -> "Комментарии видны, когда телефон на связи с компьютером. " + e.message
        is ApiException -> e.message ?: "Ошибка"
        else -> "Не получилось: ${e.message}"
    }

    /** Карточка открылась (или поменялось число комментариев) — берём их с компьютера. */
    fun loadComments(task: Task) {
        val v = view ?: return
        if (task.id < 0) {
            comments = null
            commentsProblem = "Задача ещё не дошла до компьютера — комментарии можно будет написать потом."
            return
        }
        viewModelScope.launch {
            try {
                val loaded = parseComments(v.list.id, Repo.details(v.list.id, task.id))
                applied {
                    comments = loaded
                    commentsProblem = null
                }
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                applied {
                    if (comments?.taskId != task.id) comments = null
                    commentsProblem = problemText(e)
                }
            }
        }
    }

    private fun commentAction(done: String?, work: suspend (TaskComments) -> JSONObject?) {
        val c = comments ?: return
        sending = true
        viewModelScope.launch {
            try {
                val task = work(c) ?: Repo.details(c.listId, c.taskId)
                applied { comments = parseComments(c.listId, task) }
                done?.let { Repo.message = it }
                Repo.launch { Repo.sync() }  // счётчик 💬 в списке
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                Repo.message = problemText(e)
            } finally {
                applied { sending = false }
            }
        }
    }

    fun addComment(text: String, onSent: () -> Unit) {
        if (text.isBlank()) return
        commentAction(null) { c -> Repo.addComment(c.listId, c.taskId, text.trim()).also { onSent() } }
    }

    fun deleteComment(comment: Comment) =
        commentAction("Комментарий удалён") { c -> Repo.deleteComment(c.listId, c.taskId, comment.id); null }

    // --- изменения: сразу на экране, на компьютер — когда будет связь ---

    fun toggleDone(task: Task) {
        val v = view ?: return
        Repo.patch(v.list.id, task, JSONObject().put("done", !task.done), checkVersion = false)
        if (!task.done) Repo.message = "Выполнено: ${task.title}"
    }

    /** Форма: новая задача (task == null) или «Изменить» в карточке. */
    fun openTask(task: Task?) {
        draft = Draft(task, statusId = task?.statusId ?: view?.statuses?.firstOrNull { !it.done }?.id)
    }

    /** Нажали на напоминание — открываем карточку задачи. */
    fun openTask(list: String, taskId: Long) {
        val data = Repo.data ?: return
        if (data.views[list]?.tasks?.any { it.id == taskId } != true) return
        selectList(list)
        draft = null
        cardId = taskId
    }

    fun save(d: Draft) {
        val v = view ?: return
        if (d.title.isBlank()) {
            Repo.message = "Напишите, что нужно сделать"
            return
        }
        val fields = JSONObject()
        val base = d.task
        fun changed(new: Any?, old: Any?) = base == null || new != old
        if (changed(d.title.trim(), base?.title)) fields.put("title", d.title.trim())
        if (changed(d.body, base?.body)) fields.put("body", d.body)
        if (changed(d.dueAt, base?.dueAt)) fields.put("due_at", d.dueAt ?: JSONObject.NULL)
        if (changed(d.remindBefore, base?.remindBefore)) fields.put("remind_before", d.remindBefore ?: JSONObject.NULL)
        if (changed(d.urgent, base?.urgent)) fields.put("urgent", d.urgent)
        if (changed(d.important, base?.important)) fields.put("important", d.important)
        if (v.list.shared && changed(d.assignee, base?.assignee)) fields.put("assignee", d.assignee ?: JSONObject.NULL)
        if (d.statusId != null && changed(d.statusId, base?.statusId)) fields.put("status_id", d.statusId)
        if (base == null) {
            Repo.create(v.list.id, fields, d.title.trim())
        } else if (fields.length() > 0) {
            Repo.patch(v.list.id, base, fields, checkVersion = true)
        }
        draft = null
    }

    fun delete(task: Task) {
        val v = view ?: return
        Repo.delete(v.list.id, task)
        draft = null
        cardId = null
        Repo.message = "Задача удалена"
    }
}
