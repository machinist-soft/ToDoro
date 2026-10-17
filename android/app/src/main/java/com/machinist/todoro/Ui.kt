package com.machinist.todoro

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Элементы оформления в стиле окна ToDoro на компьютере (плоские кнопки, переключатели, поля). */

private val Corner = RoundedCornerShape(6.dp)

enum class Look { ACCENT, SOFT, ACCENT_SOFT, DANGER_SOFT }

/** Кнопка как на компьютере: синяя (главная), белая с рамкой, мягкая синяя или мягкая красная. */
@Composable
fun FlatButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    look: Look = Look.SOFT,
    enabled: Boolean = true,
    height: Dp = 44.dp,
) {
    val p = P
    val (bg, fg, border) = when (look) {
        Look.ACCENT -> Triple(p.accent, Color.White, null)
        Look.SOFT -> Triple(p.surface, p.text, p.border)
        Look.ACCENT_SOFT -> Triple(p.accentSoft, p.accent, null)
        Look.DANGER_SOFT -> Triple(p.dangerSoft, p.danger, null)
    }
    Box(
        modifier
            .height(height)
            .clip(Corner)
            .background(if (enabled) bg else p.segmentBg)
            .then(if (border != null) Modifier.border(1.dp, border, Corner) else Modifier)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 16.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = if (enabled) fg else p.done, fontSize = 15.sp,
            fontWeight = if (look == Look.ACCENT) FontWeight.Medium else FontWeight.Normal, maxLines = 1)
    }
}

/** Переключатель «Все / Активные / …» — серая подложка, выбранный пункт белый с синим текстом. */
@Composable
fun <T> Segmented(items: List<Pair<T, String>>, selected: T?, onSelect: (T) -> Unit) {
    val p = P
    Row(
        Modifier.clip(Corner).background(p.segmentBg).padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        items.forEach { (value, label) ->
            val on = value == selected
            Text(
                label,
                Modifier.clip(RoundedCornerShape(5.dp))
                    .background(if (on) p.surface else Color.Transparent)
                    .clickable { onSelect(value) }
                    .padding(horizontal = 12.dp, vertical = 7.dp),
                color = if (on) p.accent else p.text, fontSize = 14.sp, maxLines = 1,
            )
        }
    }
}

/** Точка приоритета слева у задачи; у обычной задачи — пустое место того же размера. */
@Composable
fun PriorityDot(level: Int, size: Dp = 9.dp) {
    val color = priorityColor(level)
    Box(Modifier.size(size).clip(CircleShape).background(color ?: Color.Transparent))
}

