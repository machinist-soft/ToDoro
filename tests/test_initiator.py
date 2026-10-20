"""«Инициатор» задачи в общих списках: столбец initiator в базе (NULL — инициатор = автор),
поле в форме, сохранение правки, CSV, письмо, связь с телефоном. Временные файлы; окна Tk —
за краем экрана; данные пользователя не трогаются."""

import gc
import json
import shutil
import sqlite3
import sys
import tempfile
import threading
import tkinter as tk
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import phone  # noqa: E402
import team  # noqa: E402
from tests.test_core import TempDir  # noqa: E402

OFFSCREEN = "+-5000+-5000"
STATUSES = [(1, "Новая", "#3b82f6", 0)]


def version(conn, task_id):
    return db.task_meta(conn, task_id)["version"]


class InitiatorDbTests(TempDir):
    def test_old_database_gets_column(self):
        """Список старой версии (без столбца initiator) открывается, задачи на месте,
        инициатор — автор."""
        path = self.dir / "old.db"
        old = sqlite3.connect(path)
        old.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                    "done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "created_by TEXT)")
        old.execute("INSERT INTO tasks (title, created_by) VALUES ('старая', 'Анна')")
        old.execute("INSERT INTO tasks (title) VALUES ('без автора')")
        old.commit()
        old.close()
        conn = db.connect(path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        self.assertIn("initiator", columns)
        meta = db.task_meta(conn, 1)
        self.assertEqual((meta["author"], meta["initiator"]), ("Анна", "Анна"))
        self.assertIsNone(db.task_meta(conn, 2)["initiator"])
        self.assertEqual(db.task_people(conn), ({1: "Анна"}, {}))
        conn.close()

    def test_set_initiator_and_meta(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        db.set_initiator(conn, tid, "  Мария  ", by="Анна")
        meta = db.task_meta(conn, tid)
        self.assertEqual((meta["author"], meta["initiator"], meta["updated_by"]),
                         ("Анна", "Мария", "Анна"))
        stored = conn.execute("SELECT initiator FROM tasks WHERE id = ?", (tid,)).fetchone()[0]
        self.assertEqual(stored, "Мария")  # пробелы по краям убраны

    def test_empty_initiator_returns_to_author(self):
        """None, пустая строка и одни пробелы — в базе NULL, инициатор снова автор."""
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        for empty in (None, "", "   "):
            db.set_initiator(conn, tid, "Мария")
            db.set_initiator(conn, tid, empty)
            stored = conn.execute("SELECT initiator FROM tasks WHERE id = ?", (tid,)).fetchone()[0]
            self.assertIsNone(stored, repr(empty))
            self.assertEqual(db.task_meta(conn, tid)["initiator"], "Анна")

    def test_empty_string_in_file_means_author(self):
        """Пустая строка, записанная в файл кем-то в обход set_initiator, — тоже «автор»."""
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        with conn:
            conn.execute("UPDATE tasks SET initiator = '' WHERE id = ?", (tid,))
        self.assertEqual(db.task_meta(conn, tid)["initiator"], "Анна")
        self.assertEqual(db.task_people(conn)[0], {tid: "Анна"})

    def test_set_initiator_bumps_version(self):
        """Смена инициатора — тоже правка: чужая форма, открытая раньше, не затирает её."""
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        opened = version(conn, tid)  # Анна открыла форму
        db.set_initiator(conn, tid, "Мария", by="Борис")  # Борис сменил инициатора
        self.assertEqual(version(conn, tid), opened + 1)
        self.assertFalse(db.update_task(conn, tid, "отчёт v2", None, None, by="Анна", version=opened))
        self.assertEqual(db.task_meta(conn, tid)["updated_by"], "Борис")

    def test_set_initiator_missing_task(self):
        conn = db.connect(self.dir / "a.db")
        db.set_initiator(conn, 999, "Мария")  # задачу уже удалили — не падает
        self.assertIsNone(db.task_meta(conn, 999))

    def test_task_people(self):
        conn = db.connect(self.dir / "a.db")
        plain = db.add_task(conn, "автор без инициатора", created_by="Анна")
        manual = db.add_task(conn, "инициатор указан", created_by="Анна")
        db.set_initiator(conn, manual, "Мария")
        orphan = db.add_task(conn, "без автора, с инициатором")
        db.set_initiator(conn, orphan, "Директор")
        assigned = db.add_task(conn, "только исполнитель")
        db.set_assignee(conn, assigned, "Борис")
        db.add_task(conn, "совсем пустая")
        self.assertEqual(db.task_people(conn),
                         ({plain: "Анна", manual: "Мария", orphan: "Директор"}, {assigned: "Борис"}))

    def test_long_initiator(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "x", created_by="Анна")
        name = "Я" * 10_000
        db.set_initiator(conn, tid, name)
        self.assertEqual(db.task_meta(conn, tid)["initiator"], name)

    def test_move_task_keeps_initiator(self):
        src, dst = db.connect(self.dir / "a.db"), db.connect(self.dir / "b.db")
        tid = db.add_task(src, "отчёт", created_by="Анна")
        db.set_initiator(src, tid, "Мария")
        plain = db.add_task(src, "без инициатора", created_by="Анна")
        new_id = db.move_task_to(src, tid, dst)
        meta = db.task_meta(dst, new_id)
        self.assertEqual((meta["author"], meta["initiator"]), ("Анна", "Мария"))
        new_plain = db.move_task_to(src, plain, dst)
        stored = dst.execute("SELECT initiator FROM tasks WHERE id = ?", (new_plain,)).fetchone()[0]
        self.assertIsNone(stored)  # «инициатор = автор» так и остаётся, без копии имени
        self.assertEqual(db.task_meta(dst, new_plain)["initiator"], "Анна")

    def test_move_task_into_old_list_file(self):
        """Перенос в файл, созданный старой версией (без столбца): connect его дополнит."""
        path = self.dir / "old.db"
        old = sqlite3.connect(path)
        old.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                    "done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        old.commit()
        old.close()
        src, dst = db.connect(self.dir / "a.db"), db.connect(path)
        tid = db.add_task(src, "отчёт", created_by="Анна")
        db.set_initiator(src, tid, "Мария")
        self.assertEqual(db.task_meta(dst, db.move_task_to(src, tid, dst))["initiator"], "Мария")

    def test_reminders_and_mine_ignore_initiator(self):
        """Кому напоминать и «мои задачи» — по-прежнему исполнитель, иначе автор; инициатор
        не в счёт."""
        conn = db.connect(self.dir / "a.db")
        due = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        db.update_task(conn, tid, "отчёт", due, 60, by="Анна")
        db.set_initiator(conn, tid, "Мария")
        self.assertEqual([r[1] for r in db.shared_reminders(conn, "Анна")], [tid])
        self.assertEqual(db.shared_reminders(conn, "Мария"), [])
        self.assertEqual([r[0] for r in db.pending_tasks(conn, "Анна")], [tid])
        self.assertEqual(db.pending_tasks(conn, "Мария"), [])
        db.set_assignee(conn, tid, "Борис")
        self.assertEqual([r[1] for r in db.shared_reminders(conn, "Борис")], [tid])
        self.assertEqual(db.shared_reminders(conn, "Анна"), [])


class InitiatorPhoneTests(unittest.TestCase):
    """В задаче для телефона: "author" — кто создал (по нему телефон решает, кому напоминать),
    "initiator" — действующий инициатор."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-phone-"))
        self.addCleanup(self.remove_dir)
        self.prefs_path = self.dir / "todoro.db"
        prefs = db.connect(self.prefs_path)
        db.set_setting(prefs, "user_name", "Аня")
        self.token = phone.new_token(prefs)
        folder = self.dir / "share"
        group = team.Team(folder)
        self.item = group.add_list("Команда", "Боря")
        self.list_path = group.path(self.item)
        group.close()
        db.set_setting(prefs, "shared_folder", str(folder))
        prefs.close()
        self.server = phone.Server(0, self.token, self.prefs_path)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def remove_dir(self):
        gc.collect()
        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, method, path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(self.base + path, data=body, method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def synced(self, task_id):
        answer = self.call("GET", "/api/v1/sync")[1]
        return next(t for t in answer["views"][self.item["id"]]["tasks"] if t["id"] == task_id)

    def test_initiator_defaults_to_author(self):
        task = self.call("POST", f"/api/v1/lists/{self.item['id']}/tasks", {"title": "Позвонить"})[1]["task"]
        self.assertEqual((task["author"], task["initiator"]), ("Аня", "Аня"))
        self.assertEqual(self.synced(task["id"])["initiator"], "Аня")

    def test_initiator_set_on_pc(self):
        task = self.call("POST", f"/api/v1/lists/{self.item['id']}/tasks", {"title": "Позвонить"})[1]["task"]
        conn = db.connect(self.list_path)
        db.set_initiator(conn, task["id"], "Директор", by="Боря")
        conn.close()
        synced = self.synced(task["id"])
        self.assertEqual((synced["author"], synced["initiator"]), ("Аня", "Директор"))
        one = self.call("GET", f"/api/v1/lists/{self.item['id']}")[1]
        found = next(t for t in one["tasks"] if t["id"] == task["id"])
        self.assertEqual((found["author"], found["initiator"]), ("Аня", "Директор"))

    def test_phone_edit_keeps_initiator(self):
        """Правка с телефона (он про инициатора не знает) инициатора не сбрасывает,
        а присланное "initiator" ничего не меняет."""
        task = self.call("POST", f"/api/v1/lists/{self.item['id']}/tasks", {"title": "Позвонить"})[1]["task"]
        conn = db.connect(self.list_path)
        db.set_initiator(conn, task["id"], "Директор")
        conn.close()
        status, answer = self.call("PATCH", f"/api/v1/lists/{self.item['id']}/tasks/{task['id']}",
                                   {"title": "Позвонить в банк", "initiator": "Хакер"})
        self.assertEqual(status, 200)
        self.assertEqual((answer["task"]["title"], answer["task"]["initiator"]),
                         ("Позвонить в банк", "Директор"))

    def test_personal_list_task_has_field(self):
        task = self.call("POST", "/api/v1/lists/personal/tasks", {"title": "Хлеб"})[1]["task"]
        self.assertIn("initiator", task)
        self.assertEqual(task["initiator"], task["author"])


class InitiatorAppTests(TempDir):
    """Функции todoro.py без окна: CSV, письмо, сохранение правки."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def fake_app(self, conn, shared=True, user="Анна"):
        """Минимум TodoApp, нужный apply_edit/form_data/people/resolve_conflict."""
        T = self.T
        app = SimpleNamespace(conn=conn, list_id="team" if shared else None, refreshed=[],
                              unit_names={})
        app.created_by = lambda: user if shared else None
        app.members = lambda: ["Анна", "Борис"] if shared else None
        app.current_list = lambda: {"shared": shared, "name": "Команда"}
        app.task_info = lambda task_id: {"status_id": db.get_task_row(conn, task_id)[-1]}
        app.celebrate = lambda task_id: None
        app.refresh = lambda select_id=None: app.refreshed.append(select_id)
        app.user_name = lambda: user
        app.CHANGED_NAMES = T.TodoApp.CHANGED_NAMES
        for name in ("apply_edit", "form_data", "people", "resolve_conflict", "create_from_mail"):
            setattr(app, name, getattr(T.TodoApp, name).__get__(app))
        app.mail_ids = set()
        app.attach = lambda task_id, files: None
        return app

    def result(self, conn, task_id, **changes):
        title, due_at, remind_before, urgent, important, body = db.get_task(conn, task_id)
        meta = db.task_meta(conn, task_id)
        data = dict(title=title, due_at=due_at, remind_before=remind_before, urgent=urgent,
                    important=important, body=body, status_id=db.get_task_row(conn, task_id)[-1],
                    assignee=meta["assignee"], initiator=meta["initiator"])
        data.update(changes)
        return data

    def stored(self, conn, task_id):
        return conn.execute("SELECT initiator FROM tasks WHERE id = ?", (task_id,)).fetchone()[0]

    # --- CSV ---

    def test_csv_export_shows_initiator(self):
        conn = db.connect(self.dir / "a.db")
        manual = db.add_task(conn, "отчёт", created_by="Анна")
        db.set_initiator(conn, manual, "Мария")
        plain = db.add_task(conn, "звонок", created_by="Борис")
        nobody = db.add_task(conn, "ничья")
        columns = self.T.CSV_COLUMNS
        self.assertEqual(columns[columns.index("Создана"):columns.index("Исполнитель") + 1],
                         ["Создана", "Автор", "Инициатор", "Исполнитель"])
        author, initiator = columns.index("Автор"), columns.index("Инициатор")
        rows = {r[0]: r for r in self.T.export_rows(conn)}
        self.assertTrue(all(len(r) == len(columns) for r in rows.values()))
        self.assertEqual((rows[manual][author], rows[manual][initiator]), ("Анна", "Мария"))
        self.assertEqual((rows[plain][author], rows[plain][initiator]), ("Борис", "Борис"))
        self.assertEqual((rows[nobody][author], rows[nobody][initiator]), ("", ""))
        conn.close()

    def test_csv_import_by_initiator_and_author(self):
        """При импорте «Инициатор» идёт в инициатора, «Автор» — в автора (created_by);
        заголовки — в любом регистре и с пробелами."""
        conn = db.connect(self.dir / "a.db")
        for header, field, other in (("Инициатор", "initiator", "created_by"),
                                     (" инициатор ", "initiator", "created_by"),
                                     ("Автор", "created_by", "initiator"),
                                     (" АВТОР ", "created_by", "initiator")):
            path = self.dir / "x.csv"
            path.write_text(f"Заголовок;{header}\nОтчёт;Мария\n", encoding="utf-8-sig")
            tasks, notes = self.T.prepare_import(conn, self.T.read_csv(path))
            self.assertEqual(notes, [], header)
            self.assertEqual(tasks[0][field], "Мария", header)
            self.assertIsNone(tasks[0][other], header)
        conn.close()

    def test_csv_both_columns(self):
        """В файле есть и «Автор», и «Инициатор» — каждый попадает на своё место."""
        conn = db.connect(self.dir / "a.db")
        path = self.dir / "x.csv"
        path.write_text("Заголовок;Автор;Инициатор\nОтчёт;Анна;Директор\n", encoding="utf-8-sig")
        tasks, _ = self.T.prepare_import(conn, self.T.read_csv(path))
        db.import_tasks(conn, tasks, created_by="Борис")
        new_id = conn.execute("SELECT MAX(id) FROM tasks").fetchone()[0]
        meta = db.task_meta(conn, new_id)
        self.assertEqual((meta["author"], meta["initiator"]), ("Анна", "Директор"))
        conn.close()

    def test_csv_old_file_with_author_only(self):
        """Файл старой версии — только столбец «Автор»: значение становится автором (created_by),
        инициатор не записывается, т. е. им считается тот же автор."""
        conn = db.connect(self.dir / "a.db")
        path = self.dir / "old.csv"
        path.write_text("№;Заголовок;Описание;Статус;Приоритет;Срок;Напомнить;Создана;Автор;Исполнитель\n"
                        "1;Отчёт;;Новая;Обычный;;;;Анна;\n", encoding="utf-8-sig")
        tasks, notes = self.T.prepare_import(conn, self.T.read_csv(path))
        self.assertEqual(notes, [])
        self.assertEqual((tasks[0]["created_by"], tasks[0]["initiator"]), ("Анна", None))
        db.import_tasks(conn, tasks, created_by="Борис")
        new_id = conn.execute("SELECT MAX(id) FROM tasks").fetchone()[0]
        meta = db.task_meta(conn, new_id)
        self.assertEqual((meta["author"], meta["initiator"]), ("Анна", "Анна"))
        self.assertIsNone(self.stored(conn, new_id))
        conn.close()

    def test_csv_roundtrip_initiator(self):
        """Экспорт → импорт другим участником: автор сохраняется, инициатор тоже; у задачи
        без отдельного инициатора столбец initiator остаётся NULL, а задача без автора
        получает автором того, кто импортирует."""
        conn = db.connect(self.dir / "a.db")
        manual = db.add_task(conn, "отчёт", created_by="Анна")
        db.set_initiator(conn, manual, "Мария")
        db.add_task(conn, "звонок", created_by="Анна")
        db.add_task(conn, "ничья")
        path = self.dir / "x.csv"
        self.T.write_csv(path, self.T.CSV_COLUMNS, self.T.export_rows(conn))
        tasks, notes = self.T.prepare_import(conn, self.T.read_csv(path))
        self.assertEqual(notes, [])
        other = db.connect(self.dir / "b.db")
        db.import_tasks(other, tasks, created_by="Борис")
        got = {title: (author, initiator) for title, author, initiator in other.execute(
            "SELECT title, created_by, initiator FROM tasks")}
        self.assertEqual(got, {"отчёт": ("Анна", "Мария"), "звонок": ("Анна", None),
                               "ничья": ("Борис", None)})
        conn.close()
        other.close()

    def test_import_initiator_equal_to_author_stored_as_null(self):
        """Инициатор в файле совпадает с автором (или, без автора, с тем, кто импортирует) —
        в базе NULL; другое имя — записывается."""
        conn = db.connect(self.dir / "a.db")
        path = self.dir / "x.csv"
        path.write_text("Заголовок;Автор;Инициатор\nА;Анна;Анна\nБ;;Борис\nВ;;Мария\n",
                        encoding="utf-8-sig")
        tasks, _ = self.T.prepare_import(conn, self.T.read_csv(path))
        db.import_tasks(conn, tasks, created_by="Борис")
        got = {title: (author, initiator) for title, author, initiator in conn.execute(
            "SELECT title, created_by, initiator FROM tasks")}
        self.assertEqual(got, {"А": ("Анна", None), "Б": ("Борис", None), "В": ("Борис", "Мария")})
        conn.close()

    def test_csv_roundtrip_keeps_reminders(self):
        """Автор «Анна», инициатор «Директор», без исполнителя, со сроком → экспорт → импорт
        Анной: напоминание по-прежнему Анне, видимый инициатор — «Директор»."""
        conn = db.connect(self.dir / "a.db")
        due = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        db.update_task(conn, tid, "отчёт", due, 60, by="Анна")
        db.set_initiator(conn, tid, "Директор")
        path = self.dir / "x.csv"
        self.T.write_csv(path, self.T.CSV_COLUMNS, self.T.export_rows(conn))
        tasks, notes = self.T.prepare_import(conn, self.T.read_csv(path))
        self.assertEqual(notes, [])
        other = db.connect(self.dir / "b.db")
        db.import_tasks(other, tasks, created_by="Анна")
        new_id = other.execute("SELECT MAX(id) FROM tasks").fetchone()[0]
        self.assertEqual([r[1] for r in db.shared_reminders(other, "Анна")], [new_id])
        self.assertEqual(db.shared_reminders(other, "Директор"), [])
        self.assertEqual(db.task_meta(other, new_id)["initiator"], "Директор")
        self.assertEqual(db.task_people(other)[0], {new_id: "Директор"})
        conn.close()
        other.close()

    # --- письмо ---

    def test_email_has_initiator_line(self):
        _, text = self.T.build_email(5, "Отчёт", "Новая", "", "", "", "16.10", False,
                                     author="Мария", assignee="Борис")
        self.assertIn("Инициатор: Мария", text)
        self.assertIn("Исполнитель: Борис", text)
        self.assertNotIn("автор", text.lower())
        _, text = self.T.build_email(5, "Отчёт", "Новая", "", "", "", "16.10", False)
        self.assertNotIn("Инициатор", text)

    # --- карточка и форма ---

    def test_form_data_and_people(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        app = self.fake_app(conn)
        self.assertEqual(app.form_data(tid)["initiator"], "Анна")
        self.assertEqual(app.people(tid)["author"], "Анна")
        db.set_initiator(conn, tid, "Мария")
        self.assertEqual(app.form_data(tid)["initiator"], "Мария")
        self.assertEqual(app.people(tid)["author"], "Мария")
        conn.close()

    # --- apply_edit ---

    def test_apply_edit_changes_initiator(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        app = self.fake_app(conn, user="Борис")
        before = version(conn, tid)
        self.assertTrue(app.apply_edit(tid, self.result(conn, tid, initiator="Мария"), version=before))
        meta = db.task_meta(conn, tid)
        self.assertEqual((meta["author"], meta["initiator"], meta["updated_by"]), ("Анна", "Мария", "Борис"))
        self.assertEqual(meta["version"], before + 2)  # правка полей + смена инициатора

    def test_apply_edit_clear_returns_to_author(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        db.set_initiator(conn, tid, "Мария")
        app = self.fake_app(conn)
        app.apply_edit(tid, self.result(conn, tid, initiator=None))
        self.assertIsNone(self.stored(conn, tid))
        self.assertEqual(db.task_meta(conn, tid)["initiator"], "Анна")

    def test_apply_edit_back_to_author_name_stores_null(self):
        """Инициатора «Мария» вернули на имя автора «Анна» — в базе NULL, а не «Анна»: если
        автора потом поменяют, инициатор пойдёт за ним."""
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        db.set_initiator(conn, tid, "Мария")
        app = self.fake_app(conn, user="Борис")
        before = version(conn, tid)
        app.apply_edit(tid, self.result(conn, tid, initiator="Анна"))
        self.assertIsNone(self.stored(conn, tid))
        meta = db.task_meta(conn, tid)
        self.assertEqual((meta["initiator"], meta["updated_by"], meta["version"]), ("Анна", "Борис", before + 2))

    def test_apply_edit_without_change_does_not_touch_initiator(self):
        """Поле не трогали (в нём автор) или очистили, когда инициатор и так автор, — в базу
        имя не записывается, лишней версии нет."""
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        app = self.fake_app(conn)
        for initiator in ("Анна", None):
            before = version(conn, tid)
            app.apply_edit(tid, self.result(conn, tid, initiator=initiator))
            self.assertEqual(version(conn, tid), before + 1, initiator)  # только update_task
            self.assertIsNone(self.stored(conn, tid))

    def test_apply_edit_same_manual_initiator(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        db.set_initiator(conn, tid, "Мария")
        app = self.fake_app(conn)
        before = version(conn, tid)
        app.apply_edit(tid, self.result(conn, tid, initiator="Мария"))
        self.assertEqual(version(conn, tid), before + 1)
        self.assertEqual(self.stored(conn, tid), "Мария")

    def test_apply_edit_task_without_author(self):
        """Задача без автора (например, из личного списка): пустое поле ничего не пишет,
        имя — записывается."""
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт")
        app = self.fake_app(conn)
        before = version(conn, tid)
        app.apply_edit(tid, self.result(conn, tid, initiator=None))
        self.assertEqual(version(conn, tid), before + 1)
        app.apply_edit(tid, self.result(conn, tid, initiator="Мария"))
        self.assertEqual(db.task_meta(conn, tid)["initiator"], "Мария")

    def test_apply_edit_personal_list_ignores_initiator(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт")
        app = self.fake_app(conn, shared=False)
        app.apply_edit(tid, self.result(conn, tid, initiator="Мария"))
        self.assertIsNone(self.stored(conn, tid))

    def test_apply_edit_conflict_keeps_initiator(self):
        """Устаревшая форма (версия не та) не сохраняет и инициатора."""
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        app = self.fake_app(conn)
        opened = version(conn, tid)
        db.set_initiator(conn, tid, "Директор", by="Борис")
        self.assertFalse(app.apply_edit(tid, self.result(conn, tid, initiator="Мария"), version=opened))
        self.assertEqual(db.task_meta(conn, tid)["initiator"], "Директор")

    def test_conflict_names_initiator(self):
        """В окне конфликта среди изменённого другим участником — «инициатора»."""
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        app = self.fake_app(conn)
        initial = app.form_data(tid)
        db.set_initiator(conn, tid, "Директор", by="Борис")
        seen = {}

        class FakeConflict:
            def __init__(self, root, title, who, when, changed, can_return):
                seen["changed"], seen["who"] = changed, who

            def show(self):
                return "theirs"

        app.root = None
        with mock.patch.object(self.T, "ConflictDialog", FakeConflict):
            app.resolve_conflict(tid, dict(initial), initial, can_return=True)
        self.assertEqual((seen["changed"], seen["who"]), (["инициатора"], "Борис"))

    def test_task_from_mail_initiator(self):
        """Задача из письма в общем списке: инициатор — тот, кто её создал (или выбранный)."""
        conn = db.connect(self.dir / "a.db")
        app = self.fake_app(conn, user="Анна")
        mail = dict(mail_id="m1", mail_from="boss@example.com", files=[], entry_id="e", store_id="s")
        status_id = db.list_statuses(conn)[0][0]
        base = dict(title="Письмо", body="", due_at=None, remind_before=None, urgent=False,
                    important=False, status_id=status_id, assignee="Анна")
        with mock.patch.object(self.T.outlook, "mark_added") as marked:
            first = app.create_from_mail(mail, dict(base, initiator="Анна"))
            second = app.create_from_mail(dict(mail, mail_id="m2"), dict(base, initiator="Директор"))
        self.assertEqual(marked.call_count, 2)
        self.assertEqual(db.task_meta(conn, first)["initiator"], "Анна")
        self.assertIsNone(self.stored(conn, first))  # «как автор» — имя отдельно не пишется
        self.assertEqual(db.task_meta(conn, second)["initiator"], "Директор")


class InitiatorFormTests(unittest.TestCase):
    """Поле «Инициатор» в форме задачи (настоящий Tk, окна за краем экрана)."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro
        cls.root = tk.Tk()
        cls.root.geometry("300x200" + OFFSCREEN)
        todoro.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.top = tk.Toplevel(self.root)
        self.top.geometry(OFFSCREEN)

    def tearDown(self):
        self.top.destroy()
        self.root.update()

    def task(self, initiator=None, assignee=None):
        return dict(title="Отчёт", body="", due_at=None, remind_before=None, urgent=0, important=0,
                    status_id=1, assignee=assignee, initiator=initiator, version=3)

    def form(self, task, members=None, compact=False):
        form = self.T.TaskForm(self.top, task, STATUSES, on_save=lambda r: None,
                               on_cancel=lambda: None, members=members, compact=compact)
        form.pack(fill="both")
        self.top.update()
        return form

    def labels(self, form):
        return [w.cget("text") for w in form.winfo_children() if isinstance(w, tk.ttk.Label)]

    def test_shared_form_has_initiator(self):
        for compact in (False, True):
            form = self.form(self.task(initiator="Анна"), members=["Борис", "Анна"], compact=compact)
            self.assertIsNotNone(form.initiator)
            self.assertIn("Инициатор", self.labels(form))
            self.assertEqual(form.initiator.get(), "Анна")
            self.assertEqual(list(form.initiator.cget("values")), ["Анна", "Борис"])
            self.assertEqual(form.values()["initiator"], "Анна")
            self.assertFalse(form.dirty())
            form.destroy()

    def test_outside_name_in_list(self):
        """Инициатор не из участников (например, руководитель) — есть в выпадающем списке."""
        form = self.form(self.task(initiator="Директор"), members=["Анна"])
        self.assertEqual(list(form.initiator.cget("values")), ["Анна", "Директор"])

    def test_typed_value_is_stripped(self):
        form = self.form(self.task(initiator="Анна"), members=["Анна"])
        form.initiator.delete(0, "end")
        form.initiator.insert(0, "  Директор  ")
        self.assertEqual(form.values()["initiator"], "Директор")
        self.assertTrue(form.dirty())
        form.initiator.delete(0, "end")
        form.initiator.insert(0, "   ")
        self.assertIsNone(form.values()["initiator"])

    def test_empty_initiator(self):
        """Задача без автора и инициатора — поле пустое, values() даёт None."""
        form = self.form(self.task(initiator=None), members=[])
        self.assertEqual(form.initiator.get(), "")
        self.assertIsNone(form.values()["initiator"])

    def test_task_without_initiator_key(self):
        """Словарь задачи без ключа initiator (старые места вызова) — форма не падает."""
        task = self.task()
        del task["initiator"]
        form = self.form(task, members=["Анна"])
        self.assertIsNone(form.values()["initiator"])

    def test_personal_form_has_no_initiator(self):
        form = self.form(self.task(initiator="Анна"), members=None)
        self.assertIsNone(form.initiator)
        self.assertNotIn("Инициатор", self.labels(form))
        self.assertIsNone(form.values()["initiator"])


class InitiatorCaptionTests(unittest.TestCase):
    """Подписи: «Автор» стал «Инициатором»."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def test_card_field_caption(self):
        self.assertTrue(self.T.CARD_FIELDS["author"].startswith("Инициатор"))

    def test_combobox_cursor_color(self):
        """В поле «Инициатор» можно вписать имя — курсор должен быть виден (цвет текста темы),
        в том числе в тёмной теме."""
        root = tk.Tk()
        root.withdraw()
        try:
            self.T.setup_style(root)
            style = tk.ttk.Style(root)
            self.assertEqual(str(style.lookup("TCombobox", "insertcolor")).lower(), self.T.TEXT.lower())
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
