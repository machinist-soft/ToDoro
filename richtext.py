"""Оформление описания задачи — простыми значками прямо в тексте (без окон, только разбор).

Описание хранится обычным текстом, поэтому его читают без изменений и телефон, и старые версии
ToDoro, и экспорт в CSV, — видны только значки:

    **жирный**   *курсив*   ~~зачёркнутый~~
    - пункт списка            (или «• пункт»)
    1. пункт нумерованного списка
    | ячейка | ячейка |        (таблица: строки подряд, строка из «---» — линия под заголовком)

Здесь — разбор этого текста для показа (inline, blocks), значки для подсветки в поле ввода
(marks), снятие значков (plain), а ещё перевод письма Outlook из HTML (html_to_markup) и
строк, скопированных из Excel (tsv_to_table), в такой же текст.
"""
import re
from html.parser import HTMLParser

# **…**, ~~…~~, *…*: внутри не с пробела и не на пробел — «2 * 3 * 4» остаётся текстом.
# Закрывающие «**» — последние в «***»: «**жирный и *курсив***» — курсив внутри жирного.
INLINE = re.compile(r"\*\*(?=\S)(?P<bold>.+?)(?<=\S)\*\*(?!\*)"
                    r"|~~(?=\S)(?P<strike>.+?)(?<=\S)~~"
                    r"|(?<![*\w])\*(?=[^\s*])(?P<italic>.+?)(?<=[^\s*])\*(?![*\w])")
SIZE = {"bold": 2, "strike": 2, "italic": 1}  # длина значка
LONG_LINE = 2000  # в строке длиннее значки не ищем: на «*a *a *a…» поиск идёт очень долго
BULLET = re.compile(r"^(\s*)([-•–*])\s+(?=\S)")
NUMBER = re.compile(r"^(\s*)(\d{1,3})[.)]\s+(?=\S)")
TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
TABLE_RULE = re.compile(r"^\s*\|(\s*:?-{3,}:?\s*\|)+\s*$")


def inline(text, styles=frozenset()):
    """Строка без значков по кусочкам: [(текст, набор стилей)]. Значки внутри значков
    (**жирный и *курсив***) тоже понимаются."""
    parts, pos = [], 0
    if len(text) > LONG_LINE:  # журнал или код одной строкой — значки не ищем (это долго)
        return [(text, frozenset(styles))] if text else []
    for m in INLINE.finditer(text):
        if m.start() > pos:
            parts.append((text[pos:m.start()], styles))
        parts += inline(m.group(m.lastgroup), styles | {m.lastgroup})
        pos = m.end()
    if pos < len(text):
        parts.append((text[pos:], styles))
    return [(t, frozenset(s)) for t, s in parts if t]


def marks(text):
    """Для подсветки в поле ввода: [(начало, конец, что)] в одной строке. «mark» — сами значки
    (их показывают бледно), «bold»/«italic»/«strike» — текст между ними."""
    found = []
    if len(text) > LONG_LINE:
        return found
    for m in INLINE.finditer(text):
        style = m.lastgroup
        size, start, end, inner = SIZE[style], m.start(), m.end(), m.start(style)
        found += [(start, start + size, "mark"), (end - size, end, "mark")]
        found.append((inner, inner + len(m.group(style)), style))
        found += [(s + inner, e + inner, k) for s, e, k in marks(m.group(style))]
    return found


def cells(line):
    """Ячейки строки таблицы «| a | b |» → ["a", "b"]."""
    return [cell.strip() for cell in line.strip()[1:-1].split("|")]


