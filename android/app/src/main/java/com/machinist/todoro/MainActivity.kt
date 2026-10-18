package com.machinist.todoro

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.Image
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

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
            val dark = when (vm.theme) {
                ThemeMode.LIGHT -> false
                ThemeMode.DARK -> true
                ThemeMode.SYSTEM -> isSystemInDarkTheme()
            }
            // Значки строки состояния — тёмные на светлой теме и светлые на тёмной, даже если
            // тема выбрана в приложении, а не в телефоне
            DisposableEffect(dark) {
                enableEdgeToEdge(
                    statusBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT) { dark },
                    navigationBarStyle = SystemBarStyle.auto(Color.argb(0xe6, 0xFF, 0xFF, 0xFF), Color.argb(0x80, 0x1b, 0x1b, 0x1b)) { dark },
                )
                onDispose {}
            }
            ToDoroTheme(dark) {
                if (Repo.pairing == null) PairScreen(::startScan) else MainScreen(vm, ::startScan)
                PairingDialog(vm)
            }
        }
        if (savedInstanceState == null) handle(intent)
        Reminders.createChannels(this)
        Updates.autoCheck(this)  // раз в сутки: нет ли новой версии приложения (полоска на главном экране)
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
        // открыли ссылку todoro://connect?... (QR-код отсканировали камерой телефона)
        intent?.takeIf { it.action == Intent.ACTION_VIEW }?.dataString?.let { link ->
            vm.pair(link, fromLink = true)?.let { Repo.message = it }
        }
        // нажали на напоминание — открываем задачу
        val list = intent?.getStringExtra("open_list") ?: return
        vm.openTask(list, intent.getLongExtra("open_task", 0))
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

/** Первое знакомство: подключение по QR-коду. */
@Composable
fun PairScreen(onScan: () -> Unit) {
    val p = P
    val snackbar = remember { SnackbarHostState() }
    MessageEffect(snackbar)
    Scaffold(containerColor = p.bg, snackbarHost = { SnackbarHost(snackbar) }) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Logo()
            Spacer(Modifier.height(18.dp))
            Image(painterResource(R.drawable.totoro_happy), "Тоторо", Modifier.size(width = 130.dp, height = 143.dp))
            Spacer(Modifier.height(18.dp))
            Panel {
                Column(Modifier.padding(16.dp)) {
                    Text("Привет! Задачи живут на компьютере в программе ToDoro — телефон берёт их оттуда.",
                        color = p.text, fontSize = 16.sp)
                    Spacer(Modifier.height(10.dp))
                    listOf(
                        "На компьютере откройте ☰ Меню → Подключить телефон.",
                        "Нажмите «2. Подключить телефон».",
                        "Здесь нажмите кнопку ниже и наведите камеру на QR-код.",
                    ).forEachIndexed { i, step ->
                        Text("${i + 1}. $step", color = p.text, fontSize = 15.sp, modifier = Modifier.padding(vertical = 3.dp))
                    }
                    Spacer(Modifier.height(8.dp))
                    Text("Телефон должен быть в домашнем Wi-Fi или подключён к VPN.", color = p.muted, fontSize = 14.sp)
                }
            }
            Spacer(Modifier.height(20.dp))
            FlatButton("Сканировать QR-код", onScan, Modifier.fillMaxWidth(), look = Look.ACCENT, height = 50.dp)
        }
    }
}

/** «Подключиться к компьютеру?» — перед подключением по ссылке или со сменой компьютера. */
@Composable
fun PairingDialog(vm: AppViewModel) {
    val pairing = vm.pendingPairing ?: return
    val p = P
    val pc = if (pairing.name.isNotEmpty()) "«${pairing.name}»" else "с ToDoro"
    val parts = mutableListOf(
        "Компьютер $pc, адрес: ${pairing.hosts.joinToString(", ")}.",
        "Подключайтесь, только если сами отсканировали QR-код в ToDoro на своём компьютере " +
            "(☰ Меню → Подключить телефон). Ссылка с сайта или из письма может вести на чужой компьютер.",
    )
    val old = Repo.pairing
    if (old != null && !Repo.samePc(pairing)) {
        val oldPc = if (old.name.isNotEmpty()) "«${old.name}»" else "с ToDoro"
        parts += "Телефон забудет прежний компьютер $oldPc." + if (Repo.pendingCount > 0)
            " Правки, которые ещё не дошли до него (${Repo.pendingCount}), пропадут." else ""
    }
    AlertDialog(
        onDismissRequest = { vm.answerPairing(false) },
        containerColor = p.surface,
        title = { Text("Подключиться к компьютеру?") },
        text = { Text(parts.joinToString("\n\n")) },
        confirmButton = { TextButton(onClick = { vm.answerPairing(true) }) { Text("Подключить") } },
        dismissButton = { TextButton(onClick = { vm.answerPairing(false) }) { Text("Отмена") } },
    )
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
