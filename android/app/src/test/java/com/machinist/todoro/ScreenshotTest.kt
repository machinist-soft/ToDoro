package com.machinist.todoro

import android.content.Context
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.work.testing.WorkManagerTestInitHelper
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Снимки экранов приложения без телефона: Robolectric запускает приложение прямо в Java,
 * а оно подключается к настоящему серверу ToDoro (phone.py) с примерами задач.
 *
 * Запуск — из папки проекта: python tools/android_screenshots.py (он поднимает сервер и
 * передаёт адрес и ключ в -Dtodoro.server=http://127.0.0.1:порт,ключ).
 * Снимки — в android/app/build/screens/.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34], qualifiers = "w393dp-h851dp-xxhdpi")
class ScreenshotTest {
    @get:Rule
    val compose = createEmptyComposeRule()

    private fun start() {
        val server = System.getProperty("todoro.server").orEmpty()
        assumeTrue("нет сервера ToDoro (-Dtodoro.server)", server.isNotEmpty())
        val (url, key) = server.split(",")
        val port = url.substringAfterLast(":").toInt()
        val context = ApplicationProvider.getApplicationContext<Context>()
        WorkManagerTestInitHelper.initializeTestWorkManager(context)
        Pairing(listOf("127.0.0.1"), port, key, "ПК").save(context)
        System.getProperty("todoro.list")?.takeIf { it.isNotEmpty() }?.let { list ->
            context.getSharedPreferences("app", Context.MODE_PRIVATE).edit().putString("list", list).commit()
        }
        ActivityScenario.launch(MainActivity::class.java)
        compose.waitUntil(20_000) { Repo.data != null }
        compose.waitForIdle()
    }

    private fun shot(name: String) {
        compose.waitForIdle()
        compose.onRoot().captureRoboImage("build/screens/$name.png")
    }

    @Test
    fun screens() {
        start()
        shot("1-main")
        compose.onNode(hasText("Сдать квартальный отчёт")).performClick()
        shot("2-card")
        compose.onNode(hasText("✎  Изменить")).performClick()
        shot("3-form")
    }

    @Test
    @Config(qualifiers = "w393dp-h851dp-night-xxhdpi")
    fun dark() {
        start()
        shot("4-dark")
    }
}
