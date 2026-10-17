package com.machinist.todoro

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

private val DEFAULT_TIME: LocalTime = LocalTime.of(9, 0)  // как DEFAULT_TIME на компьютере

/** Форма «Изменение задачи» / «Новая задача» — как форма в правой панели окна. */
@Composable
fun TaskForm(vm: AppViewModel, draft: Draft, view: ListView) {
    val p = P
    val snackbar = remember { SnackbarHostState() }
    MessageEffect(snackbar)
    var askDiscard by remember { mutableStateOf(false) }
    fun update(d: Draft) {
        vm.draft = d
    }
    fun back() {
        if (draft.changed) askDiscard = true else vm.draft = null
    }
    BackHandler { back() }

    Scaffold(containerColor = p.bg, snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            Row(Modifier.fillMaxWidth().background(p.surface).imePadding().padding(horizontal = 14.dp, vertical = 10.dp)) {
                FlatButton("Сохранить", { vm.save(draft) }, Modifier.weight(1f), look = Look.ACCENT)
                Spacer(Modifier.width(8.dp))
                FlatButton("Отмена", ::back, Modifier.weight(1f))
            }
        }) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())
                .padding(horizontal = 14.dp, vertical = 10.dp),
        ) {
            Text(if (draft.task == null) "Новая задача" else "Изменение задачи", color = p.text, fontSize = 20.sp,
                fontWeight = FontWeight.SemiBold)
            Text(view.list.name + if (view.list.shared) " · общий" else "", color = p.muted, fontSize = 13.sp)

            FieldLabel("Заголовок")
            Field(draft.title, { update(draft.copy(title = it)) }, Modifier.fillMaxWidth())
            FieldLabel("Описание")
            Field(draft.body, { update(draft.copy(body = it)) }, Modifier.fillMaxWidth(), singleLine = false, minLines = 4)

            FieldLabel("Статус")
            DropField(view.statuses.firstOrNull { it.id == draft.statusId }?.name ?: "—",
                view.statuses.map { it.name to it.id }, Modifier.fillMaxWidth()) { update(draft.copy(statusId = it)) }

            if (view.list.shared) {
                FieldLabel("Исполнитель")
                val people = (view.members + listOfNotNull(draft.assignee)).distinct()
                DropField(draft.assignee ?: "Не назначен",
                    listOf("Не назначен" to null) + people.map { (if (it == view.user) "$it (я)" else it) to it },
                    Modifier.fillMaxWidth()) { update(draft.copy(assignee = it)) }
            }

            FieldLabel("Срок выполнения")
            DueFields(draft, ::update)

            FieldLabel("Приоритет")
            Row {
                CheckLine("Срочно", draft.urgent) { update(draft.copy(urgent = it)) }
                Spacer(Modifier.width(12.dp))
                CheckLine("Важно", draft.important) { update(draft.copy(important = it)) }
            }
            val level = Task(0, "", "", false, null, draft.urgent, draft.important, null, null, null, null,
                null, null, null, 0, 0, 0).level
            Row(verticalAlignment = Alignment.CenterVertically) {
                PriorityDot(level)
                Spacer(Modifier.width(6.dp))
                Text("${PRIORITY_NAMES[level]!!.ifEmpty { "Обычная задача" }} — ${PRIORITY_HINTS[level]}",
                    color = p.muted, fontSize = 13.sp)
            }

            FieldLabel("Напоминание")
            if (draft.dueAt == null) {
                Text("Сначала укажите срок.", color = p.done, fontSize = 14.sp)
            } else {
                val options = REMIND_OPTIONS + listOfNotNull(
                    draft.remindBefore?.takeIf { m -> REMIND_OPTIONS.none { it.second == m } }?.let { remindLabel(it) to it })
                DropField(remindLabel(draft.remindBefore), options, Modifier.fillMaxWidth()) {
                    update(draft.copy(remindBefore = it))
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }

    if (askDiscard) {
        AlertDialog(
            onDismissRequest = { askDiscard = false },
            containerColor = p.surface,
            title = { Text("Не сохранять правки?") },
            confirmButton = { TextButton(onClick = { askDiscard = false; vm.draft = null }) { Text("Не сохранять") } },
            dismissButton = { TextButton(onClick = { askDiscard = false }) { Text("Вернуться") } },
        )
    }
}

/** Дата (календарь) и время (часы) + «Сегодня / Завтра / Через неделю / Без срока». */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DueFields(draft: Draft, update: (Draft) -> Unit) {
    val p = P
    val due = parseDue(draft.dueAt)
    var pickDate by remember { mutableStateOf(false) }
    var pickTime by remember { mutableStateOf(false) }
    fun setDate(date: LocalDate) {
        val time = due?.toLocalTime() ?: DEFAULT_TIME
        update(draft.copy(dueAt = LocalDateTime.of(date, time).format(DUE_FORMAT)))
    }
    val box = Modifier.height(44.dp).clip(RoundedCornerShape(6.dp)).background(p.surface)
        .border(1.dp, p.border, RoundedCornerShape(6.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(box.weight(1f).clickable { pickDate = true }.padding(horizontal = 12.dp), contentAlignment = Alignment.CenterStart) {
            Text(due?.format(DateTimeFormatter.ofPattern("dd.MM.yyyy")) ?: "Без срока  📅",
                color = if (due == null) p.done else if (due.isBefore(LocalDateTime.now())) p.danger else p.text, fontSize = 16.sp)
        }
        Spacer(Modifier.width(10.dp))
        Text("время", color = p.muted, fontSize = 14.sp)
        Spacer(Modifier.width(8.dp))
        Box(box.width(90.dp).clickable(enabled = due != null) { pickTime = true }.padding(horizontal = 12.dp),
            contentAlignment = Alignment.CenterStart) {
            Text(due?.toLocalTime()?.toString() ?: "—", color = if (due == null) p.done else p.text, fontSize = 16.sp)
        }
    }
    Row(Modifier.padding(top = 4.dp)) {
        LinkText("Сегодня") { setDate(LocalDate.now()) }
        Spacer(Modifier.width(14.dp))
        LinkText("Завтра") { setDate(LocalDate.now().plusDays(1)) }
        Spacer(Modifier.width(14.dp))
        LinkText("Через неделю") { setDate(LocalDate.now().plusDays(7)) }
        Spacer(Modifier.width(14.dp))
        LinkText("Без срока") { update(draft.copy(dueAt = null, remindBefore = null)) }
    }
    if (pickDate) {
        val start = (due?.toLocalDate() ?: LocalDate.now()).atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
        val state = rememberDatePickerState(initialSelectedDateMillis = start)
        DatePickerDialog(
            onDismissRequest = { pickDate = false },
            confirmButton = {
                TextButton(onClick = {
                    pickDate = false
                    state.selectedDateMillis?.let { setDate(Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate()) }
                }) { Text("Готово") }
            },
            dismissButton = { TextButton(onClick = { pickDate = false }) { Text("Отмена") } },
        ) { DatePicker(state = state) }
    }
    if (pickTime && due != null) {
        val state = rememberTimePickerState(due.hour, due.minute, is24Hour = true)
        AlertDialog(
            onDismissRequest = { pickTime = false },
            containerColor = p.surface,
            title = { Text("Время") },
            text = { TimePicker(state = state) },
            confirmButton = {
                TextButton(onClick = {
                    pickTime = false
                    update(draft.copy(dueAt = LocalDateTime.of(due.toLocalDate(), LocalTime.of(state.hour, state.minute))
                        .format(DUE_FORMAT)))
                }) { Text("Готово") }
            },
            dismissButton = { TextButton(onClick = { pickTime = false }) { Text("Отмена") } },
        )
    }
}
