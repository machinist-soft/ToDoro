package com.machinist.todoro

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.FileProvider
import androidx.core.content.pm.PackageInfoCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest

/** Новая версия приложения в последнем выпуске на GitHub. */
data class AppRelease(
    val versionCode: Long,
    val versionName: String,
    val apkUrl: String,
    val apkSha256: String,   // контрольная сумма, которую GitHub даёт для файла выпуска
    val apkSize: Long,
    val page: String,        // страница выпуска — «Что нового»
)

/** Что сейчас с обновлением — для окна «О приложении» и полоски на главном экране. */
sealed class UpdateState {
    data object Idle : UpdateState()
    data object Checking : UpdateState()
    data object UpToDate : UpdateState()
    data class Available(val release: AppRelease) : UpdateState()
    data class Downloading(val release: AppRelease, val progress: Float) : UpdateState()
    data class Ready(val release: AppRelease, val file: File) : UpdateState()
    data class Failed(val message: String, val release: AppRelease? = null) : UpdateState()
}

/**
 * Обновление приложения прямо с телефона. Телефон сам спрашивает у GitHub последний выпуск
 * (компьютер для этого не нужен; никаких данных не отправляется — только «какая версия
 * последняя»). Номер версии берётся из ToDoro-android.json — его кладёт рядом с ToDoro.apk
 * tools/build_apk.py (номера версий на компьютере и в телефоне разные). Скачанный APK
 * сверяется с контрольной суммой SHA-256 от GitHub, а ставит его сам Android — он же
 * проверяет, что APK подписан тем же ключом, что и установленное приложение.
 */
object Updates {
    const val REPO = "machinist-soft/ToDoro"
    const val PROJECT_URL = "https://github.com/$REPO"
    const val RELEASES_URL = "$PROJECT_URL/releases"
    private const val LATEST_URL = "https://api.github.com/repos/$REPO/releases/latest"
    const val VERSION_FILE = "ToDoro-android.json"  // то же имя — в tools/build_apk.py
    const val APK_NAME = "ToDoro.apk"
    private const val PREFS = "updates"
    private const val CHECK_EVERY = 24 * 60 * 60 * 1000L  // сама проверка — не чаще раза в сутки

    var state by mutableStateOf<UpdateState>(UpdateState.Idle)
        private set
    /** Когда последний раз удалось спросить GitHub (0 — ни разу). */
    var checkedAt by mutableStateOf(0L)
        private set
    /** Версия, про которую на главном экране нажали «Не сейчас» — полоску больше не показываем. */
    var dismissedCode by mutableStateOf(0L)
        private set

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun init(context: Context) {
        val p = prefs(context)
        checkedAt = p.getLong("checked_at", 0)
        dismissedCode = p.getLong("dismissed", 0)
    }

    fun versionName(context: Context): String =
        context.packageManager.getPackageInfo(context.packageName, 0).versionName.orEmpty()

    fun versionCode(context: Context): Long =
        PackageInfoCompat.getLongVersionCode(context.packageManager.getPackageInfo(context.packageName, 0))

    /** Открыли приложение: раз в сутки тихо смотрим, нет ли новой версии. */
    fun autoCheck(context: Context) {
        val app = context.applicationContext
        init(app)
        // проверка уже идёт, нашлась новая версия или она скачивается — не мешаем
        if (state != UpdateState.Idle && state != UpdateState.UpToDate) return
        // ничего не скачивается — APK, скачанный в прошлый раз (уже установленный), не нужен
        File(app.cacheDir, "update").deleteRecursively()
        if (System.currentTimeMillis() - checkedAt < CHECK_EVERY) return
        startCheck(app, manual = false)
    }

    /**
     * manual — нажали «Проверить обновления»: тогда и ошибку показываем (сама проверка молчит).
     * Состояние меняется сразу, под замком: двойное нажатие не запустит вторую проверку.
     */
    @Synchronized
    fun startCheck(context: Context, manual: Boolean) {
        val current = state
        if (current is UpdateState.Checking || current is UpdateState.Downloading) return
        state = UpdateState.Checking
        val app = context.applicationContext
        Repo.launch { check(app, manual) }
    }

