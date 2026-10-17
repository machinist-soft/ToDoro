package com.machinist.todoro

import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/** Списки, колонки и задачи — в том виде, в каком их присылает компьютер (phone.py). */

data class TaskList(val id: String, val name: String, val shared: Boolean)

data class Status(val id: Long, val name: String, val color: Long, val done: Boolean)

data class Task(
    val id: Long,
    val title: String,
    val body: String,
    val done: Boolean,
    val statusId: Long?,
    val urgent: Boolean,
    val important: Boolean,
    val dueAt: String?,          // «ГГГГ-ММ-ДД ЧЧ:ММ»
    val remindBefore: Int?,      // минут до срока; null — не напоминать
    val createdAt: String?,
    val author: String?,
    val assignee: String?,
    val updatedBy: String?,
    val updatedAt: String?,
    val version: Int,
    val files: Int,
    val comments: Int,
    val doneAt: String? = null,  // когда выполнили: «ГГГГ-ММ-ДД ЧЧ:ММ:СС»
) {
    val due: LocalDateTime? get() = parseDue(dueAt)
    val overdue: Boolean get() = !done && due?.isBefore(LocalDateTime.now()) == true
    /** Матрица Эйзенхауэра: 1 — срочно и важно, 2 — важно, 3 — срочно, 4 — обычная. */
    val level: Int get() = if (urgent && important) 1 else if (important) 2 else if (urgent) 3 else 4
    val doneToday: Boolean get() = done && doneAt?.startsWith(java.time.LocalDate.now().toString()) == true
}

val PRIORITY_NAMES = mapOf(1 to "Срочно и важно", 2 to "Важно", 3 to "Срочно", 4 to "")
val PRIORITY_HINTS = mapOf(1 to "сделать в первую очередь", 2 to "запланировать",
    3 to "сделать быстро или поручить", 4 to "можно отложить")

fun nowStamp(): String = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"))

data class ListView(
    val list: TaskList,
    val statuses: List<Status>,
    val tasks: List<Task>,
    val members: List<String>,
    val user: String,
)

val DUE_FORMAT: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

fun parseDue(text: String?): LocalDateTime? = try {
    text?.let { LocalDateTime.parse(it, DUE_FORMAT) }
} catch (e: Exception) {
    null
}

/** «20.10 10:00», для другого года — «20.10.2027 10:00». */
fun showDue(due: LocalDateTime): String {
    val pattern = if (due.year == LocalDateTime.now().year) "dd.MM HH:mm" else "dd.MM.yyyy HH:mm"
    return due.format(DateTimeFormatter.ofPattern(pattern))
}

/** «2026-10-17 19:46:21» → «17.10.2026 19:46». */
fun showStamp(text: String?): String = try {
    LocalDateTime.parse(text, DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"))
        .format(DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm"))
} catch (e: Exception) {
    text.orEmpty()
}

/** Варианты напоминания — как в программе на компьютере. */
val REMIND_OPTIONS: List<Pair<String, Int?>> = listOf(
    "Не напоминать" to null,
    "За 5 минут" to 5,
    "За 15 минут" to 15,
    "За 30 минут" to 30,
    "За 1 час" to 60,
    "За 2 часа" to 120,
    "За 1 день" to 24 * 60,
    "За 2 дня" to 2 * 24 * 60,
    "За 1 неделю" to 7 * 24 * 60,
)

fun remindLabel(minutes: Int?): String =
    REMIND_OPTIONS.firstOrNull { it.second == minutes }?.first ?: "За $minutes мин"

private fun JSONObject.str(key: String): String? = if (isNull(key)) null else getString(key)
private fun JSONObject.int(key: String): Int? = if (isNull(key)) null else getInt(key)
private fun JSONObject.long(key: String): Long? = if (isNull(key)) null else getLong(key)

private inline fun <T> JSONArray.map(block: (Int) -> T): List<T> = (0 until length()).map(block)

fun parseTask(o: JSONObject) = Task(
    id = o.getLong("id"),
    title = o.optString("title"),
    body = o.str("body").orEmpty(),
    done = o.optBoolean("done"),
    statusId = o.long("status_id"),
    urgent = o.optBoolean("urgent"),
    important = o.optBoolean("important"),
    dueAt = o.str("due_at"),
    remindBefore = o.int("remind_before"),
    createdAt = o.str("created_at"),
    author = o.str("author"),
    assignee = o.str("assignee")?.takeIf { it.isNotEmpty() },
    updatedBy = o.str("updated_by"),
    updatedAt = o.str("updated_at"),
    version = o.optInt("version"),
    files = o.optInt("files"),
    comments = o.optInt("comments"),
    doneAt = o.str("done_at"),
)

fun parseLists(o: JSONObject): List<TaskList> = o.getJSONArray("lists").let { a ->
    a.map { i ->
        val item = a.getJSONObject(i)
        TaskList(item.getString("id"), item.getString("name"), item.optBoolean("shared"))
    }
}

fun parseListView(o: JSONObject): ListView {
    val list = o.getJSONObject("list")
    val statuses = o.getJSONArray("statuses")
    val tasks = o.getJSONArray("tasks")
    val members = o.optJSONArray("members") ?: JSONArray()
    return ListView(
        list = TaskList(list.getString("id"), list.getString("name"), list.optBoolean("shared")),
        statuses = statuses.map { i ->
            val s = statuses.getJSONObject(i)
            Status(s.getLong("id"), s.getString("name"), parseColor(s.optString("color")), s.optBoolean("done"))
        },
        tasks = tasks.map { i -> parseTask(tasks.getJSONObject(i)) },
        members = members.map { i -> members.getString(i) },
        user = o.optString("user"),
    )
}

/** «#22c55e» → 0xFF22C55E. */
fun parseColor(text: String): Long = try {
    0xFF000000L or text.removePrefix("#").toLong(16)
} catch (e: Exception) {
    0xFF9CA3AFL
}
