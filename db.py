"""Работа с базой данных SQLite: здесь хранятся задачи."""
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Файл базы лежит в личной папке пользователя (%APPDATA%\ToDoro): в папку установленной
# программы (Program Files) писать нельзя. Если файла нет, SQLite создаст его сам.
DATA_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "ToDoro"
DB_PATH = DATA_DIR / "todoro.db"
# Остальные списки задач (кроме личного) — каждый в своём файле в этой папке
LISTS_DIR = DATA_DIR / "lists"
PERSONAL = "personal"  # id личного списка; его задачи — в основном файле todoro.db
# Раньше база лежала рядом с программой (сначала под именем todo.db)
OLD_DB_PATHS = [Path(__file__).with_name("todoro.db"), Path(__file__).with_name("todo.db")]


def default_path():
    """todoro.db в DATA_DIR; старая база из папки программы при первом запуске переносится туда.
    Если старый файл сейчас занят (открыт другой копией программы) — работаем с ним."""
    if not DB_PATH.exists():
        old = next((p for p in OLD_DB_PATHS if p.exists()), None)
        if old:
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                os.replace(old, DB_PATH)
            except OSError:
                return old
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH

# Столбцы, которые появились в новых версиях программы.
# В старую базу они добавляются автоматически, задачи при этом сохраняются.
NEW_COLUMNS = [
    ("due_at", "TEXT"),             # срок выполнения: 'ГГГГ-ММ-ДД ЧЧ:ММ' или NULL
    ("remind_before", "INTEGER"),   # за сколько минут до срока напомнить, NULL — не напоминать
    ("reminded", "INTEGER NOT NULL DEFAULT 0"),  # 1 — напоминание уже показано
    ("urgent", "INTEGER NOT NULL DEFAULT 0"),    # 1 — срочно
    ("important", "INTEGER NOT NULL DEFAULT 0"), # 1 — важно
    ("is_example", "INTEGER NOT NULL DEFAULT 0"),  # 1 — пример, добавленный кнопкой «Примеры»
    ("body", "TEXT NOT NULL DEFAULT ''"),          # описание задачи (title — её заголовок)
    ("status_id", "INTEGER"),                       # колонка доски (таблица statuses)
    ("done_at", "TEXT"),                            # когда задачу выполнили (для «сегодня выполнено»)
    ("created_by", "TEXT"),                         # кто создал (в общих списках — имя участника)
    ("assignee", "TEXT"),                           # исполнитель (в общих списках)
    ("updated_by", "TEXT"),                         # кто изменил последним
    ("updated_at", "TEXT"),                         # когда изменили последний раз (местное время)
    ("version", "INTEGER NOT NULL DEFAULT 0"),      # растёт при каждом изменении — чтобы заметить,
                                                    # что задачу поменял кто-то другой
    ("mail_id", "TEXT"),                            # письмо Outlook, из которого создана задача
    ("mail_from", "TEXT"),                          # его отправитель — адресат письма по задаче
]

# Статусы по умолчанию: (название, цвет, «задачи здесь выполнены»)
DEFAULT_STATUSES = [
    ("Новая", "#3b82f6", 0),
    ("В работе", "#f59e0b", 0),
    ("Выполнено", "#22c55e", 1),
]


