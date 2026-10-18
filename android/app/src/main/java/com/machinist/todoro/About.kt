package com.machinist.todoro

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Открыть ссылку в браузере телефона. */
fun openLink(context: Context, url: String) {
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    } catch (e: ActivityNotFoundException) {
        Repo.message = "На телефоне нет браузера, чтобы открыть ссылку"
    }
}

/** Окно установщика Android «Обновить приложение?». */
private fun startInstall(context: Context, state: UpdateState.Ready) {
    try {
        context.startActivity(Updates.installIntent(context, state.file))
    } catch (e: ActivityNotFoundException) {
        Repo.message = "Не нашлась программа установки. Скачайте ToDoro.apk со страницы выпуска."
    }
}

/** «О приложении»: версия, компьютер, проверка и установка обновления, ссылки, лицензия. */
@Composable
fun AboutScreen(vm: AppViewModel) {
    val p = P
    val context = LocalContext.current
    val snackbar = remember { SnackbarHostState() }
    MessageEffect(snackbar)
    BackHandler { vm.about = false }
    var explainInstall by remember { mutableStateOf(false) }
    // вернулись из настроек «Установка неизвестных приложений»: разрешили — сразу ставим
    val allow = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        val ready = Updates.state as? UpdateState.Ready
        if (ready != null && Updates.canInstall(context)) startInstall(context, ready)
    }
    fun install(ready: UpdateState.Ready) {
        if (Updates.canInstall(context)) startInstall(context, ready) else explainInstall = true
    }

    Scaffold(containerColor = p.bg, snackbarHost = { SnackbarHost(snackbar) }) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())
                .padding(horizontal = 14.dp, vertical = 10.dp),
        ) {
            LinkText("‹ Назад к списку") { vm.about = false }
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Image(painterResource(R.drawable.totoro_happy), "Тоторо", Modifier.size(width = 64.dp, height = 70.dp))
                Spacer(Modifier.width(12.dp))
                Column {
                    Logo()
                    Text("Список дел, канбан и матрица Эйзенхауэра — с компьютера на телефоне.",
                        color = p.muted, fontSize = 14.sp)
                }
            }
            Spacer(Modifier.height(14.dp))

            Section("Приложение на телефоне")
            Panel {
                Column(Modifier.padding(14.dp)) {
                    Line("Версия", "${Updates.versionName(context)} (сборка ${Updates.versionCode(context)})")
                    Spacer(Modifier.height(8.dp))
                    UpdateBlock(context, ::install)
                }
            }

            Section("Компьютер")
            Panel {
                Column(Modifier.padding(14.dp)) {
                    val pairing = Repo.pairing
                    val data = Repo.data
                    Line("Подключён к", pairing?.name?.takeIf { it.isNotEmpty() }?.let { "«$it»" } ?: "компьютеру с ToDoro")
                    Line("ToDoro на компьютере", data?.pcVersion?.takeIf { it.isNotEmpty() }
                        ?: "станет известно при связи")
                    Line("Последняя связь", data?.syncedAt?.takeIf { it > 0 }?.let { showMillis(it) } ?: "ещё не было")
                    if (Repo.pendingCount > 0) Line("Правок ждут отправки", Repo.pendingCount.toString())
                    Text("Программу на компьютере обновляют там: ☰ Меню → Проверить обновления.",
                        Modifier.padding(top = 6.dp), color = p.muted, fontSize = 13.sp)
                }
            }

            Section("Ссылки")
            Panel {
                Column(Modifier.padding(horizontal = 12.dp, vertical = 6.dp)) {
                    LinkText("Что нового — все выпуски") { openLink(context, Updates.RELEASES_URL) }
                    LinkText("Сообщить об ошибке или предложить улучшение") {
                        openLink(context, Updates.bugReportUrl(context))
                    }
                    LinkText("Страница проекта на GitHub") { openLink(context, Updates.PROJECT_URL) }
                }
            }

            Spacer(Modifier.height(16.dp))
            Text("© 2026 Machinist. Код — по лицензии MIT.", color = p.muted, fontSize = 13.sp)
            Spacer(Modifier.height(4.dp))
            Text("Тоторо и Котобус — персонажи студии Ghibli (© Studio Ghibli); их рисунки здесь — " +
                "любительские, из любви к фильму. Приложение не связано со студией Ghibli, " +
                "лицензия MIT на персонажей не распространяется.", color = p.muted, fontSize = 12.sp)
            Spacer(Modifier.height(24.dp))
        }
    }

    if (explainInstall) {
        AlertDialog(
            onDismissRequest = { explainInstall = false },
            containerColor = p.surface,
            title = { Text("Нужно одно разрешение") },
            text = {
                Text("Чтобы ToDoro могло обновлять само себя, Android попросит разрешение. " +
                    "В открывшемся окне включите «Разрешить установку из этого источника» и " +
                    "нажмите «Назад» — обновление начнётся. Спрашивается только один раз.")
            },
            confirmButton = {
                TextButton(onClick = {
                    explainInstall = false
                    try {
                        allow.launch(Updates.allowInstallIntent(context))
                    } catch (e: ActivityNotFoundException) {
                        Repo.message = "Откройте настройки Android → Приложения → ToDoro → Установка неизвестных приложений."
                    }
                }) { Text("Открыть настройки") }
            },
            dismissButton = { TextButton(onClick = { explainInstall = false }) { Text("Отмена") } },
        )
    }
}

