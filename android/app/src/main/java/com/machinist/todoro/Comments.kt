package com.machinist.todoro

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONObject

/** Комментарии к задаче — как вкладка «Комментарии» в карточке на компьютере.
 *  Файлы задач на телефон не передаются (так безопаснее) — их смотрят на компьютере. */

data class Comment(val id: Long, val author: String?, val text: String, val createdAt: String?)

/** Комментарии одной задачи (с компьютера, при открытии карточки). */
data class TaskComments(val listId: String, val taskId: Long, val items: List<Comment>)

fun parseComments(listId: String, task: JSONObject): TaskComments {
    val a = task.optJSONArray("comments_list")
    return TaskComments(listId, task.getLong("id"), (0 until (a?.length() ?: 0)).map { i ->
        val o = a!!.getJSONObject(i)
        Comment(o.getLong("id"), if (o.isNull("author")) null else o.getString("author"), o.optString("text"),
            if (o.isNull("created_at")) null else o.getString("created_at"))
    })
}

@Composable
fun CommentsTab(vm: AppViewModel, c: TaskComments, user: String) {
    val p = P
    var text by rememberSaveable { mutableStateOf("") }
    var askDelete by remember { mutableStateOf<Comment?>(null) }
    if (c.items.isEmpty()) {
        Text("Комментариев пока нет — напишите первый.", color = p.done, fontSize = 15.sp)
    }
    c.items.forEachIndexed { i, comment ->
        if (i > 0) HorizontalDivider(Modifier.padding(vertical = 8.dp), color = p.headingLine)
        Row(verticalAlignment = Alignment.CenterVertically) {
            // в личном списке автора не записывают — это вы сами
            Text(comment.author ?: user.ifEmpty { "Вы" }, color = p.text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.width(8.dp))
            Text(comment.createdAt?.let { showStamp(it) }.orEmpty(), Modifier.weight(1f), color = p.muted, fontSize = 12.sp)
            Text("✕", Modifier.clip(RoundedCornerShape(6.dp)).clickable { askDelete = comment }
                .padding(horizontal = 10.dp, vertical = 4.dp), color = p.done, fontSize = 14.sp)
        }
        Text(comment.text, Modifier.padding(top = 3.dp), color = p.text, fontSize = 15.sp)
    }
    Spacer(Modifier.height(12.dp))
    Field(text, { text = it }, Modifier.fillMaxWidth(), placeholder = "Написать комментарий…", singleLine = false, minLines = 2)
    Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.End) {
        FlatButton(if (vm.sending) "Отправляю…" else "Отправить", { vm.addComment(text) { text = "" } },
            look = Look.ACCENT, enabled = text.isNotBlank() && !vm.sending, height = 40.dp)
    }

    askDelete?.let { comment ->
        AlertDialog(
            onDismissRequest = { askDelete = null },
            containerColor = p.surface,
            title = { Text("Удалить комментарий?") },
            text = { Text("«${comment.text.take(80)}» удалится — и на компьютере тоже.") },
            confirmButton = { TextButton(onClick = { askDelete = null; vm.deleteComment(comment) }) { Text("Удалить", color = p.danger) } },
            dismissButton = { TextButton(onClick = { askDelete = null }) { Text("Отмена") } },
        )
    }
}