class SharedConnection(sqlite3.Connection):
    """Соединение с общим списком в сетевой папке.

    Каждое отдельное чтение из файла — это захват и снятие блокировки, то есть несколько
    «поездок» до сервера; через VPN одна такая поездка занимает десятки миллисекунд, а одно
    действие в окне (перенести задачу, сохранить правку) читает файл десятки раз.
    Поэтому все чтения, сделанные за одно действие, идут в одной транзакции (одна блокировка),
    а закрывается она, когда окно освободилось (after_idle). Перед записью транзакция
    чтения закрывается, чтобы запись ждала других участников как обычно (иначе SQLite сразу
    ответил бы «база занята»)."""
    root = None      # окно Tk; пока не задано — соединение работает как обычное
    reading = False  # открыта наша транзакция чтения

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Сколько записей сохранили мы сами: счётчик изменений файла растёт и от них, а
        # перечитывать список нужно, только если его поменял кто-то другой
        self.own_writes = 0
        self.dirty = False
        self.set_trace_callback(self.trace)

    def trace(self, sql):
        word = sql.lstrip()[:8].upper()
        if word.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
            self.dirty = True
        elif word.startswith("COMMIT"):
            self.own_writes += self.dirty
            self.dirty = False
        elif word.startswith("ROLLBACK"):
            self.dirty = False

    def execute(self, sql, *args):
        if self.root is not None:
            word = sql.lstrip()[:6].upper()
            if word == "SELECT":
                if not self.in_transaction:
                    super().execute("BEGIN")
                    self.reading = True
                    self.root.after_idle(self.end_reading)
            elif word != "PRAGMA":
                self.end_reading()
        return super().execute(sql, *args)

    def executemany(self, sql, *args):
        self.end_reading()
        return super().executemany(sql, *args)

    def executescript(self, sql):
        self.end_reading()
        return super().executescript(sql)

    def end_reading(self):
        if self.reading:
            self.reading = False
            if self.in_transaction:
                self.commit()

    def close(self):
        self.reading = False  # отложенный end_reading не должен трогать закрытое соединение
        super().close()


