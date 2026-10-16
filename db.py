"""Работа с базой данных SQLite: здесь хранятся задачи."""
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Файл базы лежит рядом с программой. Если его нет, SQLite создаст его сам.
DB_PATH = Path(__file__).with_name("todoro.db")
OLD_DB_PATH = Path(__file__).with_name("todo.db")  # так база называлась в первых версиях


def default_path():
    """todoro.db; старый todo.db при первом запуске переименовывается.
    Если старый файл сейчас занят (открыт другой копией программы) — работаем с ним."""
    if not DB_PATH.exists() and OLD_DB_PATH.exists():
        try:
            os.replace(OLD_DB_PATH, DB_PATH)
        except OSError:
            return OLD_DB_PATH
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
]

# Статусы по умолчанию: (название, цвет, «задачи здесь выполнены»)
DEFAULT_STATUSES = [
    ("Новая", "#3b82f6", 0),
    ("В работе", "#f59e0b", 0),
    ("Выполнено", "#22c55e", 1),
]


def connect(path=None):
    conn = sqlite3.connect(path or default_path())
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
    # Задачам без статуса (из старых версий) назначаем: выполненным — первую «выполненную»
    # колонку, остальным — первую невыполненную, кроме самой первой («Новая»), если она есть:
    # раньше такие задачи показывались как «В работе».
    open_ids = [r[0] for r in conn.execute("SELECT id FROM statuses WHERE is_done = 0 ORDER BY position")]
    done_ids = [r[0] for r in conn.execute("SELECT id FROM statuses WHERE is_done = 1 ORDER BY position")]
    in_work = open_ids[1] if len(open_ids) > 1 else (open_ids or done_ids)[0]
    conn.execute("UPDATE tasks SET status_id = ? WHERE status_id IS NULL AND done = 0", (in_work,))
    conn.execute("UPDATE tasks SET status_id = ? WHERE status_id IS NULL AND done = 1",
                 ((done_ids or open_ids)[0],))
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
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


