package com.machinist.todoro

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import java.util.concurrent.TimeUnit

/**
 * Фоновая синхронизация с компьютером, когда приложение закрыто:
 * раз в 15 минут — забрать свежие задачи (для напоминаний); и сразу, как появится сеть, —
 * отправить правки, сделанные без связи (если компьютер недоступен — попробует позже).
 */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        Repo.init(applicationContext)
        if (Repo.pairing == null) return Result.success()
        val ok = Repo.sync()
        val flush = inputData.getBoolean("flush", false)
        return if (flush && !ok && !Repo.keyRejected) Result.retry() else Result.success()
    }

    companion object {
        private val network = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        fun schedulePeriodic(context: Context) {
            val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(network)
                .build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork("sync", ExistingPeriodicWorkPolicy.KEEP, request)
        }

        fun scheduleFlush(context: Context) {
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(network)
                .setInputData(workDataOf("flush" to true))
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork("flush", ExistingWorkPolicy.KEEP, request)
        }
    }
}