def connect(path=None, timeout=5, shared=False):
    """timeout — сколько секунд ждать, если файл сейчас пишет кто-то другой (общие списки).
    shared — файл в общей сетевой папке (см. SharedConnection)."""
    # общий список при обрыве связи закрывается в фоне (иначе окно зависнет) — отсюда
    # check_same_thread=False; пользуется соединением всё равно только окно
    conn = sqlite3.connect(path or default_path(), timeout=timeout,
                           factory=SharedConnection if shared else sqlite3.Connection,
                           check_same_thread=not shared)
    # Таблица tasks — это как лист Excel: каждая строка — одна задача.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT    NOT NULL,
            done       INTEGER NOT NULL DEFAULT 0,
            created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    for name, decl in NEW_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {decl}")
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")

    # Статусы — это колонки канбан-доски. Их можно добавлять, удалять и перекрашивать.
    # is_done = 1 — задачи в этой колонке считаются выполненными.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS statuses (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT    NOT NULL,
            color    TEXT    NOT NULL,
            position INTEGER NOT NULL,
            is_done  INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    if not conn.execute("SELECT COUNT(*) FROM statuses").fetchone()[0]:
        conn.executemany(
            "INSERT INTO statuses (name, color, position, is_done) VALUES (?, ?, ?, ?)",
            [(name, color, i, done) for i, (name, color, done) in enumerate(DEFAULT_STATUSES)],
        )
    # Вложения (файлы и картинки) и комментарии к задачам. Файл хранится прямо в базе списка:
    # так он виден всем участникам общего списка и переносится вместе с задачей.
    # Содержимое (data) — последним столбцом: SQLite читает строку по порядку, и чтобы узнать
    # столбцы после большого файла, ему пришлось бы прочитать весь файл (в старых списках
    # data стоит раньше added_by и added_at — см. list_attachments).
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS attachments (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id  INTEGER NOT NULL,
            name     TEXT    NOT NULL,
            size     INTEGER NOT NULL,
            added_by TEXT,
            added_at TEXT    NOT NULL,
            data     BLOB    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS attachments_task ON attachments (task_id);
        CREATE TABLE IF NOT EXISTS comments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id    INTEGER NOT NULL,
            author     TEXT,
            text       TEXT    NOT NULL,
            created_at TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS comments_task ON comments (task_id);
        """
    )
    # Задачам без статуса (из старых версий) назначаем: выполненным — первую «выполненную»
    # колонку, остальным — первую невыполненную, кроме самой первой («Новая»), если она есть:
    # раньше такие задачи показывались как «В работе».
    if conn.execute("SELECT EXISTS (SELECT 1 FROM tasks WHERE status_id IS NULL)").fetchone()[0]:
        open_ids = [r[0] for r in conn.execute("SELECT id FROM statuses WHERE is_done = 0 ORDER BY position")]
        done_ids = [r[0] for r in conn.execute("SELECT id FROM statuses WHERE is_done = 1 ORDER BY position")]
        in_work = open_ids[1] if len(open_ids) > 1 else (open_ids or done_ids)[0]
        conn.execute("UPDATE tasks SET status_id = ? WHERE status_id IS NULL AND done = 0", (in_work,))
        conn.execute("UPDATE tasks SET status_id = ? WHERE status_id IS NULL AND done = 1",
                     ((done_ids or open_ids)[0],))
    if conn.in_transaction:  # что-то действительно поменяли (новая база, новые столбцы)
        conn.commit()
    return conn


# ---------- статусы (колонки доски) ----------

def list_statuses(conn):
    """[(id, name, color, is_done), ...] в порядке колонок слева направо."""
    return conn.execute("SELECT id, name, color, is_done FROM statuses ORDER BY position, id").fetchall()


def first_status(conn, done):
    """Первая колонка с нужным признаком «выполнено» (или None)."""
    row = conn.execute("SELECT id FROM statuses WHERE is_done = ? ORDER BY position, id LIMIT 1",
                       (int(done),)).fetchone()
    return row[0] if row else None


def add_status(conn, name, color):
    with conn:
        pos = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM statuses").fetchone()[0]
        return conn.execute("INSERT INTO statuses (name, color, position) VALUES (?, ?, ?)",
                            (name, color, pos)).lastrowid


def rename_status(conn, status_id, name):
    with conn:
        conn.execute("UPDATE statuses SET name = ? WHERE id = ?", (name, status_id))


def set_status_color(conn, status_id, color):
    with conn:
        conn.execute("UPDATE statuses SET color = ? WHERE id = ?", (color, status_id))


def set_status_done(conn, status_id, is_done, by=None):
    """Отметить колонку как «выполненную» (или нет) — вместе со всеми её задачами."""
    with conn:
        conn.execute("UPDATE statuses SET is_done = ? WHERE id = ?", (int(is_done), status_id))
        conn.execute(
            f"UPDATE tasks SET done = ?, done_at = {DONE_AT_SQL}, {TOUCH_SQL} WHERE status_id = ?",
            (int(is_done), int(is_done), by, status_id),
        )


def reorder_statuses(conn, ids):
    """Новый порядок колонок слева направо."""
    with conn:
        conn.executemany("UPDATE statuses SET position = ? WHERE id = ?",
                         [(pos, sid) for pos, sid in enumerate(ids)])


def move_status(conn, status_id, step):
    """Сдвигает колонку влево (step=-1) или вправо (step=1)."""
    ids = [r[0] for r in list_statuses(conn)]
    i = ids.index(status_id)
    j = i + step
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
        with conn:
            conn.executemany("UPDATE statuses SET position = ? WHERE id = ?",
                             [(pos, sid) for pos, sid in enumerate(ids)])


def delete_status(conn, status_id, move_to, by=None):
    """Удаляет колонку; её задачи переносятся в колонку move_to."""
    with conn:
        done = conn.execute("SELECT is_done FROM statuses WHERE id = ?", (move_to,)).fetchone()[0]
        conn.execute(f"UPDATE tasks SET status_id = ?, done = ?, done_at = {DONE_AT_SQL}, {TOUCH_SQL} "
                     "WHERE status_id = ?", (move_to, done, done, by, status_id))
        conn.execute("DELETE FROM statuses WHERE id = ?", (status_id,))


def count_in_status(conn, status_id):
    return conn.execute("SELECT COUNT(*) FROM tasks WHERE status_id = ?", (status_id,)).fetchone()[0]


# Время выполнения: ставится, когда задача становится выполненной, и стирается,
# когда перестаёт. Если задача уже была выполнена — время не меняется.
# (В UPDATE слева от «=» новые значения, а в выражениях — старые значения строки.)
DONE_AT_SQL = ("CASE WHEN ? = 0 THEN NULL WHEN done = 1 THEN done_at "
               "ELSE strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime') END")

# Отметка «изменено»: номер версии +1, время и кто изменил (параметр — имя или None)
TOUCH_SQL = ("version = version + 1, updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'), "
             "updated_by = ?")


def set_task_status(conn, task_id, status_id, by=None):
    """Переносит задачу в колонку; «выполнена» ли она — решает колонка.
    Возвращает True, если задача только что стала выполненной."""
    is_done = conn.execute("SELECT is_done FROM statuses WHERE id = ?", (status_id,)).fetchone()[0]
    was_done = conn.execute("SELECT done FROM tasks WHERE id = ?", (task_id,)).fetchone()[0]
    with conn:
        conn.execute(
            f"UPDATE tasks SET status_id = ?, done = ?, done_at = {DONE_AT_SQL}, {TOUCH_SQL} WHERE id = ?",
            (status_id, is_done, is_done, by, task_id),
        )
    return bool(is_done and not was_done)


def count_done_today(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE done = 1 AND date(done_at) = date('now', 'localtime')"
    ).fetchone()[0]


# ---------- настройки (например, выбранный вид: список или доска) ----------

def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def peek_setting(key, default=None):
    """Настройка из основного файла — без создания таблиц и без записи (до запуска окна:
    например, тема оформления). Нет файла или настройки — default."""
    if not DB_PATH.exists():
        return default
    try:
        conn = sqlite3.connect(DB_PATH.as_uri() + "?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return default
    return row[0] if row else default


def set_setting(conn, key, value):
    with conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


# Столбцы задачи в том порядке, в каком их ждёт программа (см. list_tasks).
# SQLite хранит время создания в UTC, поэтому переводим его в местное время.
TASK_COLUMNS_SQL = """
    SELECT id, title, done,
           strftime('%d.%m.%Y %H:%M', created_at, 'localtime'),
           due_at, remind_before, urgent, important, body, status_id
    FROM tasks
"""


def list_tasks(conn, done=None):
    """Возвращает задачи в порядке добавления:
    [(id, title, done, created, due_at, remind_before, urgent, important, body, status_id), ...].

    done=None — все задачи, True — только выполненные, False — только невыполненные.
    """
    sql = TASK_COLUMNS_SQL
    params = ()
    if done is not None:
        sql += " WHERE done = ?"
        params = (int(done),)
    return conn.execute(sql + " ORDER BY id", params).fetchall()


def get_task_row(conn, task_id):
    """Одна задача в том же виде, что строки list_tasks, или None."""
    return conn.execute(TASK_COLUMNS_SQL + " WHERE id = ?", (task_id,)).fetchone()


def get_task(conn, task_id):
    """Возвращает (title, due_at, remind_before, urgent, important, body) одной задачи."""
    return conn.execute(
        "SELECT title, due_at, remind_before, urgent, important, body FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()


def add_task(conn, title, status_id=None, created_by=None):
    """Новая задача попадает в первую колонку доски (обычно «Новая»)."""
    if status_id is None:
        status_id = list_statuses(conn)[0][0]
    # «with conn» сохраняет изменения в файл (commit) сразу после запроса.
    with conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, status_id, done, created_by) "
            "VALUES (?, ?, (SELECT is_done FROM statuses WHERE id = ?), ?)",
            (title, status_id, status_id, created_by),
        )
    return cur.lastrowid


def set_mail_id(conn, task_id, mail_id, mail_from=None):
    """Запоминает письмо, из которого создана задача, и адрес его отправителя."""
    with conn:
        conn.execute("UPDATE tasks SET mail_id = ?, mail_from = ? WHERE id = ?",
                     (mail_id or None, mail_from or None, task_id))


def mail_from(conn, task_id):
    """Адрес отправителя письма, из которого создана задача («» — задача не из письма)."""
    row = conn.execute("SELECT mail_from FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return (row[0] or "") if row else ""


def find_by_mail(conn, mail_id):
    """id задачи, созданной из этого письма (или None)."""
    if not mail_id:
        return None
    row = conn.execute("SELECT id FROM tasks WHERE mail_id = ? ORDER BY id LIMIT 1", (mail_id,)).fetchone()
    return row[0] if row else None


def update_task(conn, task_id, title, due_at, remind_before, urgent=False, important=False,
                body=None, by=None, version=None):
    """version — номер версии задачи, с которым открыли форму: если задачу с тех пор кто-то
    изменил, ничего не сохраняется и возвращается False (иначе True)."""
    # Если изменился срок или напоминание — напомнить нужно заново.
    # («IS» вместо «=» правильно сравнивает и пустые значения NULL.)
    # body=None — описание не трогаем.
    with conn:
        cur = conn.execute(
            f"""
            UPDATE tasks SET
                reminded = CASE WHEN due_at IS ? AND remind_before IS ? THEN reminded ELSE 0 END,
                title = ?, due_at = ?, remind_before = ?, urgent = ?, important = ?,
                body = COALESCE(?, body), {TOUCH_SQL}
            WHERE id = ? AND (? IS NULL OR version = ?)
            """,
            (due_at, remind_before, title, due_at, remind_before,
             int(urgent), int(important), body, by, task_id, version, version),
        )
    return cur.rowcount > 0


def set_done(conn, task_id, done, by=None):
    """Отметить выполненной — перенести в первую «выполненную» колонку, снять отметку —
    в первую невыполненную. Возвращает False, если подходящей колонки нет."""
    status_id = first_status(conn, done)
    if status_id is None:
        return False
    set_task_status(conn, task_id, status_id, by)
    return True


def set_assignee(conn, task_id, assignee, by=None):
    """Назначить исполнителя (None — снять)."""
    with conn:
        conn.execute(f"UPDATE tasks SET assignee = ?, {TOUCH_SQL} WHERE id = ?", (assignee, by, task_id))


def task_meta(conn, task_id):
    """Кто создал, исполнитель, кто и когда изменил, номер версии — или None, если задачи нет."""
    row = conn.execute("SELECT created_by, assignee, updated_by, updated_at, version FROM tasks "
                       "WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    return dict(zip(("author", "assignee", "updated_by", "updated_at", "version"), row))


def assigned_to(conn, user):
    """Невыполненные задачи, назначенные на user: [(id, title, кто назначил/изменил)]."""
    return conn.execute("SELECT id, title, updated_by FROM tasks WHERE done = 0 AND assignee = ?",
                        (user,)).fetchall()


def get_json_setting(conn, key, default):
    """Настройка-список или словарь (хранится как JSON)."""
    import json
    value = get_setting(conn, key)
    try:
        return json.loads(value) if value else default
    except ValueError:
        return default


def set_json_setting(conn, key, value):
    import json
    set_setting(conn, key, json.dumps(value, ensure_ascii=False))


def delete_task(conn, task_id):
    """Удаляет задачу вместе с её файлами и комментариями."""
    with conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        for table in ("attachments", "comments"):
            conn.execute(f"DELETE FROM {table} WHERE task_id = ?", (task_id,))


def drop_orphans(conn):
    """Убирает вложения и комментарии задач, которых больше нет."""
    for table in ("attachments", "comments"):
        conn.execute(f"DELETE FROM {table} WHERE task_id NOT IN (SELECT id FROM tasks)")


def count_examples(conn):
    return conn.execute("SELECT COUNT(*) FROM tasks WHERE is_example = 1").fetchone()[0]


def add_examples(conn, examples):
    """Добавляет примеры задач (см. examples.py).

    stage примера: "new" — первая колонка, "work" — вторая невыполненная (если есть),
    "done" — первая «выполненная» колонка.
    """
    statuses = list_statuses(conn)
    open_ids = [s[0] for s in statuses if not s[3]]
    done_ids = [s[0] for s in statuses if s[3]]
    first = statuses[0][0]
    targets = {
        "new": first,
        "work": open_ids[1] if len(open_ids) > 1 else (open_ids[0] if open_ids else first),
        "done": done_ids[0] if done_ids else first,
    }
    is_done = {s[0]: s[3] for s in statuses}
    with conn:
        for ex in examples:
            status_id = targets[ex.get("stage", "new")]
            task_id = conn.execute(
                """
                INSERT INTO tasks (title, done, status_id, due_at, remind_before, reminded,
                                   urgent, important, body, is_example)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (ex["title"], is_done[status_id], status_id, ex["due_at"], ex["remind_before"],
                 int(ex["reminded"]), int(ex.get("urgent", False)), int(ex.get("important", False)),
                 ex.get("body", "")),
            ).lastrowid
            for name, data in ex.get("files", []):
                conn.execute("INSERT INTO attachments (task_id, name, size, data, added_by, added_at) "
                             "VALUES (?, ?, ?, ?, NULL, ?)", (task_id, name, len(data), sqlite3.Binary(data),
                                                              now_text()))
            for text in ex.get("comments", []):
                conn.execute("INSERT INTO comments (task_id, author, text, created_at) VALUES (?, NULL, ?, ?)",
                             (task_id, text, now_text()))