/** Проверка обновления: кнопка, что нашли, ход скачивания, «Установить». */
@Composable
private fun UpdateBlock(context: Context, install: (UpdateState.Ready) -> Unit) {
    val p = P
    fun check() {
        Updates.startCheck(context, manual = true)
    }
    when (val s = Updates.state) {
        UpdateState.Checking -> Text("Проверяю, нет ли новой версии…", color = p.muted, fontSize = 14.sp)
        is UpdateState.Available -> {
            Text("Вышла новая версия ${s.release.versionName}.", color = p.text, fontSize = 15.sp,
                fontWeight = FontWeight.Medium)
            LinkText("Что нового в этой версии") { openLink(context, s.release.page) }
            Spacer(Modifier.height(6.dp))
            FlatButton("Скачать и установить", { Updates.startDownload(context, s.release) },
                Modifier.fillMaxWidth(), look = Look.ACCENT)
            Text("Задачи и подключение к компьютеру при обновлении сохранятся.",
                Modifier.padding(top = 6.dp), color = p.muted, fontSize = 13.sp)
        }
        is UpdateState.Downloading -> {
            Text("Скачиваю версию ${s.release.versionName}… ${(s.progress * 100).toInt()}%", color = p.text, fontSize = 14.sp)
            Spacer(Modifier.height(6.dp))
            LinearProgressIndicator(progress = { s.progress }, Modifier.fillMaxWidth(), color = p.accent)
        }
        is UpdateState.Ready -> {
            Text("Версия ${s.release.versionName} скачана и проверена.", color = p.text, fontSize = 15.sp,
                fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(6.dp))
            FlatButton("Установить", { install(s) }, Modifier.fillMaxWidth(), look = Look.ACCENT)
        }
        is UpdateState.Failed -> {
            Text(s.message, color = p.danger, fontSize = 14.sp)
            Spacer(Modifier.height(6.dp))
            val release = s.release
            if (release != null) {
                FlatButton("Скачать ещё раз", { Updates.startDownload(context, release) }, Modifier.fillMaxWidth())
            } else {
                FlatButton("Проверить ещё раз", ::check, Modifier.fillMaxWidth())
            }
        }
        UpdateState.Idle, UpdateState.UpToDate -> {
            if (s == UpdateState.UpToDate) {
                Text("У вас последняя версия.", color = p.text, fontSize = 14.sp)
                Spacer(Modifier.height(6.dp))
            }
            FlatButton("Проверить обновления", ::check, Modifier.fillMaxWidth())
        }
    }
    if (Updates.checkedAt > 0 && Updates.state !is UpdateState.Downloading) {
        Text("Последняя проверка: ${showMillis(Updates.checkedAt)}", Modifier.padding(top = 6.dp),
            color = p.muted, fontSize = 12.sp)
    }
}

@Composable
private fun Section(title: String) {
    Text(title, Modifier.padding(top = 14.dp, bottom = 6.dp, start = 2.dp), color = P.muted, fontSize = 13.sp,
        fontWeight = FontWeight.Medium)
}

@Composable
private fun Line(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(label, Modifier.weight(1f), color = P.muted, fontSize = 14.sp)
        Spacer(Modifier.width(10.dp))
        Text(value, Modifier.weight(1.3f), color = P.text, fontSize = 14.sp)
    }
}

/** Время в миллисекундах → «сегодня 14:05» / «12 окт 09:30», как сроки задач. */
fun showMillis(millis: Long): String = showDue(
    java.time.Instant.ofEpochMilli(millis).atZone(java.time.ZoneId.systemDefault()).toLocalDateTime(),
)