def blocks(text):
    """Описание по частям для показа:
    ("text", строка) · ("bullet", строка, отступ) · ("number", номер, строка, отступ) ·
    ("table", [строки ячеек], есть ли заголовок)."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    result, i = [], 0
    while i < len(lines):
        line = lines[i]
        if TABLE_LINE.match(line):
            rows, header = [], False
            while i < len(lines) and TABLE_LINE.match(lines[i]):
                if TABLE_RULE.match(lines[i]):
                    header = header or len(rows) == 1
                else:
                    rows.append(cells(lines[i]))
                i += 1
            if rows:
                width = max(len(r) for r in rows)
                result.append(("table", [r + [""] * (width - len(r)) for r in rows], header))
            continue
        m = BULLET.match(line)
        if m:
            result.append(("bullet", line[m.end():], len(m.group(1).expandtabs(4)) // 2))
        else:
            m = NUMBER.match(line)
            if m:
                result.append(("number", m.group(2), line[m.end():], len(m.group(1).expandtabs(4)) // 2))
            else:
                result.append(("text", line))
        i += 1
    return result


def plain(text):
    """Описание без значков — для коротких подписей (карточка на доске, письмо по задаче)."""
    out = []
    for block in blocks(text):
        kind = block[0]
        if kind == "table":
            out += ["  ".join("".join(t for t, _ in inline(c)) for c in row) for row in block[1]]
            continue
        line = block[-1] if kind == "text" else block[1] if kind == "bullet" else block[2]
        line = "".join(t for t, _ in inline(line))
        out.append("• " + line if kind == "bullet" else f"{block[1]}. {line}" if kind == "number" else line)
    return "\n".join(out)


def table(rows):
    """Строки ячеек → таблица со значками (первая строка — заголовок)."""
    def clean(cell):
        return " ".join(str(cell).replace("|", "/").split())
    rows = [[clean(c) for c in row] for row in rows]
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(r) + " |" for r in rows]
    if len(rows) > 1:
        lines.insert(1, "|" + "|".join(["---"] * width) + "|")
    return "\n".join(lines)


def tsv_to_table(text):
    """Скопировали ячейки из Excel (столбцы через табуляцию) — таблица со значками; иначе None.
    Одна ячейка или одна строка из одной колонки — это просто текст."""
    lines = (text or "").replace("\r\n", "\n").strip("\n").split("\n")
    rows = [line.split("\t") for line in lines]
    # таблица — только если табуляция в каждой непустой строке: случайный Tab в тексте из Word
    # или с сайта не превращает все абзацы в таблицу
    filled = [row for row, line in zip(rows, lines) if line.strip()]
    if not filled or not all(len(row) > 1 for row in filled):
        return None
    return table(rows)


# --- письмо Outlook: HTML → текст со значками ---

SKIP = {"head", "style", "script", "title", "xml"}
BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "tr", "ul", "ol",
         "section", "article", "header", "footer"}
# Пока письмо разбирается, значки — служебными знаками: так «****1234» из текста письма
# (маска номера карты) не спутать с соседними <b></b><b>; в «**» они превращаются в конце
STYLE_TAGS = {"b": "\x01", "strong": "\x01", "i": "\x02", "em": "\x02", "s": "\x03", "strike": "\x03",
              "del": "\x03"}
STYLE_MARKS = {"\x01": "**", "\x02": "*", "\x03": "~~"}
SPACES = " \t\xa0\n"
WORD_BULLET = re.compile(r"^\s*[·•o§▪–-]\s+(?=\S)")  # список Word: «·  пункт» обычным абзацем


class _Open:
    """Открывающий значок в строке, пока тег не закрыт (его ищут по месту, а не по номеру)."""

    def __init__(self, char):
        self.char = char

    def __str__(self):
        return self.char


def to_markup(text):
    """Служебные знаки разбора → значки. Закрытый и сразу снова открытый жирный
    (<b>a</b><b>b</b>, Word так дробит текст) — один кусок."""
    for char, marker in STYLE_MARKS.items():
        text = text.replace(char * 2, "").replace(char, marker)
    return text


class _Html(HTMLParser):
    """Собирает текст письма: абзацы — строками, жирный/курсив/зачёркнутый — значками,
    списки — «- »/«1. », таблицы с данными — таблицей со значками. Таблицы для вёрстки
    (внутри другая таблица, одна строка или один столбец) — просто текстом."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []            # готовые строки
        self.line = []           # кусочки текущей строки
        self.skip = 0
        self.lists = []          # стек списков: ["ul"] или ["ol", номер]
        self.tables = []         # стек таблиц: {"rows": [...], "row": [...] или None, "cell": [...] или None, "nested": bool}
        self.styles = []         # открытые <b>/<i>/<s>: [знак, куда пишется, _Open или None — вложенный повтор]

    # куда пишется текст: в ячейку таблицы или в строку
    def target(self):
        table = self.tables[-1] if self.tables else None
        if table is not None and table["cell"] is not None:
            return table["cell"]
        return self.line

    def break_styles(self, target, between):
        """Жирный через <br> или абзац: закрыть его в конце строки, вставить between
        (перевод строки в ячейке) и открыть снова — у каждой строки свои значки."""
        open_here = [style for style in self.styles if style[1] is target and style[2] is not None]
        for style in reversed(open_here):
            self.close_mark(target, style[2])
        target += between
        return open_here

    def reopen(self, target, styles):
        for style in styles:
            style[1], style[2] = target, _Open(style[0])
            target.append(style[2])

    def newline(self, keep_empty=False):
        """Закончить строку. Пустая строка остаётся только от пустого абзаца или <br>
        (так в письмах делают отступы), а не от каждого тега."""
        if self.tables and self.tables[-1]["cell"] is not None:
            cell = self.tables[-1]["cell"]  # в ячейке: таблица данных склеит, вёрстка — оставит
            self.reopen(cell, self.break_styles(cell, ["\n"]))
            return
        open_here = self.break_styles(self.line, [])
        text = self.clean("".join(map(str, self.line)))
        self.line = []
        self.reopen(self.line, open_here)
        if text or (keep_empty and self.out and self.out[-1]):
            self.out.append(text)

    @staticmethod
    def clean(text):
        """Строка письма: без лишних пробелов; отступ остаётся только у пункта вложенного списка."""
        text = to_markup(text.replace("\xa0", " "))
        indent = re.match(r"( +)(?=- |\d+\. )", text)
        text = WORD_BULLET.sub("- ", re.sub(r"[ \t]+", " ", text).strip())
        return (indent.group(1) if indent and text else "") + text

    def open_style(self, char):
        target = self.target()
        if any(style[0] == char and style[2] is not None for style in self.styles):
            self.styles.append([char, target, None])  # <b> внутри <b> — значки уже стоят
            return
        mark = _Open(char)
        self.styles.append([char, target, mark])
        target.append(mark)

    def close_style(self, char):
        style = next((s for s in reversed(self.styles) if s[0] == char), None)
        if style is None:
            return  # лишний </b>
        self.styles.remove(style)
        if style[2] is not None:
            self.close_mark(style[1], style[2])

    @staticmethod
    def close_mark(target, mark):
        """Закрыть значок: пробелы с краёв — за значки («**Срок:** пятница», а не
        «**Срок: **пятница» — так значок не понимается); без текста внутри — значков нет."""
        # ищем с конца: открытый значок почти всегда рядом с концом, а в ячейке таблицы список
        # копит всё её содержимое — поиск с начала на большом письме шёл бы десятки секунд
        start = next((i for i in range(len(target) - 1, -1, -1) if target[i] is mark), None)
        if start is None:
            return
        inner = "".join(piece for piece in target[start + 1:] if isinstance(piece, str))
        if not inner.strip(SPACES + "".join(STYLE_MARKS)):
            del target[start]
            return
        lead = ""  # пробелы в начале — перед значком
        for i in range(start + 1, len(target)):
            if not isinstance(target[i], str):
                break
            piece = target[i].lstrip(SPACES)
            lead += target[i][:len(target[i]) - len(piece)]
            target[i] = piece
            if piece:
                break
        trail = ""  # пробелы в конце — после значка
        for i in range(len(target) - 1, start, -1):
            if not isinstance(target[i], str):
                break
            piece = target[i].rstrip(SPACES)
            trail = target[i][len(piece):] + trail
            target[i] = piece
            if piece:
                break
        target.append(mark.char)
        target.append(trail)
        target.insert(start, lead)

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "br":
            self.newline(keep_empty=True)
        elif tag in ("ul", "ol"):
            self.newline()
            self.lists.append([tag, 0])
        elif tag == "li":
            self.newline()
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self.target().append("  " * (len(self.lists) - 1) + f"{self.lists[-1][1]}. ")
            else:
                self.target().append("  " * max(len(self.lists) - 1, 0) + "- ")
        elif tag == "table":
            if self.tables:
                self.tables[-1]["nested"] = True
            else:
                self.newline()
            self.tables.append({"rows": [], "row": None, "cell": None, "nested": False})
        elif tag == "tr" and self.tables:
            self.tables[-1]["row"] = []
        elif tag in ("td", "th") and self.tables:
            table = self.tables[-1]
            if table["row"] is None:
                table["row"] = []
            table["cell"] = []
        elif tag in STYLE_TAGS:
            self.open_style(STYLE_TAGS[tag])
        elif tag in BLOCK:
            self.newline()

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(self.skip - 1, 0)
            return
        if self.skip:
            return
        if tag in ("ul", "ol"):
            self.newline()
            if self.lists:
                self.lists.pop()
        elif tag in ("td", "th") and self.tables:
            table = self.tables[-1]
            if table["cell"] is not None and table["row"] is not None:
                cell = table["cell"]
                self.break_styles(cell, [])  # жирный не выходит за ячейку
                table["row"].append("".join(map(str, cell)))
            table["cell"] = None
        elif tag == "tr" and self.tables:
            table = self.tables[-1]
            if table["row"] is not None:
                table["rows"].append(table["row"])
            table["row"] = None
        elif tag == "table" and self.tables:
            self.close_table(self.tables.pop())
        elif tag in STYLE_TAGS:
            self.close_style(STYLE_TAGS[tag])
        elif tag in BLOCK or tag == "li":
            self.newline(keep_empty=tag in ("p", "div"))

    def close_table(self, info):
        """Таблица данных — таблицей со значками (абзацы в ячейке — через пробел). Таблица для
        вёрстки — строками своих ячеек: так свёрстаны рассылки и подписи, абзацы сохраняются."""
        rows = [r for r in info["rows"] if any(c.strip(SPACES + "".join(STYLE_MARKS)) for c in r)]
        layout = info["nested"] or len(rows) < 2 or max((len(r) for r in rows), default=0) < 2
        if layout:
            lines = []
            for row in rows:
                parts = [[self.clean(line) for line in cell.split("\n")] for cell in row]
                parts = [[line for line in cell if line] for cell in parts]
                if all(len(cell) <= 1 for cell in parts):  # ячейки строки в одну строчку — рядом
                    lines.append(" ".join(cell[0] for cell in parts if cell))
                else:
                    lines += [line for cell in parts for line in cell]
            text = "\n".join(line for line in lines if line)
        else:
            text = table([[to_markup(re.sub(r"\s+", " ", c.replace("\xa0", " "))).strip() for c in r]
                          for r in rows])
        if self.tables:  # внутренняя таблица — своими строками в ячейку внешней (та — вёрстка)
            parent = self.tables[-1]
            if parent["cell"] is not None:
                parent["cell"].append("\n" + text + "\n")
            return
        self.newline()
        if not text:
            return
        if not layout and self.out and self.out[-1]:
            self.out.append("")  # таблицу отделяем от текста пустой строкой
        self.out += text.split("\n")
        self.out.append("")

    def handle_data(self, data):
        if self.skip:
            return
        data = data.replace("\r", " ").replace("\n", " ")
        self.target().append(data.translate({ord(c): None for c in STYLE_MARKS}))

    def text(self):
        self.newline()
        while self.tables:
            self.close_table(self.tables.pop())
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self.out)).strip()


def html_to_markup(html):
    """Текст письма из его HTML (Outlook HTMLBody) — со значками оформления."""
    parser = _Html()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001 — испорченный HTML: берём, что успели разобрать
        pass
    return parser.text()