def import_tasks(conn, tasks, created_by=None):
    """Добавляет задачи из файла (см. prepare_import в todoro.py). Номера им даются новые.
    created_at=None — создана сейчас."""
    is_done = {s[0]: s[3] for s in list_statuses(conn)}
    with conn:
        conn.executemany(
            """
            INSERT INTO tasks (title, body, status_id, done, due_at, remind_before, reminded,
                               urgent, important, created_at, created_by, assignee)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?)
            """,
            [(t["title"], t["body"], t["status_id"], is_done[t["status_id"]], t["due_at"],
              t["remind_before"], int(t["reminded"]), int(t["urgent"]), int(t["important"]),
              t["created_at"], t.get("created_by") or created_by, t.get("assignee")) for t in tasks],
        )


# ---------- списки задач ----------
# Реестр списков хранится в настройках основного файла: [{"id", "name", "file"}, ...].
# Личный список — это сам основной файл (file = None), остальные — файлы в LISTS_DIR.

def list_registry(prefs):
    lists = get_json_setting(prefs, "lists", [])
    if not any(item["id"] == PERSONAL for item in lists):
        lists.insert(0, {"id": PERSONAL, "name": "Личный", "file": None})
    return lists


def save_registry(prefs, lists):
    set_json_setting(prefs, "lists", lists)


