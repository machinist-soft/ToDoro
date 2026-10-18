"""Умные подсказки без интернета: ToDoro учится на ваших прошлых задачах.

Ничего никуда не отправляет и сам базу не читает — получает список задач, который окно уже
прочитало (строки db.list_tasks: id, title, done, created, due_at, remind_before, urgent,
important, body, status_id). Поэтому подсказки мгновенные и не ходят по сети в общих списках.

- suggest_titles — варианты названия по первым буквам («Позв…» → «Позвонить в бухгалтерию»);
- parse_when — срок из текста («Сдать отчёт завтра в 10» → завтра 10:00, название без даты);
- suggest_priority — «срочно/важно»: по словам в названии или по похожим прошлым задачам;
- suggest_steps — описание-список шагов из похожей прошлой задачи.
"""

import re
from collections import Counter
from datetime import date, datetime, time, timedelta

WORD = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)

# Короткие служебные слова — по ним задачи не сравниваем
STOP_WORDS = {
    "в", "во", "на", "и", "а", "с", "со", "по", "к", "ко", "для", "о", "об", "у", "за", "из",
    "до", "не", "от", "то", "же", "ли", "или", "что", "как", "это", "мне", "его", "ее", "их",
}


def norm(text):
    return text.casefold().replace("ё", "е")


def same_length_norm(text):
    """Как norm, но длина строки не меняется («ß» → «ss» сдвинул бы позиции): буквы, которые
    casefold превращает в несколько, остаются как есть — по ним в parse_when позиции вырезаем."""
    return "".join(c.casefold() if len(c.casefold()) == 1 else c for c in text).replace("ё", "е")


def words(text):
    return WORD.findall(norm(text))


def stem(word):
    """Слово без окончания: «отчёта», «отчётом» → «отче»… грубо, но для сравнения хватает."""
    return word[:max(4, len(word) - 2)] if len(word) >= 5 else word


def stems(text):
    return {stem(w) for w in words(text) if w not in STOP_WORDS and not w.isdigit()}


# ---------- варианты названия ----------

def suggest_titles(text, rows, limit=5):
    """Названия прошлых задач, которые начинаются так же, как набранный текст, или в которых
    есть все набранные слова (последнее — может быть недописанным). Чаще встречавшиеся и
    недавние — выше. Сам набранный текст не предлагаем."""
    query = norm(" ".join(text.split()))
    typed = words(query)
    if len(query) < 2 or not typed:
        return []
    found = {}  # название (как писали) -> [место, сколько раз, последний id]
    for row in rows:
        task_id, title = row[0], " ".join((row[1] or "").split())
        key = norm(title)
        if not title or key == query:
            continue
        if key.startswith(query):
            rank = 0
        else:
            have = words(key)
            *whole, last = typed
            if not (any(w.startswith(last) for w in have)
                    and all(any(stem(h) == stem(w) or h.startswith(w) for h in have) for w in whole)):
                continue
            rank = 1
        item = found.get(key)
        if item is None:
            found[key] = [rank, 1, task_id, title]
        else:
            item[1] += 1
            if task_id > item[2]:
                item[2], item[3] = task_id, title
    best = sorted(found.values(), key=lambda i: (i[0], -i[1], -i[2]))
    return [title for _, _, _, title in best[:limit]]


# ---------- срок из текста ----------

NUMBERS = {"один": 1, "одну": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
           "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10}
NUM = r"(\d{1,2}|" + "|".join(NUMBERS) + r")"
WEEKDAYS = [("понедельник", "понедельника"), ("вторник", "вторника"), ("среда", "среду", "среды"),
            ("четверг", "четверга"), ("пятница", "пятницу", "пятницы"),
            ("суббота", "субботу", "субботы"), ("воскресенье", "воскресенья")]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
          "октября", "ноября", "декабря"]
PARTS = {"утром": 9, "днем": 14, "вечером": 19}

B = r"(?<![0-9a-zа-яё])"   # начало слова
E = r"(?![0-9a-zа-яё])"    # конец слова

