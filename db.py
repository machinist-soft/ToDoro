"""Работа с базой данных SQLite: здесь хранятся задачи."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Файл базы лежит рядом с программой. Если его нет, SQLite создаст его сам.
DB_PATH = Path(__file__).with_name("todo.db")

# Столбцы, которые появились в новых версиях программы.
# В старую базу они добавляются автоматически, задачи при этом сохраняются.
NEW_COLUMNS = [
    ("due_at", "TEXT"),             # срок выполнения: 'ГГГГ-ММ-ДД ЧЧ:ММ' или NULL
    ("remind_before", "INTEGER"),   # за сколько минут до срока напомнить, NULL — не напоминать
    ("reminded", "INTEGER NOT NULL DEFAULT 0"),  # 1 — напоминание уже показано
    ("urgent", "INTEGER NOT NULL DEFAULT 0"),    # 1 — срочно
    ("important", "INTEGER NOT NULL DEFAULT 0"), # 1 — важно
    ("is_example", "INTEGER NOT NULL DEFAULT 0"),  # 1 — пример, добавленный кнопкой «Примеры»
]


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
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
    conn.commit()
    return conn


def list_tasks(conn, done=None):
    """Возвращает задачи в порядке добавления:
    [(id, title, done, created, due_at, remind_before, urgent, important), ...].

    done=None — все задачи, True — только выполненные, False — только невыполненные.
    """
    # SQLite хранит время создания в UTC, поэтому переводим его в местное время.
    sql = """
        SELECT id, title, done,
               strftime('%d.%m.%Y %H:%M', created_at, 'localtime'),
               due_at, remind_before, urgent, important
        FROM tasks
    """
    params = ()
    if done is not None:
        sql += " WHERE done = ?"
        params = (int(done),)
    return conn.execute(sql + " ORDER BY id", params).fetchall()


def get_task(conn, task_id):
    """Возвращает (title, due_at, remind_before, urgent, important) одной задачи."""
    return conn.execute(
        "SELECT title, due_at, remind_before, urgent, important FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()


def add_task(conn, title):
    # «with conn» сохраняет изменения в файл (commit) сразу после запроса.
    with conn:
        cur = conn.execute("INSERT INTO tasks (title) VALUES (?)", (title,))
    return cur.lastrowid


def update_task(conn, task_id, title, due_at, remind_before, urgent=False, important=False):
    # Если изменился срок или напоминание — напомнить нужно заново.
    # («IS» вместо «=» правильно сравнивает и пустые значения NULL.)
    with conn:
        conn.execute(
            """
            UPDATE tasks SET
                reminded = CASE WHEN due_at IS ? AND remind_before IS ? THEN reminded ELSE 0 END,
                title = ?, due_at = ?, remind_before = ?, urgent = ?, important = ?
            WHERE id = ?
            """,
            (due_at, remind_before, title, due_at, remind_before,
             int(urgent), int(important), task_id),
        )


def set_done(conn, task_id, done):
    with conn:
        conn.execute("UPDATE tasks SET done = ? WHERE id = ?", (int(done), task_id))


def delete_task(conn, task_id):
    with conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def count_examples(conn):
    return conn.execute("SELECT COUNT(*) FROM tasks WHERE is_example = 1").fetchone()[0]


def add_examples(conn, examples):
    """Добавляет примеры задач (см. examples.py)."""
    with conn:
        conn.executemany(
            """
            INSERT INTO tasks (title, done, due_at, remind_before, reminded,
                               urgent, important, is_example)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            [
                (ex["title"], int(ex.get("done", False)), ex["due_at"], ex["remind_before"],
                 int(ex["reminded"]), int(ex.get("urgent", False)), int(ex.get("important", False)))
                for ex in examples
            ],
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