    private suspend fun check(context: Context, manual: Boolean) {
        state = try {
            val release = fetchLatest()
            checkedAt = System.currentTimeMillis()
            prefs(context).edit().putLong("checked_at", checkedAt).apply()
            if (release != null && release.versionCode > versionCode(context)) {
                UpdateState.Available(release)
            } else {
                UpdateState.UpToDate
            }
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            if (manual) UpdateState.Failed(problem(e)) else UpdateState.Idle
        }
    }

    fun dismiss(context: Context, release: AppRelease) {
        dismissedCode = release.versionCode
        prefs(context).edit().putLong("dismissed", release.versionCode).apply()
    }

    private fun problem(e: Exception) = when (e) {
        is GitHubBusy -> "GitHub сейчас не отвечает (${e.message}). Попробуйте позже."
        is IOException -> "Не получилось связаться с GitHub. Проверьте, что на телефоне есть интернет."
        else -> e.message ?: "Не получилось проверить обновления."
    }

    /** Последний выпуск: null — в нём нет приложения для телефона (или номера его версии). */
    private suspend fun fetchLatest(): AppRelease? = withContext(Dispatchers.IO) {
        val release = JSONObject(fetchText(LATEST_URL))
        val versionUrl = assetUrl(release, VERSION_FILE) ?: return@withContext null
        parseRelease(release, JSONObject(fetchText(versionUrl)))
    }

    private fun fetchText(url: String): String {
        val conn = open(url)
        try {
            if (conn.responseCode != 200) throw GitHubBusy("ответ ${conn.responseCode}")
            return conn.inputStream.use { it.readBytes().toString(Charsets.UTF_8) }
        } finally {
            conn.disconnect()
        }
    }

    private fun open(url: String): HttpURLConnection {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 10_000
        conn.readTimeout = 30_000
        conn.instanceFollowRedirects = true  // файлы выпуска GitHub отдаёт через переадресацию
        conn.setRequestProperty("User-Agent", "ToDoro-Android")  // без него api.github.com отказывает
        return conn
    }

    /**
     * Скачать APK, сверить контрольную сумму и что это действительно ToDoro новее установленного.
     * Как и startCheck — под замком: вторая загрузка в тот же файл не начнётся.
     */
    @Synchronized
    fun startDownload(context: Context, release: AppRelease) {
        val current = state
        if (current is UpdateState.Checking || current is UpdateState.Downloading) return
        state = UpdateState.Downloading(release, 0f)
        val app = context.applicationContext
        Repo.launch { download(app, release) }
    }

    private suspend fun download(context: Context, release: AppRelease) {
        state = try {
            UpdateState.Ready(release, withContext(Dispatchers.IO) { save(context, release) })
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            when (e) {
                is NotNewer -> UpdateState.Failed(e.message.orEmpty())  // «Проверить ещё раз», а не скачивать снова
                is GitHubBusy -> UpdateState.Failed("GitHub сейчас не отдаёт файл (${e.message}). Попробуйте позже.", release)
                is IOException -> UpdateState.Failed(
                    "Не получилось скачать обновление. Проверьте интернет и попробуйте ещё раз.", release)
                else -> UpdateState.Failed(e.message ?: "Не получилось скачать обновление.", release)
            }
        }
    }

