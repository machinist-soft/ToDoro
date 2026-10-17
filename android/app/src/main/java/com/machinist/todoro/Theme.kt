package com.machinist.todoro

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/** Цвета — те же, что в окне ToDoro на компьютере (PALETTES в todoro.py). */
data class Palette(
    val bg: Color,             // фон окна
    val surface: Color,        // карточки, поля ввода
    val border: Color,
    val text: Color,
    val muted: Color,
    val done: Color,           // выполненные задачи, подсказки
    val accent: Color,
    val accentSoft: Color,     // выделение, мягкая кнопка «Выполнено»
    val danger: Color,
    val dangerSoft: Color,
    val segmentBg: Color,      // подложка переключателей «Все / Активные / …»
    val hover: Color,
    val headingLine: Color,    // линии между строками
    val checkBorder: Color,
    val alertBg: Color, val alertBorder: Color,
    val goodBg: Color, val goodBorder: Color, val goodText: Color,
    val chipBg: Color, val chipGoodBg: Color,
    val warn: Color,
    val brand: Color,          // бирюзовый цвет значка ToDoro
)

val LightPalette = Palette(
    bg = Color(0xFFF4F6FB), surface = Color(0xFFFFFFFF), border = Color(0xFFE3E7EF),
    text = Color(0xFF1F2937), muted = Color(0xFF6B7280), done = Color(0xFF9CA3AF),
    accent = Color(0xFF2563EB), accentSoft = Color(0xFFE8EFFF),
    danger = Color(0xFFDC2626), dangerSoft = Color(0xFFFDF0F0),
    segmentBg = Color(0xFFE7EBF3), hover = Color(0xFFE9EDF4), headingLine = Color(0xFFDFE3EA),
    checkBorder = Color(0xFFB8C0CC),
    alertBg = Color(0xFFFDEEEE), alertBorder = Color(0xFFF3C4C4),
    goodBg = Color(0xFFEAF7EF), goodBorder = Color(0xFFBFE5CC), goodText = Color(0xFF15803D),
    chipBg = Color(0xFFEEF1F6), chipGoodBg = Color(0xFFE8F7EE),
    warn = Color(0xFFD97706), brand = Color(0xFF00978C),
)

val DarkPalette = Palette(
    bg = Color(0xFF15181E), surface = Color(0xFF1E222A), border = Color(0xFF2E3440),
    text = Color(0xFFE5E7EB), muted = Color(0xFF9AA3B2), done = Color(0xFF6B7280),
    accent = Color(0xFF4F8CFF), accentSoft = Color(0xFF22324F),
    danger = Color(0xFFF87171), dangerSoft = Color(0xFF3A2226),
    segmentBg = Color(0xFF262B34), hover = Color(0xFF2A303A), headingLine = Color(0xFF363D4A),
    checkBorder = Color(0xFF5B6372),
    alertBg = Color(0xFF3A2226), alertBorder = Color(0xFF5C2F35),
    goodBg = Color(0xFF1F3329), goodBorder = Color(0xFF2F5A41), goodText = Color(0xFF4ADE80),
    chipBg = Color(0xFF262B34), chipGoodBg = Color(0xFF1F3329),
    warn = Color(0xFFF59E0B), brand = Color(0xFF2BB8AC),
)

/** Цвета приоритета — точки слева у задачи (как priority_1..3.png на компьютере). */
fun priorityColor(level: Int): Color? = when (level) {
    1 -> Color(0xFFEF4444)
    2 -> Color(0xFFF59E0B)
    3 -> Color(0xFF3B82F6)
    else -> null
}

val LocalPalette = staticCompositionLocalOf { LightPalette }

/** Текущие цвета: P.accent, P.muted … */
val P: Palette
    @Composable get() = LocalPalette.current

@Composable
fun ToDoroTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val p = if (dark) DarkPalette else LightPalette
    val scheme = if (dark) {
        darkColorScheme(primary = p.accent, secondary = p.accent, error = p.danger, background = p.bg,
            surface = p.surface, onSurface = p.text, onBackground = p.text, onSurfaceVariant = p.muted,
            outline = p.border, surfaceContainer = p.surface, surfaceContainerHigh = p.surface)
    } else {
        lightColorScheme(primary = p.accent, secondary = p.accent, error = p.danger, background = p.bg,
            surface = p.surface, onSurface = p.text, onBackground = p.text, onSurfaceVariant = p.muted,
            outline = p.border, surfaceContainer = p.surface, surfaceContainerHigh = p.surface)
    }
    CompositionLocalProvider(LocalPalette provides p) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
