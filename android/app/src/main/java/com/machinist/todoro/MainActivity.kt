package com.machinist.todoro

import android.content.Intent
import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

val Brand = Color(0xFF00978C)       // бирюзовый цвет значка ToDoro
val BrandDark = Color(0xFF2BB8AC)
val Danger = Color(0xFFDC2626)
val Warn = Color(0xFFD97706)

class MainActivity : ComponentActivity() {
    private val vm: AppViewModel by viewModels()

    private val scan = registerForActivityResult(ScanContract()) { result ->
        result.contents?.let { text -> vm.pair(text)?.let { Repo.message = it } }
    }

    // Android 13+: разрешение показывать уведомления (напоминания о сроках)
    private val askNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        Repo.launch { Reminders.update(applicationContext, Repo.data) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Repo.init(this)  // копия задач и очередь правок — с диска, ещё до первого кадра
        enableEdgeToEdge()
        setContent {
            ToDoroTheme {
                if (Repo.pairing == null) PairScreen(vm, ::startScan) else MainScreen(vm, ::startScan)
            }
        }
        if (savedInstanceState == null) handle(intent)
        Reminders.createChannels(this)
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(
                this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        // Пока приложение на экране — раз в 15 секунд смотрим, не изменилось ли что-то на компьютере
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                while (true) {
                    Repo.sync()
                    delay(15_000)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    private fun handle(intent: Intent?) {
        pairFrom(intent)
        // нажали на напоминание — открываем задачу
        val list = intent?.getStringExtra("open_list") ?: return
        vm.openTask(list, intent.getLongExtra("open_task", 0))
    }

    /** Открыли ссылку todoro://connect?... (QR-код отсканировали камерой телефона). */
    private fun pairFrom(intent: Intent?) {
        val link = intent?.takeIf { it.action == Intent.ACTION_VIEW }?.dataString ?: return
        vm.pair(link)?.let { Repo.message = it }
    }

    private fun startScan() {
        scan.launch(
            ScanOptions()
                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .setPrompt("Наведите камеру на QR-код в ToDoro на компьютере")
                .setBeepEnabled(false)
                .setOrientationLocked(false)
        )
    }
}

@Composable
fun ToDoroTheme(content: @Composable () -> Unit) {
    val scheme = if (isSystemInDarkTheme()) {
        darkColorScheme(primary = BrandDark, secondary = BrandDark, error = Color(0xFFF87171))
    } else {
        lightColorScheme(primary = Brand, secondary = Brand, error = Danger,
            background = Color(0xFFF4F6FB), surface = Color(0xFFF4F6FB))
    }
    MaterialTheme(colorScheme = scheme, content = content)
}

// ---------- первое знакомство: подключение по QR-коду ----------

@Composable
fun PairScreen(vm: AppViewModel, onScan: () -> Unit) {
    val snackbar = remember { SnackbarHostState() }
    MessageEffect(vm, snackbar)
    Scaffold(snackbarHost = { SnackbarHost(snackbar) }) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(28.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Image(painterResource(R.mipmap.ic_launcher), null, Modifier.size(96.dp))
            Spacer(Modifier.height(16.dp))
            Text("ToDoro", fontSize = 30.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(20.dp))
            Text(
                "Задачи живут на вашем компьютере в программе ToDoro — телефон берёт их оттуда.\n\n" +
                    "1. На компьютере откройте ☰ Меню → Подключить телефон.\n" +
                    "2. Нажмите «Включить связь с телефоном».\n" +
                    "3. Здесь нажмите кнопку ниже и наведите камеру на QR-код.\n\n" +
                    "Телефон должен быть в домашнем Wi-Fi или подключён к VPN.",
                style = MaterialTheme.typography.bodyLarge,
            )
            Spacer(Modifier.height(28.dp))
            Button(onClick = onScan, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                Text("Сканировать QR-код", fontSize = 17.sp)
            }
        }
    }
}

@Composable
fun MessageEffect(vm: AppViewModel, snackbar: SnackbarHostState) {
    LaunchedEffect(Repo.message) {
        Repo.message?.let {
            Repo.message = null
            snackbar.showSnackbar(it)
        }
    }
}

// ---------- главный экран: список задач ----------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(vm: AppViewModel, onScan: () -> Unit) {
    val draft = vm.draft
    val view = vm.view
    if (draft != null && view != null) {
        TaskScreen(vm, draft, view)
        return
    }
    val snackbar = remember { SnackbarHostState() }
    MessageEffect(vm, snackbar)
    var confirmUnpair by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { ListPicker(vm) },
                actions = {
                    IconButton(onClick = { vm.refresh() }) { Icon(Icons.Default.Refresh, "Обновить") }
                    var menu by remember { mutableStateOf(false) }
                    IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, "Меню") }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        DropdownMenuItem(
                            text = { Text("Напоминания на телефоне") },
                            trailingIcon = { Checkbox(checked = vm.remindersOn, onCheckedChange = null) },
                            onClick = { vm.setReminders(!vm.remindersOn) })
                        DropdownMenuItem(
                            text = { Text("Подключить заново (QR-код)") },
                            onClick = { menu = false; onScan() })
                        DropdownMenuItem(
                            text = { Text("Отключиться от компьютера") },
                            onClick = { menu = false; confirmUnpair = true })
                    }
                },
            )
        },
        floatingActionButton = {
            if (view != null) {
                FloatingActionButton(onClick = { vm.openTask(null) }) { Icon(Icons.Default.Add, "Новая задача") }
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = Repo.syncing && Repo.data == null,
            onRefresh = { vm.refresh() },
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 12.dp, end = 12.dp, bottom = 96.dp),
            ) {
                if (Repo.keyRejected) {
                    item {
                        Banner("Компьютер больше не принимает этот телефон: связь отключили или " +
                            "сделали новый ключ. Подключите телефон заново.", "Сканировать QR-код", onScan)
                    }
                } else Repo.problem?.let { text ->
                    item { Banner(offlineText(text), "Повторить", { vm.refresh() }, warn = Repo.data != null) }
                }
                if (Repo.pendingCount > 0 && Repo.problem == null && !Repo.keyRejected) {
                    item { Text("Отправляю правки на компьютер…", Modifier.padding(6.dp), fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
                if (view != null) {
                    if (Repo.data?.sharedOffline == true) {
                        item {
                            Banner("Компьютер сейчас не видит общую папку. Общие списки — " +
                                "в том виде, как были при последней связи; правки в них уйдут позже.",
                                null, null, warn = true)
                        }
                    }
                    item { Filters(vm, view) }
                    val tasks = vm.visibleTasks()
                    if (tasks.isEmpty()) {
                        item {
                            Text(
                                when (vm.filter) {
                                    Filter.ACTIVE -> "Всё сделано! Новая задача — кнопка «+»."
                                    Filter.DONE -> "Выполненных задач пока нет."
                                    Filter.ALL -> "Задач пока нет. Новая задача — кнопка «+»."
                                },
                                Modifier.fillMaxWidth().padding(32.dp),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    items(tasks, key = { it.id }) { task -> TaskRow(vm, view, task) }
                } else if (Repo.problem == null && !Repo.keyRejected) {
                    item {
                        Text("Загружаю задачи…", Modifier.padding(32.dp),
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }

    Repo.conflict?.let { c ->
        val who = c.current.updatedBy ?: "кто-то на компьютере"
        val whenText = c.current.updatedAt?.let { " (${showStamp(it)})" }.orEmpty()
        AlertDialog(
            onDismissRequest = {},
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
            title = { Text("Отключиться?") },
            text = { Text("Телефон забудет компьютер. Задачи на компьютере останутся. " +
                "Подключиться снова можно по QR-коду.") },
            confirmButton = { TextButton(onClick = { confirmUnpair = false; vm.unpair() }) { Text("Отключиться") } },
            dismissButton = { TextButton(onClick = { confirmUnpair = false }) { Text("Отмена") } },
        )
    }
}

/** «Нет связи…» + когда последний раз видели компьютер и сколько правок ждёт отправки. */
fun offlineText(problem: String): String {
    val data = Repo.data ?: return problem
    val parts = mutableListOf(problem)
    if (data.syncedAt > 0) {
        val time = java.time.Instant.ofEpochMilli(data.syncedAt).atZone(java.time.ZoneId.systemDefault())
            .toLocalDateTime()
        parts += "Задачи — как были на ${showDue(time)}."
    }
    if (Repo.pendingCount > 0) {
        parts += "Правок ждут отправки: ${Repo.pendingCount} — уйдут, когда связь появится."
    } else {
        parts += "Можно работать: правки уйдут на компьютер, когда связь появится."
    }
    return parts.joinToString(" ")
}

@Composable
fun ListPicker(vm: AppViewModel) {
    var open by remember { mutableStateOf(false) }
    val current = vm.lists.firstOrNull { it.id == vm.listId } ?: vm.view?.list
    Box {
        Row(
            Modifier.clip(RoundedCornerShape(8.dp)).clickable { open = true }.padding(4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(current?.name ?: "ToDoro", maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (current?.shared == true) {
                    Text("общий список", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Icon(Icons.Default.ArrowDropDown, "Выбрать список")
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            val sharedOffline = Repo.data?.sharedOffline == true
            val personal = vm.lists.filter { !it.shared }
            val shared = vm.lists.filter { it.shared }
            personal.forEach { item ->
                DropdownMenuItem(text = { Text(item.name) }, onClick = { open = false; vm.selectList(item.id) })
            }
            if (shared.isNotEmpty() || sharedOffline) {
                HorizontalDivider()
                Text("Общие списки", Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                    fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            shared.forEach { item ->
                DropdownMenuItem(text = { Text(item.name) }, onClick = { open = false; vm.selectList(item.id) })
            }
            if (sharedOffline && shared.isEmpty()) {
                DropdownMenuItem(text = { Text("недоступны — нет связи с общей папкой") },
                    onClick = {}, enabled = false)
            }
        }
    }
}

@Composable
fun Banner(text: String, action: String?, onAction: (() -> Unit)?, warn: Boolean = false) {
    Card(
        Modifier.fillMaxWidth().padding(vertical = 6.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (warn) Warn.copy(alpha = 0.15f) else Danger.copy(alpha = 0.12f)),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(text)
            if (action != null && onAction != null) {
                TextButton(onClick = onAction, modifier = Modifier.align(Alignment.End)) { Text(action) }
            }
        }
    }
}

@Composable
fun Filters(vm: AppViewModel, view: ListView) {
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Filter.entries.forEach { f ->
            val count = when (f) {
                Filter.ACTIVE -> view.tasks.count { !it.done }
                Filter.DONE -> view.tasks.count { it.done }
                Filter.ALL -> view.tasks.size
            }
            FilterChip(selected = vm.filter == f, onClick = { vm.filter = f }, label = { Text("${f.label}  $count") })
        }
        if (view.list.shared) {
            FilterChip(selected = vm.onlyMine, onClick = { vm.onlyMine = !vm.onlyMine }, label = { Text("Мои") })
        }
    }
}

@Composable
fun TaskRow(vm: AppViewModel, view: ListView, task: Task) {
    val status = view.statuses.firstOrNull { it.id == task.statusId }
    Card(
        Modifier.fillMaxWidth().padding(vertical = 4.dp).clickable { vm.openTask(task) },
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest),
    ) {
        Row(Modifier.padding(start = 4.dp, end = 14.dp, top = 6.dp, bottom = 8.dp),
            verticalAlignment = Alignment.Top) {
            Checkbox(checked = task.done, onCheckedChange = { vm.toggleDone(task) })
            Column(Modifier.weight(1f).padding(top = 10.dp)) {
                Text(
                    task.title,
                    style = MaterialTheme.typography.bodyLarge,
                    textDecoration = if (task.done) TextDecoration.LineThrough else null,
                    color = if (task.done) MaterialTheme.colorScheme.onSurfaceVariant else Color.Unspecified,
                )
                val parts = mutableListOf<@Composable () -> Unit>()
                task.due?.let { due ->
                    parts += {
                        Text((if (task.overdue) "просрочено · " else "до ") + showDue(due), fontSize = 13.sp,
                            color = if (task.overdue) Danger else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                if (task.urgent && !task.done) parts += { Tag("Срочно", Danger) }
                if (task.important && !task.done) parts += { Tag("Важно", Warn) }
                if (view.list.shared && task.assignee != null) {
                    parts += { Text("→ ${task.assignee}", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
                if (status != null && !task.done) {
                    parts += {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(8.dp).clip(CircleShape).background(Color(status.color)))
                            Spacer(Modifier.width(4.dp))
                            Text(status.name, fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                if (task.files + task.comments > 0) {
                    parts += {
                        Text(listOfNotNull(
                            if (task.files > 0) "📎${task.files}" else null,
                            if (task.comments > 0) "💬${task.comments}" else null,
                        ).joinToString(" "), fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                if ((view.list.id to task.id) in Repo.pendingTasks) {
                    parts += { Text("⏳ ждёт отправки", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
                if (parts.isNotEmpty()) {
                    Row(Modifier.padding(top = 4.dp).horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        parts.forEach { it() }
                    }
                }
            }
        }
    }
}

@Composable
fun Tag(text: String, color: Color) {
    Text(text, fontSize = 12.sp, color = color, fontWeight = FontWeight.Medium,
        modifier = Modifier.clip(RoundedCornerShape(6.dp)).background(color.copy(alpha = 0.12f))
            .padding(horizontal = 6.dp, vertical = 1.dp))
}

@Composable
fun ConfirmBack(enabled: Boolean, onBack: () -> Unit) {
    BackHandler(enabled = enabled, onBack = onBack)
}
