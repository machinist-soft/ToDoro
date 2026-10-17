package com.machinist.todoro

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
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
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun MessageEffect(snackbar: SnackbarHostState) {
    LaunchedEffect(Repo.message) {
        Repo.message?.let {
            Repo.message = null
            snackbar.showSnackbar(it)
        }
    }
}

/** Главный экран: как окно ToDoro — шапка, строка новой задачи, фильтры, Тоторо, список. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(vm: AppViewModel, onScan: () -> Unit) {
    val view = vm.view
    val draft = vm.draft
    if (draft != null && view != null) {
        TaskForm(vm, draft, view)
        return
    }
    val card = vm.card()
    if (card != null && view != null) {
        TaskCard(vm, card, view)
        return
    }
    val p = P
    val snackbar = remember { SnackbarHostState() }
    MessageEffect(snackbar)
    var confirmUnpair by remember { mutableStateOf(false) }

    Scaffold(containerColor = p.bg, snackbarHost = { SnackbarHost(snackbar) }) { padding ->
        PullToRefreshBox(
            isRefreshing = Repo.syncing && Repo.data == null,
            onRefresh = { vm.refresh() },
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 14.dp, end = 14.dp, bottom = 32.dp)) {
                item { Header(vm, onScan) { confirmUnpair = true } }
                item { ListRow(vm, view) }
                if (Repo.keyRejected) {
                    item {
                        Strip("Компьютер больше не принимает этот телефон: связь отключили или сделали " +
                            "новый ключ. Подключите телефон заново.", "alert", "Сканировать QR-код", onScan)
                    }
                } else Repo.problem?.let { text ->
                    item { Strip(offlineText(text), if (Repo.data != null) "warn" else "alert", "Повторить") { vm.refresh() } }
                }
                if (view != null && Repo.data?.sharedOffline == true) {
                    item {
                        Strip("Компьютер сейчас не видит общую папку. Общие списки — в том виде, как были " +
                            "при последней связи; правки в них уйдут позже.", "warn")
                    }
                }
                if (view == null) {
                    if (Repo.problem == null && !Repo.keyRejected) item { Centered("Загружаю задачи…") }
                    return@LazyColumn
                }
                item { QuickAdd(vm) }
                item { Filters(vm, view) }
                if (vm.buddyOn) vm.buddy()?.let { b -> item { BuddyStrip(vm, b) } }
                val tasks = vm.visibleTasks()
                if (tasks.isEmpty()) {
                    item {
                        Panel {
                            Centered(when (vm.filter) {
                                Filter.ACTIVE -> "Активных задач нет — всё сделано!"
                                Filter.DONE -> "Выполненных задач пока нет."
                                Filter.OVERDUE -> "Просроченных задач нет."
                                Filter.ALL -> "Задач пока нет. Напишите первую в строке выше."
                            })
                        }
                    }
                } else {
                    itemsIndexed(tasks, key = { _, t -> t.id }) { index, task ->
                        TaskRow(vm, view, task, first = index == 0, last = index == tasks.lastIndex)
                    }
                }
                if (Repo.pendingCount > 0 && Repo.problem == null && !Repo.keyRejected) {
                    item { Text("Отправляю правки на компьютер…", Modifier.padding(8.dp), color = p.muted, fontSize = 13.sp) }
                }
            }
        }
    }

    Repo.conflict?.let { c ->
        val who = c.current.updatedBy ?: "кто-то на компьютере"
        val whenText = c.current.updatedAt?.let { " (${showStamp(it)})" }.orEmpty()
        AlertDialog(
            onDismissRequest = {},
            containerColor = p.surface,
            title = { Text("Задачу уже изменили") },
            text = {
                Text("Пока вы правили «${c.op.title}» на телефоне, её изменил $who$whenText.\n\n" +
                    "«Сохранить мой вариант» — ваши правки запишутся поверх.\n" +
                    "«Оставить их вариант» — ваши правки не сохранятся.")
            },
            confirmButton = { TextButton(onClick = { Repo.resolve(c, mine = true) }) { Text("Сохранить мой вариант") } },
            dismissButton = { TextButton(onClick = { Repo.resolve(c, mine = false) }) { Text("Оставить их вариант") } },
        )
    }
    if (confirmUnpair) {
        AlertDialog(
            onDismissRequest = { confirmUnpair = false },
            containerColor = p.surface,
            title = { Text("Отключиться?") },
            text = { Text("Телефон забудет компьютер. Задачи на компьютере останутся. Подключиться снова можно по QR-коду.") },
            confirmButton = { TextButton(onClick = { confirmUnpair = false; vm.unpair() }) { Text("Отключиться") } },
            dismissButton = { TextButton(onClick = { confirmUnpair = false }) { Text("Отмена") } },
        )
    }
}

/** Логотип и «ToDoro» слева, «☰ Меню» справа — как в шапке окна. */
@Composable
fun Header(vm: AppViewModel, onScan: () -> Unit, onUnpair: () -> Unit) {
    val p = P
    Row(Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Logo()
        Spacer(Modifier.weight(1f))
        Box {
            var menu by remember { mutableStateOf(false) }
            FlatButton("☰  Меню", { menu = true }, height = 40.dp)
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }, containerColor = p.surface) {
                DropdownMenuItem(text = { Text("Обновить") }, onClick = { menu = false; vm.refresh() })
                DropdownMenuItem(text = { Text("Напоминания на телефоне") },
                    trailingIcon = { Checkbox(checked = vm.remindersOn, onCheckedChange = null) },
                    onClick = { vm.setReminders(!vm.remindersOn) })
                DropdownMenuItem(text = { Text("Тоторо-помощник") },
                    trailingIcon = { Checkbox(checked = vm.buddyOn, onCheckedChange = null) },
                    onClick = { vm.setBuddy(!vm.buddyOn) })
                HorizontalDivider(color = p.border)
                DropdownMenuItem(text = { Text("Подключить заново (QR-код)") }, onClick = { menu = false; onScan() })
                DropdownMenuItem(text = { Text("Отключиться от компьютера") }, onClick = { menu = false; onUnpair() })
            }
        }
    }
}

