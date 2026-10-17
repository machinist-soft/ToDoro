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
import com.github.takahirom.roborazzi.captureScreenRoboImage
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
        val prefs = context.getSharedPreferences("app", Context.MODE_PRIVATE)
        prefs.edit().remove("theme").commit()  // тема, выбранная в chosenTheme, не должна попасть в другие снимки
        System.getProperty("todoro.list")?.takeIf { it.isNotEmpty() }?.let { list ->
            prefs.edit().putString("list", list).commit()
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
        compose.onNode(hasText("Отмена")).performClick()
        compose.onNode(hasText("‹ Назад к списку")).performClick()
        compose.onNode(hasText("Подготовить презентацию для клиента")).performClick()
        compose.onNode(hasText("Комментарии", substring = true)).performClick()
        compose.waitUntil(10_000) { Repo.data != null && compose.onAllNodes(hasText("Отправить")).fetchSemanticsNodes().isNotEmpty() }
        shot("5-comments")
    }

    /** Телефон в светлой теме, в приложении выбрана «☰ Меню → Тема → Тёмная». */
    @Test
    fun chosenTheme() {
        start()
        compose.onNode(hasText("☰  Меню")).performClick()
        compose.waitForIdle()
        captureScreenRoboImage("build/screens/6-menu.png")
        compose.onNode(hasText("Тёмная")).performClick()
        shot("7-chosen-dark")
        compose.onNode(hasText("☰  Меню")).performClick()
        compose.onNode(hasText("Как в телефоне")).performClick()
        compose.waitForIdle()
    }

    @Test
    @Config(qualifiers = "w393dp-h851dp-night-xxhdpi")
    fun dark() {
        start()
        shot("4-dark")
    }
}