def set_status_done(conn, status_id, is_done):
    """Отметить колонку как «выполненную» (или нет) — вместе со всеми её задачами."""
    with conn:
        conn.execute("UPDATE statuses SET is_done = ? WHERE id = ?", (int(is_done), status_id))
        conn.execute(
            f"UPDATE tasks SET done = ?, done_at = {DONE_AT_SQL} WHERE status_id = ?",
            (int(is_done), int(is_done), status_id),
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


def delete_status(conn, status_id, move_to):
    """Удаляет колонку; её задачи переносятся в колонку move_to."""
    with conn:
        done = conn.execute("SELECT is_done FROM statuses WHERE id = ?", (move_to,)).fetchone()[0]
        conn.execute(f"UPDATE tasks SET status_id = ?, done = ?, done_at = {DONE_AT_SQL} "
                     "WHERE status_id = ?", (move_to, done, done, status_id))
        conn.execute("DELETE FROM statuses WHERE id = ?", (status_id,))


def count_in_status(conn, status_id):
    return conn.execute("SELECT COUNT(*) FROM tasks WHERE status_id = ?", (status_id,)).fetchone()[0]


# Время выполнения: ставится, когда задача становится выполненной, и стирается,
# когда перестаёт. Если задача уже была выполнена — время не меняется.
# (В UPDATE слева от «=» новые значения, а в выражениях — старые значения строки.)
DONE_AT_SQL = ("CASE WHEN ? = 0 THEN NULL WHEN done = 1 THEN done_at "
               "ELSE strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime') END")


def set_task_status(conn, task_id, status_id):
    """Переносит задачу в колонку; «выполнена» ли она — решает колонка.
    Возвращает True, если задача только что стала выполненной."""
    is_done = conn.execute("SELECT is_done FROM statuses WHERE id = ?", (status_id,)).fetchone()[0]
    was_done = conn.execute("SELECT done FROM tasks WHERE id = ?", (task_id,)).fetchone()[0]
    with conn:
        conn.execute(
            f"UPDATE tasks SET status_id = ?, done = ?, done_at = {DONE_AT_SQL} WHERE id = ?",
            (status_id, is_done, is_done, task_id),
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


def set_setting(conn, key, value):
    with conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


def list_tasks(conn, done=None):
    """Возвращает задачи в порядке добавления:
    [(id, title, done, created, due_at, remind_before, urgent, important, body, status_id), ...].

    done=None — все задачи, True — только выполненные, False — только невыполненные.
    """
    # SQLite хранит время создания в UTC, поэтому переводим его в местное время.
    sql = """
        SELECT id, title, done,
               strftime('%d.%m.%Y %H:%M', created_at, 'localtime'),
               due_at, remind_before, urgent, important, body, status_id
        FROM tasks
    """
    params = ()
    if done is not None:
        sql += " WHERE done = ?"
        params = (int(done),)
    return conn.execute(sql + " ORDER BY id", params).fetchall()


def get_task(conn, task_id):
    """Возвращает (title, due_at, remind_before, urgent, important, body) одной задачи."""
    return conn.execute(
        "SELECT title, due_at, remind_before, urgent, important, body FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()


def add_task(conn, title, status_id=None):
    """Новая задача попадает в первую колонку доски (обычно «Новая»)."""
    if status_id is None:
        status_id = list_statuses(conn)[0][0]
    # «with conn» сохраняет изменения в файл (commit) сразу после запроса.
    with conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, status_id, done) "
            "VALUES (?, ?, (SELECT is_done FROM statuses WHERE id = ?))",
            (title, status_id, status_id),
        )
    return cur.lastrowid


def update_task(conn, task_id, title, due_at, remind_before, urgent=False, important=False,
                body=None):
    # Если изменился срок или напоминание — напомнить нужно заново.
    # («IS» вместо «=» правильно сравнивает и пустые значения NULL.)
    # body=None — описание не трогаем.
    with conn:
        conn.execute(
            """
            UPDATE tasks SET
                reminded = CASE WHEN due_at IS ? AND remind_before IS ? THEN reminded ELSE 0 END,
                title = ?, due_at = ?, remind_before = ?, urgent = ?, important = ?,
                body = COALESCE(?, body)
            WHERE id = ?
            """,
            (due_at, remind_before, title, due_at, remind_before,
             int(urgent), int(important), body, task_id),
        )


def set_done(conn, task_id, done):
    """Отметить выполненной — перенести в первую «выполненную» колонку, снять отметку —
    в первую невыполненную. Возвращает False, если подходящей колонки нет."""
    status_id = first_status(conn, done)
    if status_id is None:
        return False
    set_task_status(conn, task_id, status_id)
    return True


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
    with conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


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
    rows = []
    for ex in examples:
        status_id = targets[ex.get("stage", "new")]
        rows.append((ex["title"], is_done[status_id], status_id, ex["due_at"], ex["remind_before"],
                     int(ex["reminded"]), int(ex.get("urgent", False)), int(ex.get("important", False)),
                     ex.get("body", "")))
    with conn:
        conn.executemany(
            """
            INSERT INTO tasks (title, done, status_id, due_at, remind_before, reminded,
                               urgent, important, body, is_example)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            rows,
        )


def import_tasks(conn, tasks):
    """Добавляет задачи из файла (см. prepare_import в todoro.py). Номера им даются новые.
    created_at=None — создана сейчас."""
    is_done = {s[0]: s[3] for s in list_statuses(conn)}
    with conn:
        conn.executemany(
            """
            INSERT INTO tasks (title, body, status_id, done, due_at, remind_before, reminded,
                               urgent, important, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """,
            [(t["title"], t["body"], t["status_id"], is_done[t["status_id"]], t["due_at"],
              t["remind_before"], int(t["reminded"]), int(t["urgent"]), int(t["important"]),
              t["created_at"]) for t in tasks],
        )


def delete_examples(conn):
    """Удаляет только примеры; задачи пользователя не трогает. Возвращает число удалённых."""
    with conn:
        return conn.execute("DELETE FROM tasks WHERE is_example = 1").rowcount


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


def mark_reminded(conn, task_id):
    with conn:
        conn.execute("UPDATE tasks SET reminded = 1 WHERE id = ?", (task_id,))
