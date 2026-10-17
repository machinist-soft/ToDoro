package com.machinist.todoro

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
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

/** Состояние экрана. Сами задачи, связь и очередь правок — в Repo. */
class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("app", Context.MODE_PRIVATE)

    init {
        Repo.init(app)
    }

    var listId by mutableStateOf(prefs.getString("list", "personal") ?: "personal")
        private set
    var filter by mutableStateOf(Filter.ACTIVE)
    var onlyMine by mutableStateOf(false)
    var draft by mutableStateOf<Draft?>(null)
    var remindersOn by mutableStateOf(Reminders.enabled(app))
        private set

    val lists: List<TaskList> get() = Repo.data?.lists.orEmpty()

    /** Открытый список; если его больше нет — личный. */
    val view: ListView?
        get() {
            val data = Repo.data ?: return null
            return data.views[listId] ?: data.views["personal"]
        }

    fun pair(text: String): String? {
        val parsed = Pairing.parse(text)
            ?: return "Это не QR-код ToDoro. Откройте на компьютере ☰ Меню → Подключить телефон."
        Repo.pair(parsed)
        return null
    }

    fun unpair() {
        draft = null
        Repo.unpair()
    }

    fun refresh() {
        Repo.launch { Repo.sync() }
    }

    fun selectList(id: String) {
        listId = id
        prefs.edit().putString("list", id).apply()
        onlyMine = false
    }

    fun setReminders(on: Boolean) {
        remindersOn = on
        Reminders.setEnabled(getApplication(), on)
    }

    fun visibleTasks(): List<Task> {
        val v = view ?: return emptyList()
        var tasks = when (filter) {
            Filter.ACTIVE -> v.tasks.filter { !it.done }
            Filter.DONE -> v.tasks.filter { it.done }
            Filter.ALL -> v.tasks
        }
        if (v.list.shared && onlyMine) tasks = tasks.filter { it.assignee == v.user }
        // невыполненные сверху; среди них — по сроку (без срока — в конце), затем новые выше
        return tasks.sortedWith(
            compareBy<Task> { it.done }
                .thenBy { it.dueAt == null }
                .thenBy { it.dueAt }
                .thenByDescending { if (it.id < 0) Long.MAX_VALUE else it.id }
        )
    }

    // --- изменения: сразу на экране, на компьютер — когда будет связь ---

    fun toggleDone(task: Task) {
        val v = view ?: return
        Repo.patch(v.list.id, task, JSONObject().put("done", !task.done), checkVersion = false)
        if (!task.done) Repo.message = "Выполнено: ${task.title}"
    }

    fun openTask(task: Task?) {
        draft = Draft(task, statusId = task?.statusId ?: view?.statuses?.firstOrNull { !it.done }?.id)
    }

    fun openTask(list: String, taskId: Long) {
        val data = Repo.data ?: return
        val task = data.views[list]?.tasks?.firstOrNull { it.id == taskId } ?: return
        selectList(list)
        openTask(task)
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
        Repo.message = "Задача удалена"
    }
}