    private fun save(context: Context, release: AppRelease): File {
        val dir = File(context.cacheDir, "update").apply { mkdirs() }
        dir.listFiles()?.forEach { it.delete() }  // прежние скачанные версии больше не нужны
        val file = File(dir, APK_NAME)
        val digest = MessageDigest.getInstance("SHA-256")
        val conn = open(release.apkUrl)
        try {
            if (conn.responseCode != 200) throw GitHubBusy("ответ ${conn.responseCode}")
            val total = conn.contentLengthLong.takeIf { it > 0 } ?: release.apkSize
            var got = 0L
            var shown = -1
            conn.inputStream.use { input ->
                file.outputStream().use { out ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        out.write(buffer, 0, n)
                        digest.update(buffer, 0, n)
                        got += n
                        val percent = if (total > 0) (got * 100 / total).toInt() else 0
                        if (percent != shown) {  // не перерисовываем экран на каждые 64 КБ
                            shown = percent
                            state = UpdateState.Downloading(release, (percent / 100f).coerceIn(0f, 1f))
                        }
                    }
                }
            }
        } finally {
            conn.disconnect()
        }
        val sum = digest.digest().joinToString("") { "%02x".format(it) }
        if (!sum.equals(release.apkSha256, ignoreCase = true)) {
            file.delete()
            throw IllegalStateException("Скачанный файл повреждён (не совпала контрольная сумма). Попробуйте ещё раз.")
        }
        val info = context.packageManager.getPackageArchiveInfo(file.path, 0)
        if (info == null || info.packageName != context.packageName) {
            file.delete()
            throw IllegalStateException("Скачанный файл — не приложение ToDoro.")
        }
        if (PackageInfoCompat.getLongVersionCode(info) <= versionCode(context)) {
            file.delete()
            throw NotNewer("В скачанном файле нет новой версии — у вас уже последняя.")
        }
        return file
    }

    /** Android 8+ спрашивает разрешение «Установка неизвестных приложений» для ToDoro. */
    fun canInstall(context: Context): Boolean =
        Build.VERSION.SDK_INT < 26 || context.packageManager.canRequestPackageInstalls()

    /** Окно настроек Android, где ToDoro разрешают устанавливать приложения. */
    fun allowInstallIntent(context: Context) =
        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))

    /** Обычное окно Android «Обновить приложение?». */
    fun installIntent(context: Context, file: File): Intent {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
        return Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
    }

    /** Форма «Сообщить об ошибке» на GitHub: версия приложения и телефона подставлены заранее. */
    fun bugReportUrl(context: Context): String {
        fun enc(text: String) = URLEncoder.encode(text, "UTF-8")
        val phone = "Android ${Build.VERSION.RELEASE} (${Build.MANUFACTURER} ${Build.MODEL})"
        return "$PROJECT_URL/issues/new?template=bug_report.yml" +
            "&version=${enc("телефон " + versionName(context))}&windows=${enc(phone)}"
    }
}

/** GitHub ответил не 200 (лимит запросов, нет файла…) — интернет при этом есть. */
private class GitHubBusy(message: String) : IOException(message)

/** Скачанный APK не новее установленного. */
private class NotNewer(message: String) : Exception(message)

/** Ссылка на файл выпуска с таким именем (или null, если его не приложили). */
fun assetUrl(release: JSONObject, name: String): String? {
    val assets = release.optJSONArray("assets") ?: return null
    for (i in 0 until assets.length()) {
        val a = assets.getJSONObject(i)
        if (a.optString("name") == name) return a.optString("browser_download_url").takeIf { it.isNotEmpty() }
    }
    return null
}

/**
 * Ответ GitHub о выпуске + содержимое ToDoro-android.json → новая версия приложения.
 * null — в выпуске нет APK, номера версии или контрольной суммы APK (без неё не ставим).
 */
fun parseRelease(release: JSONObject, version: JSONObject): AppRelease? {
    val code = version.optLong("versionCode", 0).takeIf { it > 0 } ?: return null
    val assets = release.optJSONArray("assets") ?: return null
    for (i in 0 until assets.length()) {
        val a = assets.getJSONObject(i)
        if (a.optString("name") != Updates.APK_NAME) continue
        val url = a.optString("browser_download_url")
        // https — чтобы файл не подменили по дороге; контрольная сумма — «sha256:…»
        if (!url.startsWith("https://")) return null
        val digest = a.optString("digest")
        if (!digest.startsWith("sha256:")) return null
        val sha = digest.removePrefix("sha256:")
        if (!Regex("[0-9a-fA-F]{64}").matches(sha)) return null
        return AppRelease(
            versionCode = code,
            versionName = version.optString("versionName").ifEmpty { code.toString() },
            apkUrl = url,
            apkSha256 = sha.lowercase(),
            apkSize = a.optLong("size"),
            page = release.optString("html_url").ifEmpty { Updates.RELEASES_URL },
        )
    }
    return null
}
