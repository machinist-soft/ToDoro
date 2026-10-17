package com.machinist.todoro

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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

/** Карточка задачи — как правая панель окна ToDoro, когда задача выбрана. */
@Composable
fun TaskCard(vm: AppViewModel, task: Task, view: ListView) {
    val p = P
    val snackbar = remember { SnackbarHostState() }
    MessageEffect(snackbar)
    var askDelete by remember { mutableStateOf(false) }
    var tab by rememberSaveable { mutableStateOf("body") }
    BackHandler { vm.cardId = null }
    // комментарии — с компьютера; заново, если их число поменялось (написали на компьютере)
    LaunchedEffect(task.id, task.comments) { vm.loadComments(task) }
    val status = view.statuses.firstOrNull { it.id == task.statusId }

    Scaffold(containerColor = p.bg, snackbarHost = { SnackbarHost(snackbar) }) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())
                .padding(horizontal = 14.dp, vertical = 10.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                LinkText("‹ Назад к списку") { vm.cardId = null }
                Spacer(Modifier.weight(1f))
                Text(view.list.name, color = p.muted, fontSize = 13.sp)
            }
            Spacer(Modifier.height(8.dp))
            Panel {
                Column(Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (task.id > 0) {
                            Text("#${task.id}", Modifier.clip(RoundedCornerShape(5.dp)).background(p.chipBg)
                                .padding(horizontal = 7.dp, vertical = 2.dp), color = p.muted, fontSize = 13.sp)
                            Spacer(Modifier.width(10.dp))
                        }
                        if (task.level < 4) {
                            PriorityDot(task.level)
                            Spacer(Modifier.width(6.dp))
                            Text(PRIORITY_NAMES[task.level].orEmpty(), color = p.muted, fontSize = 13.sp)
                        }
                    }
                    Text(task.title, Modifier.padding(top = 10.dp), color = if (task.done) p.done else p.text,
                        fontSize = 21.sp, fontWeight = FontWeight.SemiBold)
                    Row(Modifier.padding(top = 6.dp)) {
                        StatusMark(task, status, fontSize = 14)
                        if (task.overdue) Text("  · срок прошёл", color = p.danger, fontSize = 14.sp)
                    }
                    HorizontalDivider(Modifier.padding(vertical = 12.dp), color = p.headingLine)
                    Segmented(listOf("body" to "Описание", "comments" to "Комментарии  ${task.comments}"), tab) { tab = it }
                    Spacer(Modifier.height(10.dp))
                    val c = vm.comments?.takeIf { it.taskId == task.id && it.listId == view.list.id }
                    when {
                        tab == "body" -> Text(task.body.ifBlank { "Описания нет." },
                            color = if (task.body.isBlank()) p.done else p.text, fontSize = 15.sp)
                        c == null -> Text(vm.commentsProblem ?: "Загружаю…", color = p.muted, fontSize = 14.sp)
                        else -> {
                            CommentsTab(vm, c, view.user)
                            vm.commentsProblem?.let { Text(it, Modifier.padding(top = 8.dp), color = p.warn, fontSize = 13.sp) }
                        }
                    }
                    HorizontalDivider(Modifier.padding(vertical = 12.dp), color = p.headingLine)
                    Props(task, view)
                }
            }
            Spacer(Modifier.height(12.dp))
            FlatButton(if (task.done) "↺  Вернуть в работу" else "✔  Выполнено", { vm.toggleDone(task) },
                Modifier.fillMaxWidth(), look = Look.ACCENT_SOFT)
            Spacer(Modifier.height(8.dp))
            FlatButton("✎  Изменить", { vm.openTask(task) }, Modifier.fillMaxWidth())
            Spacer(Modifier.height(8.dp))
            FlatButton("Удалить задачу", { askDelete = true }, Modifier.fillMaxWidth(), look = Look.DANGER_SOFT)
            Spacer(Modifier.height(24.dp))
        }
    }

    if (askDelete) {
        AlertDialog(
            onDismissRequest = { askDelete = false },
            containerColor = p.surface,
            title = { Text("Удалить задачу?") },
            text = { Text("«${task.title}» удалится вместе с файлами и комментариями" +
                if (view.list.shared) " — у всех участников." else ".") },
            confirmButton = { TextButton(onClick = { askDelete = false; vm.delete(task) }) { Text("Удалить", color = p.danger) } },
            dismissButton = { TextButton(onClick = { askDelete = false }) { Text("Отмена") } },
        )
    }
}

/** Свойства задачи: «Важность — Важно», «Срок — 17.10.2026 23:00» … — как в карточке на компьютере. */
@Composable
fun Props(task: Task, view: ListView) {
    val p = P
    val rows = listOfNotNull(
        "Важность" to if (task.important) "Важно" else "Обычная",
        "Срочность" to if (task.urgent) "Срочно" else "Не срочно",
        "Срок" to (task.due?.let { showStamp(it.format(DUE_FORMAT) + ":00") } ?: "Без срока"),
        if (task.due != null) "Напомнить" to remindLabel(task.remindBefore) else null,
        // файлы на телефон не передаются — только сколько их
        if (task.files > 0) "Файлы" to "${task.files} — смотрите на компьютере" else null,
        task.createdAt?.let { "Создана" to showStamp(it) },
        task.author?.let { "Автор" to it },
        if (view.list.shared) "Исполнитель" to (task.assignee ?: "Не назначен") else null,
        task.updatedAt?.let { "Изменена" to showStamp(it) + (task.updatedBy?.let { b -> ", $b" } ?: "") },
    )
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        rows.forEach { (label, value) ->
            Row {
                Text(label, Modifier.width(110.dp), color = p.muted, fontSize = 14.sp)
                Text(value, color = if (label == "Срок" && task.overdue) p.danger else p.text, fontSize = 14.sp,
                    fontWeight = FontWeight.Medium)
            }
        }
    }
}