DAY_PATTERNS = [
    ("rel", re.compile(B + r"(?:(?:до|к|на) )?(сегодня|послезавтра|завтра)" + E)),
    ("in_days", re.compile(B + r"через (?:" + NUM + r" )?(дн[яеи]й?|день|недел[юиь]|неделю)" + E)),
    # «к пятнице» — дательный падеж только после «к»: «в среде разработки» — не среда
    ("weekday", re.compile(B + r"(?:к|ко) (понедельнику|вторнику|среде|четвергу|пятнице|субботе|"
                           r"воскресенью)" + E)),
    # день недели — только с предлогом: «Проект Среда», «про среду разработки» — не срок
    ("weekday", re.compile(B + r"(?:в|во|до|к|ко|на) (" +
                           "|".join(n for forms in WEEKDAYS for n in forms) + r")" + E)),
    # «25.10» — месяц двумя цифрами и не часть номера версии («3.12.1», «10.5 кг» — не даты)
    ("dmy", re.compile(B + r"(?:(?:до|к|на) )?(\d{1,2})\.(\d{2})(?:\.(\d{2}|\d{4}))?(?!\.?\d)" + E)),
    ("dm", re.compile(B + r"(?:(?:до|к|на) )?(\d{1,2}) (" + "|".join(MONTHS) + r")" + E)),
]
IN_TIME = re.compile(B + r"через (?:" + NUM + r" )?(час[аов]*|минут[уы]?|мин)" + E)
# «10:30» — время всегда, «10.30» — только после «в»/«к» (иначе это дата или номер версии)
CLOCK = re.compile(B + r"(?:(?:в|к|до) )?(\d{1,2}):(\d{2})" + E + r"|" + B + r"(?:в|к) (\d{1,2})\.(\d{2})" + E)
HOUR = re.compile(B + r"(?:в|к|до) (\d{1,2})(?: (час[аов]*|ч|утра|дня|вечера|ночи))?" + E)
PART = re.compile(B + r"(утром|днем|вечером)" + E)
QUOTED = re.compile(r"«[^»]*»|\"[^\"]*\"|“[^”]*”|„[^“”]*[“”]")
# После этих слов дата — не срок: «протокол от 1 мая», «отчёт с 25.10», «про завтра»
NOT_DUE_AFTER = {"от", "с", "со", "про", "о", "об", "после", "за"}
LATIN = re.compile(r"[a-z]")


def number(value):
    if value is None:
        return 1
    return int(value) if value.isdigit() else NUMBERS[value]


def parse_when(text, now=None):
    """Ищет в тексте срок. Возвращает (текст без слов о сроке, дата, время или None) или None,
    если срока нет. Время без дня — сегодня, а если оно уже прошло — завтра.
    Осторожничает: лучше не заметить срок, чем испортить обычное название."""
    now = now or datetime.now()
    today = now.date()
    low = same_length_norm(text)  # из него вырезаем найденное, чтобы «к 15 марта» не стало ещё и «к 15» часам
    # Текст в кавычках — название («Завтра была война»), сроков в нём не ищем
    low = QUOTED.sub(lambda m: " " * len(m[0]), low)
    spans, day, clock = [], None, None

    def take(match):
        nonlocal low
        start, end = match.span()
        spans.append((start, end))
        low = low[:start] + " " * (end - start) + low[end:]

    def word_before(match):
        head = low[:match.start()].split()
        return head[-1] if head else ""

    def at_end(match):
        return not low[match.end():].strip(" ,.;:!?-–—")

    for kind, pattern in DAY_PATTERNS:
        if day is not None:
            break
        match = pattern.search(low)
        if match is None or word_before(match) in NOT_DUE_AFTER:
            continue
        if kind == "rel":
            # «Фильм Сегодня» — с большой буквы не в начале и без предлога — это имя, не срок
            if match[0] == match[1] and text[match.start()].isupper() and low[:match.start()].strip():
                continue
            day = today + timedelta(days={"сегодня": 0, "завтра": 1, "послезавтра": 2}[match[1]])
        elif kind == "in_days":
            count = number(match[1])
            day = today + timedelta(days=count * (7 if match[2].startswith("недел") else 1))
        elif kind == "weekday":
            wanted = next(i for i, forms in enumerate(WEEKDAYS)
                          if match[1] in forms or match[1][:4] == forms[0][:4])
            day = today + timedelta(days=(wanted - today.weekday() - 1) % 7 + 1)
        else:
            has_prep = match[0].split()[0] in ("до", "к", "на")
            # «Оплатить счёт 25.10» — без предлога дата только в конце; «Python до 3.12» — версия
            if kind == "dmy" and (LATIN.search(word_before(match)) or not (has_prep or at_end(match))):
                continue
            dd = int(match[1])
            mm = int(match[2]) if kind == "dmy" else MONTHS.index(match[2]) + 1
            year = match[3] if kind == "dmy" else None
            yy = (int(year) + 2000 if len(year) == 2 else int(year)) if year else today.year
            try:
                day = date(yy, mm, dd)
            except ValueError:
                continue
            if year and day < today:  # срок в прошлом — скорее дата документа, а не срок
                day = None
                continue
            if not year and day < today:
                day = day.replace(year=yy + 1)
        take(match)

    match = IN_TIME.search(low)
    if match and day is None:
        count = number(match[1])
        moment = now + (timedelta(hours=count) if match[2].startswith("час")
                        else timedelta(minutes=count))
        moment += timedelta(minutes=(-moment.minute) % 5)  # в форме минуты — с шагом 5
        day, clock = moment.date(), moment.time().replace(second=0, microsecond=0)
        take(match)
    if clock is None:
        match = CLOCK.search(low)
        if match:
            hour, minute = int(match[1] or match[3]), int(match[2] or match[4])
            if hour < 24 and minute < 60:
                clock = time(hour, minute)
                take(match)
    if clock is None:
        match = HOUR.search(low)
        # «в 3» без дня и не в конце — скорее «в 3 кассе», чем время
        if match and int(match[1]) < 24 and (day is not None or match[2] or at_end(match)):
            hour, unit = int(match[1]), match[2]
            if unit in ("дня", "вечера") and hour < 12:
                hour += 12
            elif unit == "ночи" and hour == 12:
                hour = 0
            elif unit is None and 1 <= hour <= 7:
                # «позвонить в 3» — почти всегда днём; без дня такое «в 3» не трогаем
                hour = hour + 12 if day is not None else None
            elif unit is None and hour == 0:
                hour = None
            if hour is not None:
                clock = time(hour, 0)
                take(match)
    if clock is None:
        match = PART.search(low)
        around = low[max(0, match.start() - 4):match.end() + 4].split() if match else []
        # «днём и ночью», «утром или вечером» — это не время
        if match and not {"и", "или"} & set(around):
            clock = time(PARTS[match[1]], 0)
            take(match)

    if day is None and clock is None:
        return None
    if day is None:
        day = today if clock > now.time() else today + timedelta(days=1)
    # Вырезаем найденное из текста (с конца, чтобы не сбить позиции)
    clean = text
    for start, end in sorted(spans, reverse=True):
        clean = clean[:start] + " " + clean[end:]
    clean = " ".join(clean.split()).strip(" ,.;:-–—")
    clean = re.sub(r"\s+([,.;:!?])", r"\1", clean)
    clean = re.sub(r"(?:\s+(?:в|во|к|до|на))+$", "", clean, flags=re.IGNORECASE).strip(" ,.;:-–—")
    if not clean:
        return None  # название из одних слов о сроке — пусть остаётся как есть
    if text[:1].isupper():  # «Завтра позвонить маме» → «Позвонить маме»
        clean = clean[0].upper() + clean[1:]
    return clean, day, clock