def list_path(item):
    return DB_PATH if item["file"] is None else LISTS_DIR / item["file"]


def new_list_file():
    """Имя файла для нового списка (уникальное)."""
    import uuid
    LISTS_DIR.mkdir(parents=True, exist_ok=True)
    return f"{uuid.uuid4().hex[:12]}.db"


def move_task_to(src, task_id, dst):
    """Переносит задачу в другой список: в колонку с тем же названием, иначе в первую подходящую
    (выполненную задачу — в «выполненную» колонку). Возвращает id задачи в новом списке."""
    row = src.execute(
        """SELECT t.title, t.body, t.done, t.created_at, t.due_at, t.remind_before, t.reminded,
                  t.urgent, t.important, t.done_at, s.name, t.created_by, t.assignee,
                  t.mail_id, t.mail_from
           FROM tasks t LEFT JOIN statuses s ON s.id = t.status_id WHERE t.id = ?""",
        (task_id,),
    ).fetchone()
    (title, body, done, created, due_at, remind_before, reminded, urgent, important, done_at, status,
     created_by, assignee, mail_id, mail_from_) = row
    same = [sid for sid, name, _, is_done in list_statuses(dst)
            if name.strip().lower() == (status or "").strip().lower() and is_done == done]
    status_id = same[0] if same else first_status(dst, done)
    if status_id is None:  # нет колонки нужного вида — первая любая
        status_id = list_statuses(dst)[0][0]
    is_done = dst.execute("SELECT is_done FROM statuses WHERE id = ?", (status_id,)).fetchone()[0]
    with dst:
        new_id = dst.execute(
            """INSERT INTO tasks (title, body, done, created_at, due_at, remind_before, reminded,
                                  urgent, important, done_at, status_id, created_by, assignee,
                                  mail_id, mail_from)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, body, is_done, created, due_at, remind_before, reminded, urgent, important,
             done_at if is_done else None, status_id, created_by, assignee, mail_id, mail_from_),
        ).lastrowid
        # вложения и комментарии переезжают вместе с задачей
        dst.executemany(
            "INSERT INTO attachments (task_id, name, size, data, added_by, added_at) VALUES (?, ?, ?, ?, ?, ?)",
            [(new_id,) + tuple(r) for r in src.execute(
                "SELECT name, size, data, added_by, added_at FROM attachments WHERE task_id = ? ORDER BY id",
                (task_id,))])
        dst.executemany(
            "INSERT INTO comments (task_id, author, text, created_at) VALUES (?, ?, ?, ?)",
            [(new_id,) + tuple(r) for r in src.execute(
                "SELECT author, text, created_at FROM comments WHERE task_id = ? ORDER BY id", (task_id,))])
    delete_task(src, task_id)
    return new_id


# ---------- вложения и комментарии ----------

MAX_ATTACHMENT = 25 * 1024 * 1024  # больше — не принимаем: файл списка (и общая папка) раздуется


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_attachment(conn, task_id, name, data, by=None):
    with conn:
        return conn.execute(
            "INSERT INTO attachments (task_id, name, size, data, added_by, added_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, name, len(data), sqlite3.Binary(data), by, now_text()),
        ).lastrowid


# Сведения о вложениях: {(файл списка, id): (id, имя, размер, кто добавил, когда)}.
# Вложение после добавления не меняется (только удаляется), а номера не повторяются, поэтому
# сведения можно запомнить: в старых файлах списков, чтобы прочитать «кто и когда добавил»,
# SQLite читает всё содержимое файла — через VPN для большого файла это секунды при каждом
# обновлении карточки.
_attachment_info = {}


def list_attachments(conn, task_id):
    """[(id, имя, размер, кто добавил, когда), ...] — без содержимого файлов."""
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    ids = [row[0] for row in conn.execute("SELECT id FROM attachments WHERE task_id = ? ORDER BY id",
                                          (task_id,))]
    missing = [i for i in ids if (path, i) not in _attachment_info]
    if missing:
        marks = ", ".join("?" * len(missing))
        for row in conn.execute("SELECT id, name, size, added_by, added_at FROM attachments "
                                f"WHERE id IN ({marks})", missing):
            _attachment_info[(path, row[0])] = tuple(row)
    return [_attachment_info[(path, i)] for i in ids if (path, i) in _attachment_info]


def attachment_data(conn, attachment_id):
    row = conn.execute("SELECT data FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
    return bytes(row[0]) if row else None


def delete_attachment(conn, attachment_id):
    with conn:
        conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))


def add_comment(conn, task_id, text, by=None):
    with conn:
        return conn.execute("INSERT INTO comments (task_id, author, text, created_at) VALUES (?, ?, ?, ?)",
                            (task_id, by, text, now_text())).lastrowid


def list_comments(conn, task_id):
    """[(id, автор, текст, когда), ...] — по порядку написания."""
    return conn.execute("SELECT id, author, text, created_at FROM comments WHERE task_id = ? ORDER BY id",
                        (task_id,)).fetchall()


def delete_comment(conn, comment_id):
    with conn:
        conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))


def extras_counts(conn):
    """{id задачи: (сколько файлов, сколько комментариев)} — только у задач, где они есть."""
    counts = {}
    for table, index in (("attachments", 0), ("comments", 1)):
        for task_id, n in conn.execute(f"SELECT task_id, COUNT(*) FROM {table} GROUP BY task_id"):
            pair = counts.setdefault(task_id, [0, 0])
            pair[index] = n
    return {task_id: tuple(pair) for task_id, pair in counts.items()}


def mail_task_ids(conn):
    """id задач, созданных из писем Outlook."""
    return {row[0] for row in conn.execute("SELECT id FROM tasks WHERE mail_id IS NOT NULL")}


def task_people(conn):
    """({id: автор}, {id: исполнитель}) — одним запросом, только где они известны."""
    authors, assignees = {}, {}
    for task_id, author, assignee in conn.execute(
            "SELECT id, created_by, assignee FROM tasks "
            "WHERE created_by IS NOT NULL OR (assignee IS NOT NULL AND assignee <> '')"):
        if author:
            authors[task_id] = author
        if assignee:
            assignees[task_id] = assignee
    return authors, assignees


def count_tasks(conn):
    return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]


def delete_examples(conn):
    """Удаляет только примеры; задачи пользователя не трогает. Возвращает число удалённых."""
    with conn:
        count = conn.execute("DELETE FROM tasks WHERE is_example = 1").rowcount
        drop_orphans(conn)
    return count


def due_reminders(conn, now=None):
    """Невыполненные задачи, о которых пора напомнить: [(id, title, due_at), ...]."""
    now = now or datetime.now()
    rows = conn.execute(
        """
        SELECT id, title, due_at, remind_before FROM tasks
        WHERE done = 0 AND reminded = 0
          AND due_at IS NOT NULL AND remind_before IS NOT NULL
        ORDER BY due_at
        """
    ).fetchall()
    return [
        (task_id, title, due_at)
        for task_id, title, due_at, remind_before in rows
        if datetime.fromisoformat(due_at) - timedelta(minutes=remind_before) <= now
    ]


def shared_reminders(conn, user, now=None):
    """Напоминания в общем списке: о задачах, где user — исполнитель (или автор, если
    исполнителя нет).
    Флаг reminded в общем файле не трогаем (он один на всех) — кому уже напомнили, программа
    помнит у себя. Возвращает [(ключ, id, title, due_at), ...]; ключ меняется вместе со сроком."""
    now = now or datetime.now()
    rows = conn.execute(
        """
        SELECT id, title, due_at, remind_before FROM tasks
        WHERE done = 0 AND due_at IS NOT NULL AND remind_before IS NOT NULL
          AND COALESCE(NULLIF(assignee, ''), created_by) = ?
        """, (user,),
    ).fetchall()
    return [
        (f"{task_id}|{due_at}|{remind_before}", task_id, title, due_at)
        for task_id, title, due_at, remind_before in rows
        if datetime.fromisoformat(due_at) - timedelta(minutes=remind_before) <= now
    ]


def pending_tasks(conn, user=None, now=None):
    """Невыполненные задачи, у которых срок прошёл или уже пришло время напоминания:
    [(id, title, due_at), ...], ранние сроки — сверху. user — для общего списка: только задачи,
    где он исполнитель (или автор, если исполнителя нет)."""
    now = now or datetime.now()
    sql = """SELECT id, title, due_at, remind_before FROM tasks
             WHERE done = 0 AND due_at IS NOT NULL"""
    args = ()
    if user is not None:
        sql += " AND COALESCE(NULLIF(assignee, ''), created_by) = ?"
        args = (user,)
    rows = conn.execute(sql + " ORDER BY due_at, id", args).fetchall()
    return [
        (task_id, title, due_at)
        for task_id, title, due_at, remind_before in rows
        if datetime.fromisoformat(due_at) - timedelta(minutes=remind_before or 0) <= now
    ]


def mark_reminded(conn, task_id):
    with conn:
        conn.execute("UPDATE tasks SET reminded = 1 WHERE id = ?", (task_id,))