/** Флажок «выполнено»: квадратик с рамкой, отмеченный — синий с белой галочкой. */
@Composable
fun DoneBox(done: Boolean, onClick: () -> Unit) {
    val p = P
    Box(Modifier.size(44.dp).clickable(onClick = onClick), contentAlignment = Alignment.Center) {
        Box(
            Modifier.size(22.dp).clip(RoundedCornerShape(5.dp))
                .background(if (done) p.accent else p.surface)
                .then(if (done) Modifier else Modifier.border(1.5.dp, p.checkBorder, RoundedCornerShape(5.dp))),
            contentAlignment = Alignment.Center,
        ) {
            if (done) Text("✓", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
        }
    }
}

/** Отметка статуса как в столбце «Статус»: ⚠ — просрочено, ✔ — выполнено, ○ — остальные. */
@Composable
fun StatusMark(task: Task, status: Status?, fontSize: Int = 13) {
    val p = P
    val (mark, color) = when {
        task.done -> "✔" to p.done
        task.overdue -> "⚠" to p.danger
        else -> "○" to (status?.let { Color(it.color) } ?: p.muted)
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(mark, color = color, fontSize = fontSize.sp)
        Spacer(Modifier.width(4.dp))
        Text(status?.name ?: "", color = if (task.overdue) p.danger else if (task.done) p.done else p.muted,
            fontSize = fontSize.sp, maxLines = 1)
    }
}

/** Подпись над полем в форме: «Заголовок», «Описание»… */
@Composable
fun FieldLabel(text: String) {
    Text(text, color = P.muted, fontSize = 13.sp, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
}

/** Поле ввода как на компьютере: белое, серая рамка, при вводе — синяя. */
@Composable
fun Field(
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String = "",
    singleLine: Boolean = true,
    minLines: Int = 1,
    onDone: (() -> Unit)? = null,
) {
    val p = P
    var focused by remember { mutableStateOf(false) }
    BasicTextField(
        value = value,
        onValueChange = onChange,
        modifier = modifier.onFocusChanged { focused = it.isFocused },
        singleLine = singleLine,
        minLines = minLines,
        textStyle = TextStyle(color = p.text, fontSize = 16.sp),
        cursorBrush = SolidColor(p.accent),
        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences,
            imeAction = if (onDone != null) androidx.compose.ui.text.input.ImeAction.Done
            else androidx.compose.ui.text.input.ImeAction.Default),
        keyboardActions = KeyboardActions(onDone = { onDone?.invoke() }),
        decorationBox = { inner ->
            Box(
                Modifier.fillMaxWidth().defaultMinSize(minHeight = 44.dp).clip(Corner).background(p.surface)
                    .border(if (focused) 1.5.dp else 1.dp, if (focused) p.accent else p.border, Corner)
                    .padding(horizontal = 12.dp, vertical = 11.dp),
                contentAlignment = if (singleLine) Alignment.CenterStart else Alignment.TopStart,
            ) {
                if (value.isEmpty()) Text(placeholder, color = p.done, fontSize = 16.sp)
                inner()
            }
        },
    )
}

/** Выпадающий список как Combobox на компьютере: поле с ▾, по нажатию — пункты. */
@Composable
fun <T> DropField(shown: String, options: List<Pair<String, T>>, modifier: Modifier = Modifier, onPick: (T) -> Unit) {
    val p = P
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        Row(
            Modifier.fillMaxWidth().height(44.dp).clip(Corner).background(p.surface)
                .border(1.dp, p.border, Corner).clickable { open = true }.padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(shown, Modifier.weight(1f), color = p.text, fontSize = 16.sp, maxLines = 1)
            Text("▾", color = p.muted, fontSize = 14.sp)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { (text, value) ->
                DropdownMenuItem(text = { Text(text) }, onClick = { open = false; onPick(value) })
            }
        }
    }
}

/** Флажок с подписью («Срочно», «Важно»). */
@Composable
fun CheckLine(text: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    val p = P
    Row(Modifier.clip(Corner).clickable { onChange(!checked) }.padding(end = 8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        DoneBox(checked) { onChange(!checked) }
        Text(text, color = p.text, fontSize = 16.sp)
    }
}

/** Синяя ссылка-действие: «Сегодня», «Завтра»… */
@Composable
fun LinkText(text: String, onClick: () -> Unit) {
    Text(text, Modifier.clip(Corner).clickable(onClick = onClick).padding(vertical = 6.dp, horizontal = 2.dp),
        color = P.accent, fontSize = 14.sp)
}

/** Полоса-уведомление под шапкой (как Banner на компьютере): красная, жёлтая или зелёная. */
@Composable
fun Strip(text: String, kind: String = "alert", action: String? = null, onAction: (() -> Unit)? = null) {
    val p = P
    val (bg, border) = when (kind) {
        "good" -> p.goodBg to p.goodBorder
        "warn" -> p.warn.copy(alpha = 0.12f) to p.warn.copy(alpha = 0.35f)
        else -> p.alertBg to p.alertBorder
    }
    Column(
        Modifier.fillMaxWidth().padding(vertical = 4.dp).clip(Corner).background(bg)
            .border(BorderStroke(1.dp, border), Corner).padding(12.dp),
    ) {
        Text(text, color = p.text, fontSize = 14.sp)
        if (action != null && onAction != null) {
            Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.End) {
                FlatButton(action, onAction, height = 36.dp)
            }
        }
    }
}

/** Белая карточка с рамкой — основа списка задач и карточки задачи. */
@Composable
fun Panel(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val p = P
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(p.surface)
        .border(1.dp, p.border, RoundedCornerShape(8.dp))) { content() }
}

@Composable
fun HScroll(content: @Composable () -> Unit) {
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        content()
    }
}

@Composable
fun Centered(text: String) {
    Text(text, Modifier.fillMaxWidth().padding(28.dp), color = P.muted, textAlign = TextAlign.Center)
}