@Composable
fun Logo() {
    val p = P
    Row(verticalAlignment = Alignment.CenterVertically) {
        Image(painterResource(R.mipmap.ic_launcher), null, Modifier.size(32.dp))
        Spacer(Modifier.width(8.dp))
        Text("ToDo", color = p.text, fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
        Text("ro", color = p.brand, fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
    }
}

/** «Личный ▾» и счётчики «Активных / Выполнено / Сделано сегодня». */
@Composable
fun ListRow(vm: AppViewModel, view: ListView?) {
    val p = P
    var open by remember { mutableStateOf(false) }
    val current = vm.lists.firstOrNull { it.id == vm.listId } ?: view?.list
    HScroll {
        Box {
            val name = (current?.name ?: "ToDoro") + if (current?.shared == true) "  · общий" else ""
            FlatButton("$name  ▾", { open = true }, height = 38.dp)
            DropdownMenu(expanded = open, onDismissRequest = { open = false }, containerColor = p.surface) {
                val sharedOffline = Repo.data?.sharedOffline == true
                val personal = vm.lists.filter { !it.shared }
                val shared = vm.lists.filter { it.shared }
                personal.forEach { item ->
                    DropdownMenuItem(text = { Text(item.name) }, onClick = { open = false; vm.selectList(item.id) })
                }
                if (shared.isNotEmpty() || sharedOffline) {
                    HorizontalDivider(color = p.border)
                    Text("Общие списки", Modifier.padding(horizontal = 12.dp, vertical = 6.dp), fontSize = 12.sp, color = p.muted)
                }
                shared.forEach { item ->
                    DropdownMenuItem(text = { Text(item.name) }, onClick = { open = false; vm.selectList(item.id) })
                }
                if (sharedOffline && shared.isEmpty()) {
                    DropdownMenuItem(text = { Text("недоступны — нет связи с общей папкой") }, onClick = {}, enabled = false)
                }
            }
        }
        if (view != null) {
            val active = view.tasks.count { !it.done }
            Chip("Активных  $active")
            Chip("Выполнено  ${view.tasks.size - active}")
            Chip("✔ Сделано сегодня  ${view.tasks.count { it.doneToday }}", good = true)
        }
    }
    Spacer(Modifier.height(8.dp))
}

/** «Заголовок новой задачи…» + «＋ Добавить» — как строка вверху окна. */
@Composable
fun QuickAdd(vm: AppViewModel) {
    var text by rememberSaveable { mutableStateOf("") }
    fun add() {
        if (vm.quickAdd(text)) text = ""
    }
    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Field(text, { text = it }, Modifier.weight(1f), placeholder = "Заголовок новой задачи…", onDone = ::add)
        Spacer(Modifier.width(8.dp))
        FlatButton("＋ Добавить", ::add, look = Look.ACCENT)
    }
    Row(Modifier.padding(top = 2.dp, bottom = 6.dp)) {
        LinkText("Подробнее: срок, описание, приоритет…") { vm.openTask(null) }
    }
}

@Composable
fun Filters(vm: AppViewModel, view: ListView) {
    HScroll {
        val overdue = view.tasks.count { it.overdue }
        Segmented(
            Filter.entries.map { it to (if (it == Filter.OVERDUE && overdue > 0) "${it.label}  $overdue" else it.label) },
            vm.filter,
        ) { vm.filter = it }
        if (view.list.shared) {
            Segmented(listOf(true to "Мои задачи"), if (vm.onlyMine) true else null) { vm.onlyMine = !vm.onlyMine }
        }
    }
    Spacer(Modifier.height(10.dp))
}

/** Тоторо-помощник: картинка по настроению и облачко с подсказкой, как в правой панели окна. */
@Composable
fun BuddyStrip(vm: AppViewModel, b: Buddy) {
    val p = P
    val alert = b.mood == "alert"
    Row(Modifier.fillMaxWidth().padding(bottom = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        Image(
            painterResource(when (b.mood) {
                "alert" -> R.drawable.totoro_worried
                "sleep" -> R.drawable.totoro_sleep
                else -> if (b.tasks.isEmpty()) R.drawable.totoro_happy else R.drawable.totoro
            }),
            "Тоторо", Modifier.size(width = 64.dp, height = 70.dp),
        )
        Spacer(Modifier.width(8.dp))
        Column(
            Modifier.weight(1f).clip(RoundedCornerShape(12.dp))
                .background(if (alert) p.alertBg else p.surface)
                .border(1.dp, if (alert) p.alertBorder else p.border, RoundedCornerShape(12.dp))
                .padding(horizontal = 12.dp, vertical = 9.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(b.lead, color = p.muted, fontSize = 13.sp, textAlign = TextAlign.Center)
            b.tasks.forEach { t ->
                Text("«${t.title}»", Modifier.clickable { vm.cardId = t.id }, color = if (alert) p.danger else p.accent,
                    fontSize = 14.sp, fontWeight = FontWeight.Medium, textAlign = TextAlign.Center,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            if (b.tail.isNotEmpty()) Text(b.tail, color = p.text, fontSize = 13.sp, textAlign = TextAlign.Center)
            if (b.stats.isNotEmpty()) Text(b.stats, color = p.muted, fontSize = 12.sp, textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 2.dp))
        }
    }
}

/** Строка задачи — как строка таблицы: точка приоритета, №, заголовок, статус, срок, исполнитель. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TaskRow(vm: AppViewModel, view: ListView, task: Task, first: Boolean, last: Boolean) {
    val p = P
    val shape = RoundedCornerShape(
        topStart = if (first) 8.dp else 0.dp, topEnd = if (first) 8.dp else 0.dp,
        bottomStart = if (last) 8.dp else 0.dp, bottomEnd = if (last) 8.dp else 0.dp,
    )
    val status = view.statuses.firstOrNull { it.id == task.statusId }
    val faded = task.done
    Column(Modifier.fillMaxWidth().clip(shape).background(p.surface)) {
        Row(
            Modifier.fillMaxWidth().clickable { vm.cardId = task.id }.padding(start = 12.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f).padding(vertical = 4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    PriorityDot(task.level)
                    Spacer(Modifier.width(8.dp))
                    Text(
                        task.title, Modifier.weight(1f, fill = false),
                        color = when {
                            faded -> p.done
                            task.overdue -> p.danger
                            else -> p.text
                        },
                        fontSize = 16.sp, maxLines = 2, overflow = TextOverflow.Ellipsis,
                    )
                }
                // строка свойств переносится целиком, а не по буквам, если не помещается
                FlowRow(Modifier.padding(start = 17.dp, top = 3.dp), horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    if (task.id > 0) Text("#${task.id}", color = if (faded) p.done else p.muted, fontSize = 13.sp)
                    StatusMark(task, status)
                    task.due?.let { due ->
                        Text(showDue(due), color = if (task.overdue) p.danger else if (faded) p.done else p.muted,
                            fontSize = 13.sp, maxLines = 1)
                    }
                    if (view.list.shared && task.assignee != null) {
                        Text("→ ${task.assignee}", color = if (faded) p.done else p.muted, fontSize = 13.sp, maxLines = 1)
                    }
                    if (task.files + task.comments > 0) {
                        Text(listOfNotNull(
                            if (task.files > 0) "📎${task.files}" else null,
                            if (task.comments > 0) "💬${task.comments}" else null,
                        ).joinToString(" "), color = p.muted, fontSize = 13.sp)
                    }
                    if ((view.list.id to task.id) in Repo.pendingTasks) Text("⏳", fontSize = 12.sp)
                }
            }
            DoneBox(task.done) { vm.toggleDone(task) }
        }
        if (!last) HorizontalDivider(Modifier.padding(start = 12.dp), color = p.headingLine)
    }
    if (last) Spacer(Modifier.height(4.dp))
}
