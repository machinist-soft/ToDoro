package com.machinist.todoro

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneOffset

/** Форма задачи: новая или правка существующей. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskScreen(vm: AppViewModel, draft: Draft, view: ListView) {
    val snackbar = remember { SnackbarHostState() }
    MessageEffect(vm, snackbar)
    var askDiscard by remember { mutableStateOf(false) }
    var askDelete by remember { mutableStateOf(false) }
    fun update(d: Draft) {
        vm.draft = d
    }
    fun back() {
        if (draft.changed) askDiscard = true else vm.draft = null
    }
    BackHandler { back() }
    val task = draft.task

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (task == null) "Новая задача" else "Задача №${task.id}") },
                navigationIcon = {
                    IconButton(onClick = { back() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад") }
                },
                actions = {
                    if (task != null) {
                        IconButton(onClick = { askDelete = true }) { Icon(Icons.Default.Delete, "Удалить") }
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).imePadding().verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            OutlinedTextField(
                value = draft.title, onValueChange = { update(draft.copy(title = it)) },
                label = { Text("Что сделать") }, modifier = Modifier.fillMaxWidth(),
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
            )
            OutlinedTextField(
                value = draft.body, onValueChange = { update(draft.copy(body = it)) },
                label = { Text("Описание") }, modifier = Modifier.fillMaxWidth(), minLines = 3,
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
            )
            Choice(
                "Статус",
                view.statuses.firstOrNull { it.id == draft.statusId }?.name ?: "—",
                view.statuses.map { it.name to it.id },
            ) { update(draft.copy(statusId = it)) }
            DueField(draft, ::update)
            if (draft.dueAt != null) {
                Choice("Напомнить", remindLabel(draft.remindBefore), REMIND_OPTIONS) {
                    update(draft.copy(remindBefore = it))
                }
            }
            Toggle("Срочно", draft.urgent) { update(draft.copy(urgent = it)) }
            Toggle("Важно", draft.important) { update(draft.copy(important = it)) }
            if (view.list.shared) {
                val people = (view.members + listOfNotNull(draft.assignee)).distinct()
                Choice(
                    "Исполнитель", draft.assignee ?: "не назначен",
                    listOf("не назначен" to null) + people.map { (if (it == view.user) "$it (я)" else it) to it },
                ) { update(draft.copy(assignee = it)) }
            }
            if (task != null) {
                val lines = listOfNotNull(
                    task.author?.let { "Автор: $it" },
                    task.createdAt?.let { "Создана: ${showStamp(it)}" },
                    task.updatedAt?.let { "Изменена: ${showStamp(it)}" + (task.updatedBy?.let { b -> ", $b" } ?: "") },
                    if (task.files + task.comments > 0)
                        "Файлы и комментарии (${task.files} и ${task.comments}) пока видны только на компьютере"
                    else null,
                )
                Text(lines.joinToString("\n"), fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Button(
                onClick = { vm.save(draft) }, enabled = !vm.saving,
                modifier = Modifier.fillMaxWidth().height(50.dp),
            ) { Text(if (vm.saving) "Сохраняю…" else "Сохранить", fontSize = 16.sp) }
            Spacer(Modifier.height(24.dp))
        }
    }

    if (askDiscard) {
        AlertDialog(
            onDismissRequest = { askDiscard = false },
            title = { Text("Не сохранять правки?") },
            confirmButton = { TextButton(onClick = { askDiscard = false; vm.draft = null }) { Text("Не сохранять") } },
            dismissButton = { TextButton(onClick = { askDiscard = false }) { Text("Вернуться") } },
        )
    }
    if (askDelete && task != null) {
        AlertDialog(
            onDismissRequest = { askDelete = false },
            title = { Text("Удалить задачу?") },
            text = { Text("«${task.title}» удалится вместе с файлами и комментариями" +
                if (view.list.shared) " — у всех участников." else ".") },
            confirmButton = {
                TextButton(onClick = { askDelete = false; vm.delete(task) }) { Text("Удалить", color = Danger) }
            },
            dismissButton = { TextButton(onClick = { askDelete = false }) { Text("Отмена") } },
        )
    }
    vm.conflict?.let { c ->
        val who = c.current.updatedBy ?: "кто-то на компьютере"
        val whenText = c.current.updatedAt?.let { " (${showStamp(it)})" }.orEmpty()
        AlertDialog(
            onDismissRequest = {},
            title = { Text("Задачу уже изменили") },
            text = {
                Text("Пока вы правили задачу, её изменил $who$whenText.\n\n" +
                    "«Сохранить мой вариант» — ваши правки запишутся поверх.\n" +
                    "«Оставить их вариант» — ваши правки не сохранятся.")
            },
            confirmButton = { TextButton(onClick = { vm.save(c.draft, over = c.current) }) { Text("Сохранить мой вариант") } },
            dismissButton = { TextButton(onClick = { vm.keepTheirs() }) { Text("Оставить их вариант") } },
        )
    }
}

@Composable
fun <T> Choice(label: String, shown: String, options: List<Pair<String, T>>, onPick: (T) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { open = true }, modifier = Modifier.fillMaxWidth()) {
            Text("$label: ", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(shown, Modifier.weight(1f))
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { (text, value) ->
                DropdownMenuItem(text = { Text(text) }, onClick = { open = false; onPick(value) })
            }
        }
    }
}

@Composable
fun Toggle(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

/** Срок: дата (календарь), потом время (часы). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DueField(draft: Draft, update: (Draft) -> Unit) {
    val due = parseDue(draft.dueAt)
    var pickDate by remember { mutableStateOf(false) }
    var pickedDate by remember { mutableStateOf<LocalDate?>(null) }
    Row(verticalAlignment = Alignment.CenterVertically) {
        OutlinedButton(onClick = { pickDate = true }, modifier = Modifier.weight(1f)) {
            Text("Срок: ", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(due?.let { showDue(it) } ?: "без срока", Modifier.weight(1f),
                color = if (due != null && due.isBefore(LocalDateTime.now())) Danger else Color.Unspecified)
        }
        if (due != null) {
            TextButton(onClick = { update(draft.copy(dueAt = null, remindBefore = null)) }) { Text("Убрать") }
        }
    }
    if (pickDate) {
        val start = (due?.toLocalDate() ?: LocalDate.now()).atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
        val state = rememberDatePickerState(initialSelectedDateMillis = start)
        DatePickerDialog(
            onDismissRequest = { pickDate = false },
            confirmButton = {
                TextButton(onClick = {
                    pickDate = false
                    pickedDate = state.selectedDateMillis?.let {
                        Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate()
                    }
                }) { Text("Дальше") }
            },
            dismissButton = { TextButton(onClick = { pickDate = false }) { Text("Отмена") } },
        ) { DatePicker(state = state) }
    }
    pickedDate?.let { date ->
        val time = due?.toLocalTime() ?: LocalTime.of(9, 0)
        val state = rememberTimePickerState(time.hour, time.minute, is24Hour = true)
        AlertDialog(
            onDismissRequest = { pickedDate = null },
            title = { Text("Время") },
            text = { TimePicker(state = state) },
            confirmButton = {
                TextButton(onClick = {
                    pickedDate = null
                    val value = LocalDateTime.of(date, LocalTime.of(state.hour, state.minute))
                    update(draft.copy(dueAt = value.format(DUE_FORMAT)))
                }) { Text("Готово") }
            },
            dismissButton = { TextButton(onClick = { pickedDate = null }) { Text("Отмена") } },
        )
    }
}
