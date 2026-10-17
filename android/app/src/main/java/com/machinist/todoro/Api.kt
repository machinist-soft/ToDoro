package com.machinist.todoro

import android.content.Context
import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** Что зашито в QR-код в окне ToDoro «Подключить телефон»: адреса компьютера, порт и ключ. */
data class Pairing(val hosts: List<String>, val port: Int, val key: String, val name: String) {
    companion object {
        fun parse(text: String): Pairing? {
            val uri = Uri.parse(text.trim())
            if (uri.scheme != "todoro" || uri.host != "connect") return null
            val hosts = uri.getQueryParameter("hosts")?.split(",")
                ?.map { it.trim() }?.filter { it.isNotEmpty() }.orEmpty()
            val port = uri.getQueryParameter("port")?.toIntOrNull() ?: return null
            val key = uri.getQueryParameter("key")?.takeIf { it.isNotEmpty() } ?: return null
            if (hosts.isEmpty()) return null
            return Pairing(hosts, port, key, uri.getQueryParameter("name").orEmpty())
        }

        private const val PREFS = "pairing"

        fun load(context: Context): Pairing? {
            val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            val key = p.getString("key", null) ?: return null
            val hosts = p.getString("hosts", "").orEmpty().split(",").filter { it.isNotEmpty() }
            if (hosts.isEmpty()) return null
            return Pairing(hosts, p.getInt("port", 0), key, p.getString("name", "").orEmpty())
        }

        fun clear(context: Context) {
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().apply()
        }
    }

    fun save(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString("hosts", hosts.joinToString(","))
            .putInt("port", port)
            .putString("key", key)
            .putString("name", name)
            .apply()
    }
}

/** Компьютер ответил ошибкой (неверный ключ, задачу уже изменили, нет такой задачи…). */
class ApiException(val status: Int, message: String, val body: JSONObject?) : Exception(message)

/** До компьютера не достучаться ни по одному адресу. */
class OfflineException(message: String) : Exception(message)

/**
 * Запросы к значку ToDoro в трее (phone.py). У компьютера может быть несколько адресов
 * (Wi-Fi дома, VPN) — пробуем по очереди, начиная с того, что сработал в прошлый раз.
 * На другой адрес переходим, только если не удалось даже соединиться: иначе запрос мог
 * уже выполниться, и повтор добавил бы задачу дважды.
 */
class Api(private val pairing: Pairing) {
    @Volatile
    private var host: String = pairing.hosts.first()

    suspend fun get(path: String) = call("GET", path, null)
    suspend fun post(path: String, json: JSONObject) = call("POST", path, json)
    suspend fun patch(path: String, json: JSONObject) = call("PATCH", path, json)
    suspend fun delete(path: String) = call("DELETE", path, null)

    private suspend fun call(method: String, path: String, json: JSONObject?): JSONObject =
        withContext(Dispatchers.IO) {
            val order = listOf(host) + pairing.hosts.filter { it != host }
            for (candidate in order) {
                val conn = open(candidate, method, path, json != null)
                try {
                    conn.connect()
                } catch (e: IOException) {
                    conn.disconnect()
                    continue  // этот адрес недоступен — пробуем следующий
                }
                host = candidate
                try {
                    if (json != null) conn.outputStream.use { it.write(json.toString().toByteArray()) }
                    return@withContext read(conn)
                } catch (e: IOException) {
                    throw OfflineException(offlineText())
                } finally {
                    conn.disconnect()
                }
            }
            throw OfflineException(offlineText())
        }

    private fun open(host: String, method: String, path: String, hasBody: Boolean): HttpURLConnection {
        val conn = URL("http://$host:${pairing.port}/api/v1$path").openConnection() as HttpURLConnection
        conn.connectTimeout = 4000
        conn.readTimeout = 30000  // общий список: компьютер может ждать сетевую папку
        conn.useCaches = false
        conn.setRequestProperty("Authorization", "Bearer ${pairing.key}")
        if (method == "PATCH") {
            // HttpURLConnection не знает PATCH — сервер понимает подмену через этот заголовок
            conn.requestMethod = "POST"
            conn.setRequestProperty("X-HTTP-Method-Override", "PATCH")
        } else {
            conn.requestMethod = method
        }
        if (hasBody) {
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        return conn
    }

    private fun read(conn: HttpURLConnection): JSONObject {
        val status = conn.responseCode
        val stream = if (status >= 400) conn.errorStream else conn.inputStream
        val text = stream?.use { it.readBytes().toString(Charsets.UTF_8) }.orEmpty()
        val body = try {
            JSONObject(text)
        } catch (e: Exception) {
            null
        }
        if (status >= 400) {
            throw ApiException(status, body?.optString("error")?.takeIf { it.isNotEmpty() }
                ?: "Ошибка $status", body)
        }
        return body ?: JSONObject()
    }

    private fun offlineText(): String {
        val pc = if (pairing.name.isNotEmpty()) "«${pairing.name}»" else "с ToDoro"
        return "Нет связи с компьютером $pc. Проверьте, что телефон в домашнем Wi-Fi или " +
            "подключён к VPN, а компьютер включён."
    }

    companion object {
        fun listPath(listId: String) = "/lists/" + URLEncoder.encode(listId, "UTF-8")
    }
}
