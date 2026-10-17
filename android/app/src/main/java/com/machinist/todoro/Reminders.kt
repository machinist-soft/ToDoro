package com.machinist.todoro

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.time.ZoneId

/** Одно напоминание: о какой задаче и когда (миллисекунды). */
data class Reminder(
    val key: String,         // меняется вместе со сроком — после переноса срока напомним снова
    val listId: String,
    val listName: String,
    val taskId: Long,
    val title: String,
    val due: String,
    val at: Long,
)

/**
 * Напоминания о сроках на телефоне — по копии задач (Repo.data), так что работают и без связи.
 * Как на компьютере: в личных списках — обо всех задачах, в общих — только о тех, где вы
 * исполнитель (или автор, если исполнителя нет). Будильники Android заводятся заново после
 * каждой синхронизации; что уже показали — помним, чтобы не напоминать дважды.
 */
object Reminders {
    private const val CHANNEL = "reminders"
    private const val CHANNEL_SYNC = "sync"
    private const val PREFS = "reminders"
    private const val LATE_LIMIT = 60 * 60 * 1000L   // пропущенное (телефон был выключен) — не старше часа
    const val SNOOZE_MINUTES = 15

    fun enabled(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean("enabled", true)

    fun setEnabled(context: Context, on: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean("enabled", on).apply()
        update(context, Repo.data)
    }

    fun due(data: SyncData?): List<Reminder> {
        data ?: return emptyList()
        val zone = ZoneId.systemDefault()
        return data.lists.flatMap { list ->
            val view = data.views[list.id] ?: return@flatMap emptyList()
            view.tasks.mapNotNull { t ->
                val due = t.due ?: return@mapNotNull null
                val before = t.remindBefore ?: return@mapNotNull null
                if (t.done || t.id < 0) return@mapNotNull null
                if (list.shared && (t.assignee ?: t.author) != data.user) return@mapNotNull null
                Reminder("${list.id}|${t.id}|${t.dueAt}|$before", list.id, list.name, t.id, t.title,
                    t.dueAt.orEmpty(), due.minusMinutes(before.toLong()).atZone(zone).toInstant().toEpochMilli())
            }
        }
    }

    /** Заводит будильники на будущие напоминания, снимает лишние, показывает недавно пропущенные. */
    @Synchronized
    fun update(context: Context, data: SyncData?) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val reminders = if (enabled(context)) due(data) else emptyList()
        val now = System.currentTimeMillis()
        val shown = prefs.getStringSet("shown", emptySet())!!.toMutableSet()
        val wanted = reminders.filter { it.key !in shown }
        val alarms = context.getSystemService(AlarmManager::class.java)
        // снимаем будильники, которые больше не нужны (задачу выполнили, срок сменили)
        val scheduled = prefs.getStringSet("scheduled", emptySet())!!
        val future = wanted.filter { it.at > now }
        for (key in scheduled - future.map { it.key }.toSet()) {
            alarms.cancel(alarmIntent(context, key, null))
        }
        for (r in future) {
            val intent = alarmIntent(context, r.key, r)
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S || alarms.canScheduleExactAlarms()) {
                alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, r.at, intent)
            } else {
                alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, r.at, intent)
            }
        }
        // время уже прошло совсем недавно (телефон был выключен или задачу только что добавили)
        for (r in wanted.filter { it.at <= now && now - it.at < LATE_LIMIT }) {
            show(context, r)
            shown += r.key
        }
        // помним только про задачи, которые ещё есть, — список не разрастается
        val keys = due(data).map { it.key }.toSet()
        prefs.edit()
            .putStringSet("scheduled", future.map { it.key }.toSet())
            .putStringSet("shown", shown.intersect(keys))
            .apply()
    }

    fun markShown(context: Context, key: String) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val shown = prefs.getStringSet("shown", emptySet())!!.toMutableSet()
        shown += key
        prefs.edit().putStringSet("shown", shown).apply()
    }

    private fun alarmIntent(context: Context, key: String, r: Reminder?): PendingIntent {
        val intent = Intent(context, ReminderReceiver::class.java).setAction("todoro.REMIND")
            .setData(android.net.Uri.parse("todoro-remind:" + android.net.Uri.encode(key)))
        if (r != null) intent.putExtra("reminder", toJson(r).toString())
        return PendingIntent.getBroadcast(context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    fun snooze(context: Context, r: Reminder) {
        val at = System.currentTimeMillis() + SNOOZE_MINUTES * 60_000L
        val intent = Intent(context, ReminderReceiver::class.java).setAction("todoro.REMIND")
            .setData(android.net.Uri.parse("todoro-snooze:" + android.net.Uri.encode(r.key)))
            .putExtra("reminder", toJson(r).toString())
            .putExtra("snoozed", true)
        val pending = PendingIntent.getBroadcast(context, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val alarms = context.getSystemService(AlarmManager::class.java)
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S || alarms.canScheduleExactAlarms()) {
            alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending)
        } else {
            alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending)
        }
    }

    // --- уведомления ---

    fun createChannels(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "Напоминания о сроках",
            NotificationManager.IMPORTANCE_HIGH).apply { description = "Когда подходит срок задачи" })
        nm.createNotificationChannel(NotificationChannel(CHANNEL_SYNC, "Синхронизация с компьютером",
            NotificationManager.IMPORTANCE_DEFAULT).apply { description = "Если правку не удалось сохранить" })
    }

    private fun canNotify(context: Context) = Build.VERSION.SDK_INT < 33 ||
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
        PackageManager.PERMISSION_GRANTED

    fun notificationId(key: String) = key.hashCode()

    fun show(context: Context, r: Reminder) {
        if (!canNotify(context)) return
        createChannels(context)
        val id = notificationId(r.key)
        val open = PendingIntent.getActivity(context, id,
            Intent(context, MainActivity::class.java)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                .putExtra("open_list", r.listId).putExtra("open_task", r.taskId),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        fun action(name: String) = PendingIntent.getBroadcast(context, id,
            Intent(context, ReminderReceiver::class.java).setAction(name)
                .setData(android.net.Uri.parse("todoro-$name:" + android.net.Uri.encode(r.key)))
                .putExtra("reminder", toJson(r).toString()),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val due = parseDue(r.due)
        val whenText = due?.let { "Срок: ${showDue(it)}" }.orEmpty()
        val notification = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(0xFF00978C.toInt())
            .setContentTitle(r.title)
            .setContentText(listOf(whenText, r.listName).filter { it.isNotEmpty() }.joinToString(" · "))
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(open)
            .setAutoCancel(true)
            .addAction(0, "Выполнено", action("todoro.DONE"))
            .addAction(0, "Через $SNOOZE_MINUTES мин", action("todoro.SNOOZE"))
            .build()
        try {
            NotificationManagerCompat.from(context).notify(id, notification)
        } catch (e: SecurityException) {
            // разрешение на уведомления отозвали
        }
    }

    fun notifyConflict(context: Context, title: String) {
        if (!canNotify(context)) return
        createChannels(context)
        val open = PendingIntent.getActivity(context, 1,
            Intent(context, MainActivity::class.java).setFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(context, CHANNEL_SYNC)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(0xFF00978C.toInt())
            .setContentTitle("Правка не сохранена")
            .setContentText("«$title» изменили на компьютере. Откройте ToDoro и выберите, чей вариант оставить.")
            .setStyle(NotificationCompat.BigTextStyle())
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        try {
            NotificationManagerCompat.from(context).notify(("conflict" + title).hashCode(), notification)
        } catch (e: SecurityException) {
        }
    }

    fun toJson(r: Reminder): JSONObject = JSONObject().put("key", r.key).put("list", r.listId)
        .put("list_name", r.listName).put("task", r.taskId).put("title", r.title)
        .put("due", r.due).put("at", r.at)

    fun fromJson(text: String?): Reminder? = try {
        val o = JSONObject(text!!)
        Reminder(o.getString("key"), o.getString("list"), o.optString("list_name"), o.getLong("task"),
            o.getString("title"), o.optString("due"), o.getLong("at"))
    } catch (e: Exception) {
        null
    }
}

/** Сработал будильник напоминания или нажали кнопку в уведомлении. */
class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        Repo.init(context)
        val r = Reminders.fromJson(intent.getStringExtra("reminder")) ?: return
        when (intent.action) {
            "todoro.REMIND" -> {
                // за это время задачу могли выполнить или перенести — сверяемся с копией
                val still = Reminders.due(Repo.data).any { it.key == r.key }
                if (!Reminders.enabled(context) || !still) return
                Reminders.show(context, r)
                Reminders.markShown(context, r.key)
            }
            "todoro.DONE" -> {
                NotificationManagerCompat.from(context).cancel(Reminders.notificationId(r.key))
                val task = Repo.data?.views?.get(r.listId)?.tasks?.firstOrNull { it.id == r.taskId } ?: return
                val pending = goAsync()  // записать правку, пока Android не закрыл приложение
                Repo.launch {
                    try {
                        Repo.add(Op("patch", r.listId, task.id, JSONObject().put("done", true), null, task.title))
                        SyncWorker.scheduleFlush(context)
                    } finally {
                        pending.finish()
                    }
                }
            }
            "todoro.SNOOZE" -> {
                NotificationManagerCompat.from(context).cancel(Reminders.notificationId(r.key))
                Reminders.snooze(context, r)
            }
        }
    }
}

/** После перезагрузки телефона будильники пропадают — заводим их снова. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        Repo.init(context)
        Reminders.update(context, Repo.data)
    }
}