def describe_when(day, clock, today=None):
    """«завтра, 10:00», «пт 23.10» — коротко, для подсказки."""
    today = today or date.today()
    names = {0: "сегодня", 1: "завтра", 2: "послезавтра"}
    delta = (day - today).days
    text = names.get(delta) or ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][day.weekday()] + \
        day.strftime(" %d.%m") + (day.strftime(".%Y") if day.year != today.year else "")
    return f"{text}, {clock:%H:%M}" if clock else text


# ---------- приоритет и шаги по похожим задачам ----------

# Сказано прямо — ставим сразу; похожие слова («срочный вклад», «обязательные платежи») —
# только предлагаем
URGENT_EXACT, IMPORTANT_EXACT = {"срочно", "asap"}, {"важно"}
URGENT_WORDS = ("срочн", "немедленн")
IMPORTANT_WORDS = ("важн", "обязательн", "критичн")


def similar(text, rows, least=0.5):
    """Прошлые задачи, похожие на текст (общие слова без окончаний), — сначала самые похожие
    и недавние."""
    mine = stems(text)
    if not mine:
        return []
    scored = []
    for row in rows:
        theirs = stems(row[1] or "")
        if not theirs or norm(row[1]) == norm(text):
            continue
        score = len(mine & theirs) / len(mine | theirs)
        if score >= least:
            scored.append((score, row[0], row))
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return [row for _, _, row in scored]


def suggest_priority(text, rows):
    """(срочно, важно, почему, сказано явно) или None. Слова «срочно», «важно» в названии —
    сказано явно (True); «срочный», «обязательные»… — только совет; иначе — как чаще всего
    отмечали похожие задачи (если хотя бы две из них и не «обычные»)."""
    low = words(text)
    urgent = bool(URGENT_EXACT & set(low))
    important = bool(IMPORTANT_EXACT & set(low))
    if urgent or important:
        found = [n for n, f in (("«срочно»", urgent), ("«важно»", important)) if f]
        return urgent, important, "в названии есть " + " и ".join(found), True
    urgent = any(w.startswith(URGENT_WORDS) for w in low)
    important = any(w.startswith(IMPORTANT_WORDS) for w in low)
    if urgent or important:
        return urgent, important, "так подсказывают слова в названии", False
    alike = similar(text, rows)
    if len(alike) < 2:
        return None
    votes = Counter((bool(r[6]), bool(r[7])) for r in alike[:10])
    (urgent, important), count = votes.most_common(1)[0]
    if not (urgent or important) or count * 2 <= min(len(alike), 10):
        return None
    return urgent, important, f"так отмечены похожие задачи ({count} из {min(len(alike), 10)})", False


def suggest_steps(text, rows):
    """(название, описание) похожей прошлой задачи, у которой описание — список из нескольких
    строк (шаги), или None."""
    for row in similar(text, rows):
        body = (row[8] or "").strip()
        if sum(1 for line in body.splitlines() if line.strip()) >= 2:
            return row[1], body
    return None
