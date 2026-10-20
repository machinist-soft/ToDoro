"""«Бизнес-единица» задачи и справочник единиц списка: функции db.py (с миграцией старой базы),
перенос задачи в другой список, CSV, письмо, поиск и сортировка, форма задачи, сохранение
правки, окно «Бизнес-единицы» и столбец в таблице. Временные файлы; окна Tk — за краем экрана;
сообщения и вложенные окна подменены; данные пользователя не трогаются."""

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


def unit_of(conn, task_id):
    return conn.execute("SELECT unit_id FROM tasks WHERE id = ?", (task_id,)).fetchone()[0]


def names(conn):
    return [name for _, name in db.list_units(conn)]


# ---------- db.py ----------

class UnitsDbTests(TempDir):
    def test_new_list_has_empty_dictionary(self):
        conn = db.connect(self.dir / "a.db")
        self.assertEqual(db.list_units(conn), [])
        tid = db.add_task(conn, "отчёт")
        self.assertIsNone(db.task_meta(conn, tid)["unit_id"])
        self.assertEqual(db.task_units(conn), {})
        conn.close()

    def test_old_database_gets_column_and_table(self):
        """Список старой версии (без столбца unit_id и таблицы units) открывается, задачи на
        месте, единица у них не указана."""
        path = self.dir / "old.db"
        old = sqlite3.connect(path)
        old.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                    "done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        old.execute("INSERT INTO tasks (title) VALUES ('старая')")
        old.commit()
        old.close()
        conn = db.connect(path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
        self.assertIn("unit_id", columns)
        self.assertEqual(db.list_units(conn), [])
        self.assertIsNone(db.task_meta(conn, 1)["unit_id"])
        uid = db.add_unit(conn, "Розница")
        db.set_task_unit(conn, 1, uid)
        self.assertEqual(db.task_units(conn), {1: uid})
        conn.close()
        # повторное открытие уже обновлённого файла ничего не ломает
        conn = db.connect(path)
        self.assertEqual(names(conn), ["Розница"])
        conn.close()

    def test_add_keeps_order_and_strips(self):
        conn = db.connect(self.dir / "a.db")
        first = db.add_unit(conn, "  Розница  ")
        second = db.add_unit(conn, "Опт")
        self.assertEqual(db.list_units(conn), [(first, "Розница"), (second, "Опт")])
        conn.close()

    def test_unit_by_name(self):
        """Поиск по названию — без учёта регистра и пробелов по краям; пусто и None — None."""
        conn = db.connect(self.dir / "a.db")
        uid = db.add_unit(conn, "Розница Москва")
        for name in ("Розница Москва", "розница москва", "  РОЗНИЦА МОСКВА  "):
            self.assertEqual(db.unit_by_name(conn, name), uid, name)
        for name in ("Опт", "", "   ", None):
            self.assertIsNone(db.unit_by_name(conn, name), repr(name))
        conn.close()

    def test_unit_key(self):
        """unit_key сжимает пробелы внутри, убирает по краям и снимает регистр."""
        self.assertEqual(db.unit_key("  Розница  Север "), "розница север")
        self.assertEqual(db.unit_key("РОЗНИЦА\tСЕВЕР"), db.unit_key("розница север"))
        self.assertEqual(db.unit_key(None), "")
        self.assertEqual(db.unit_key("   "), "")

    def test_inner_spaces_match(self):
        """«Розница  Север» (два пробела, записано в обход программы) и «розница север» —
        одна единица: поиск, копирование и импорт её не дублируют."""
        conn = db.connect(self.dir / "a.db")
        with conn:  # в обход add_unit — двойной пробел внутри остаётся
            conn.execute("INSERT INTO units (name, position) VALUES ('Розница  Север', 0)")
        uid = db.list_units(conn)[0][0]
        self.assertEqual(db.unit_by_name(conn, "розница север"), uid)
        src = db.connect(self.dir / "b.db")
        db.add_unit(src, "розница север")
        self.assertEqual(db.copy_units(src, conn), 0)
        status_id = db.list_statuses(conn)[0][0]
        db.import_tasks(conn, [dict(title="т", body="", status_id=status_id, due_at=None,
                                    remind_before=None, reminded=False, urgent=False,
                                    important=False, created_at=None, unit="РОЗНИЦА   СЕВЕР")])
        self.assertEqual(db.list_units(conn), [(uid, "Розница  Север")])
        self.assertEqual(conn.execute("SELECT unit_id FROM tasks").fetchone()[0], uid)
        # и наоборот: в справочнике обычное название, ищут с лишними пробелами
        self.assertEqual(db.unit_by_name(src, "  Розница   СЕВЕР "), db.list_units(src)[0][0])
        src.close()
        conn.close()

    def test_rename(self):
        conn = db.connect(self.dir / "a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "отчёт")
        db.set_task_unit(conn, tid, uid)
        db.rename_unit(conn, uid, "  Розничные продажи ")
        self.assertEqual(db.list_units(conn), [(uid, "Розничные продажи")])
        self.assertEqual(unit_of(conn, tid), uid)  # задача по-прежнему с этой единицей
        conn.close()

    def test_move(self):
        conn = db.connect(self.dir / "a.db")
        a, b, c = (db.add_unit(conn, n) for n in ("А", "Б", "В"))
        db.move_unit(conn, c, -1)
        self.assertEqual(names(conn), ["А", "В", "Б"])
        db.move_unit(conn, a, 1)
        self.assertEqual(names(conn), ["В", "А", "Б"])
        db.move_unit(conn, c, -1)  # уже первая — ничего не меняется
        db.move_unit(conn, b, 1)   # уже последняя — тоже
        self.assertEqual(names(conn), ["В", "А", "Б"])
        conn.close()

    def test_count_and_delete_moving_tasks(self):
        """Удаление единицы, которая стоит у задач: им ставится другая, правка засчитывается
        (версия +1, кто изменил); задачи с другими единицами не трогаются."""
        conn = db.connect(self.dir / "a.db")
        retail, wholesale = db.add_unit(conn, "Розница"), db.add_unit(conn, "Опт")
        t1, t2, other = db.add_task(conn, "1"), db.add_task(conn, "2"), db.add_task(conn, "3")
        db.set_task_unit(conn, t1, retail)
        db.set_task_unit(conn, t2, retail)
        db.set_task_unit(conn, other, wholesale)
        self.assertEqual(db.count_in_unit(conn, retail), 2)
        before = {t: version(conn, t) for t in (t1, t2, other)}
        db.delete_unit(conn, retail, wholesale, by="Анна")
        self.assertEqual(db.list_units(conn), [(wholesale, "Опт")])
        self.assertEqual((unit_of(conn, t1), unit_of(conn, t2)), (wholesale, wholesale))
        self.assertEqual(version(conn, t1), before[t1] + 1)
        self.assertEqual(db.task_meta(conn, t1)["updated_by"], "Анна")
        self.assertEqual(version(conn, other), before[other])
        self.assertEqual(db.count_in_unit(conn, wholesale), 3)
        conn.close()

    def test_delete_to_not_set(self):
        conn = db.connect(self.dir / "a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "1")
        db.set_task_unit(conn, tid, uid)
        db.delete_unit(conn, uid)
        self.assertEqual(db.list_units(conn), [])
        self.assertIsNone(unit_of(conn, tid))
        self.assertEqual(db.task_units(conn), {})
        conn.close()

    def test_delete_unused(self):
        conn = db.connect(self.dir / "a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "1")
        before = version(conn, tid)
        self.assertEqual(db.count_in_unit(conn, uid), 0)
        db.delete_unit(conn, uid)
        self.assertEqual(db.list_units(conn), [])
        self.assertEqual(version(conn, tid), before)
        conn.close()

    def test_copy_units(self):
        """Копируются только недостающие (по названию без учёта регистра), в порядке источника;
        повтор в самом источнике добавляется один раз."""
        src, dst = db.connect(self.dir / "a.db"), db.connect(self.dir / "b.db")
        for name in ("Розница", "Опт", "Интернет", "опт "):
            db.add_unit(src, name)
        db.add_unit(dst, "РОЗНИЦА")
        self.assertEqual(db.copy_units(src, dst), 2)
        self.assertEqual(names(dst), ["РОЗНИЦА", "Опт", "Интернет"])
        self.assertEqual(db.copy_units(src, dst), 0)  # второй раз — нечего добавлять
        empty = db.connect(self.dir / "c.db")
        self.assertEqual(db.copy_units(empty, dst), 0)
        self.assertEqual(names(src), ["Розница", "Опт", "Интернет", "опт"])  # источник не тронут
        for conn in (src, dst, empty):
            conn.close()

    def test_set_task_unit_bumps_version(self):
        """Смена единицы — правка: форма, открытая раньше, её не затирает."""
        conn = db.connect(self.dir / "a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        opened = version(conn, tid)
        db.set_task_unit(conn, tid, uid, by="Борис")
        meta = db.task_meta(conn, tid)
        self.assertEqual((meta["unit_id"], meta["version"], meta["updated_by"]), (uid, opened + 1, "Борис"))
        self.assertFalse(db.update_task(conn, tid, "отчёт v2", None, None, by="Анна", version=opened))
        db.set_task_unit(conn, tid, None)
        self.assertIsNone(db.task_meta(conn, tid)["unit_id"])
        db.set_task_unit(conn, 999, uid)  # задачу уже удалили — не падает
        conn.close()

    def test_task_units(self):
        conn = db.connect(self.dir / "a.db")
        a, b = db.add_unit(conn, "А"), db.add_unit(conn, "Б")
        t1, t2 = db.add_task(conn, "1"), db.add_task(conn, "2")
        db.add_task(conn, "без единицы")
        db.set_task_unit(conn, t1, a)
        db.set_task_unit(conn, t2, b)
        self.assertEqual(db.task_units(conn), {t1: a, t2: b})
        conn.close()

    def test_long_and_unicode_name(self):
        conn = db.connect(self.dir / "a.db")
        name = "Ünit «Я»—🙂 " * 1000
        uid = db.add_unit(conn, name)
        self.assertEqual(db.unit_by_name(conn, name.upper()), uid)
        self.assertEqual(names(conn), [name.strip()])
        conn.close()

    # --- перенос в другой список ---

    def test_move_task_adds_missing_unit(self):
        """В целевом списке такой единицы нет — она добавляется в его справочник."""
        src, dst = db.connect(self.dir / "a.db"), db.connect(self.dir / "b.db")
        db.add_unit(dst, "Опт")
        uid = db.add_unit(src, "Розница")
        tid = db.add_task(src, "отчёт")
        db.set_task_unit(src, tid, uid)
        new_id = db.move_task_to(src, tid, dst)
        self.assertEqual(names(dst), ["Опт", "Розница"])
        self.assertEqual(unit_of(dst, new_id), db.unit_by_name(dst, "Розница"))
        src.close()
        dst.close()

    def test_move_task_reuses_existing_unit(self):
        """Единица с тем же названием (в другом регистре) уже есть — новая не добавляется."""
        src, dst = db.connect(self.dir / "a.db"), db.connect(self.dir / "b.db")
        target = db.add_unit(dst, "РОЗНИЦА")
        uid = db.add_unit(src, "Розница")
        tid = db.add_task(src, "отчёт")
        db.set_task_unit(src, tid, uid)
        new_id = db.move_task_to(src, tid, dst)
        self.assertEqual(db.list_units(dst), [(target, "РОЗНИЦА")])
        self.assertEqual(unit_of(dst, new_id), target)
        src.close()
        dst.close()

    def test_move_task_without_unit(self):
        src, dst = db.connect(self.dir / "a.db"), db.connect(self.dir / "b.db")
        db.add_unit(src, "Розница")
        tid = db.add_task(src, "отчёт")
        new_id = db.move_task_to(src, tid, dst)
        self.assertIsNone(unit_of(dst, new_id))
        self.assertEqual(db.list_units(dst), [])  # справочник цели не засоряется
        src.close()
        dst.close()

    def test_move_task_with_dangling_unit(self):
        """У задачи номер единицы, которой в справочнике уже нет (испорченные данные) —
        переносится без единицы."""
        src, dst = db.connect(self.dir / "a.db"), db.connect(self.dir / "b.db")
        tid = db.add_task(src, "отчёт")
        with src:
            src.execute("UPDATE tasks SET unit_id = 777 WHERE id = ?", (tid,))
        new_id = db.move_task_to(src, tid, dst)
        self.assertIsNone(unit_of(dst, new_id))
        self.assertEqual(db.list_units(dst), [])
        src.close()
        dst.close()

    def test_move_task_into_old_list_file(self):
        """Перенос в файл старой версии (без units): connect его дополнит, единица добавится."""
        path = self.dir / "old.db"
        old = sqlite3.connect(path)
        old.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                    "done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        old.commit()
        old.close()
        src, dst = db.connect(self.dir / "a.db"), db.connect(path)
        uid = db.add_unit(src, "Розница")
        tid = db.add_task(src, "отчёт")
        db.set_task_unit(src, tid, uid)
        new_id = db.move_task_to(src, tid, dst)
        self.assertEqual(db.list_units(dst), [(unit_of(dst, new_id), "Розница")])
        src.close()
        dst.close()

    # --- импорт ---

    def test_import_tasks_units(self):
        """Новые названия добавляются в справочник один раз, существующие (в любом регистре)
        берутся из него; пусто и None — без единицы."""
        conn = db.connect(self.dir / "a.db")
        retail = db.add_unit(conn, "Розница")
        status_id = db.list_statuses(conn)[0][0]
        base = dict(body="", status_id=status_id, due_at=None, remind_before=None, reminded=False,
                    urgent=False, important=False, created_at=None)
        tasks = [dict(base, title="1", unit="розница"), dict(base, title="2", unit="Опт"),
                 dict(base, title="3", unit=" опт "), dict(base, title="4", unit=None),
                 dict(base, title="5", unit=""), dict(base, title="6")]
        db.import_tasks(conn, tasks)
        wholesale = db.unit_by_name(conn, "Опт")
        self.assertEqual(names(conn), ["Розница", "Опт"])
        got = dict(conn.execute("SELECT title, unit_id FROM tasks"))
        self.assertEqual(got, {"1": retail, "2": wholesale, "3": wholesale, "4": None, "5": None,
                               "6": None})
        conn.close()


# ---------- todoro.py без окна ----------

class UnitsAppTests(TempDir):
    """CSV, письмо, поиск, сортировка, сохранение правки — на подставном TodoApp."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def setUp(self):
        super().setUp()
        self.conns = []

    def tearDown(self):
        for conn in self.conns:
            conn.close()
        super().tearDown()

    def open(self, name):
        conn = db.connect(self.dir / name)
        self.conns.append(conn)
        return conn

    def fake_app(self, conn, shared=False, user="Анна"):
        T = self.T
        app = SimpleNamespace(conn=conn, list_id="team" if shared else None, refreshed=[],
                              authors={}, assignees={}, unit_names={}, search_query="",
                              extra_counts={}, mail_ids=set(), column_sort=None)
        app.created_by = lambda: user if shared else None
        app.members = lambda: ["Анна", "Борис"] if shared else None
        app.current_list = lambda: {"shared": shared, "name": "Список"}
        app.task_info = lambda task_id: {"status_id": db.get_task_row(conn, task_id)[-1]}
        app.celebrate = lambda task_id: None
        app.refresh = lambda select_id=None: app.refreshed.append(select_id)
        app.user_name = lambda: user
        app.sort_key = lambda row: row[0]
        app.CHANGED_NAMES = T.TodoApp.CHANGED_NAMES
        for name in ("apply_edit", "form_data", "people", "resolve_conflict", "found", "sort_rows",
                     "marks_order", "units_list_conn"):
            setattr(app, name, getattr(T.TodoApp, name).__get__(app))
        return app

    def result(self, conn, task_id, **changes):
        title, due_at, remind_before, urgent, important, body = db.get_task(conn, task_id)
        meta = db.task_meta(conn, task_id)
        data = dict(title=title, due_at=due_at, remind_before=remind_before, urgent=urgent,
                    important=important, body=body, status_id=db.get_task_row(conn, task_id)[-1],
                    assignee=meta["assignee"], initiator=meta["initiator"], unit_id=meta["unit_id"])
        data.update(changes)
        return data

    # --- CSV ---

    def test_csv_export(self):
        conn = self.open("a.db")
        uid = db.add_unit(conn, "Розница")
        with_unit, without = db.add_task(conn, "отчёт"), db.add_task(conn, "звонок")
        db.set_task_unit(conn, with_unit, uid)
        columns = self.T.CSV_COLUMNS
        self.assertEqual(columns[-1], "Бизнес-единица")
        rows = {r[0]: r for r in self.T.export_rows(conn)}
        self.assertTrue(all(len(r) == len(columns) for r in rows.values()))
        self.assertEqual((rows[with_unit][-1], rows[without][-1]), ("Розница", ""))
        conn.close()

    def test_csv_import_aliases_and_notes(self):
        """Заголовок «Бизнес-единица» / «бизнес единица» в любом регистре; про новую единицу —
        одно замечание, про имеющуюся (в другом регистре) — ни одного; пробелы внутри сжимаются."""
        conn = self.open("a.db")
        db.add_unit(conn, "Розница")
        for header in ("Бизнес-единица", " бизнес единица ", "БИЗНЕС-ЕДИНИЦА"):
            path = self.dir / "x.csv"
            path.write_text(f"Заголовок;{header}\nА;Опт\nБ; опт \nВ;РОЗНИЦА\nГ;\nД;Интернет   магазин\n",
                            encoding="utf-8-sig")
            tasks, notes = self.T.prepare_import(conn, self.T.read_csv(path))
            self.assertEqual([t["unit"] for t in tasks],
                             ["Опт", "опт", "РОЗНИЦА", None, "Интернет магазин"], header)
            self.assertEqual(len(notes), 2, notes)
            self.assertIn("строка 2", notes[0])
            self.assertIn("«Опт»", notes[0])
            self.assertIn("«Интернет магазин»", notes[1])
        db.import_tasks(conn, tasks)
        self.assertEqual(names(conn), ["Розница", "Опт", "Интернет магазин"])
        got = dict(conn.execute("SELECT title, unit_id FROM tasks"))
        self.assertEqual(got["Б"], got["А"])
        self.assertEqual(got["В"], db.unit_by_name(conn, "Розница"))
        self.assertIsNone(got["Г"])
        conn.close()

    def test_csv_old_file_without_column(self):
        conn = self.open("a.db")
        path = self.dir / "old.csv"
        path.write_text("№;Заголовок;Описание;Статус;Приоритет;Срок;Напомнить;Создана;Автор;Исполнитель\n"
                        "1;Отчёт;;Новая;Обычный;;;;Анна;\n", encoding="utf-8-sig")
        tasks, notes = self.T.prepare_import(conn, self.T.read_csv(path))
        self.assertEqual(notes, [])
        self.assertIsNone(tasks[0]["unit"])
        db.import_tasks(conn, tasks)
        self.assertEqual(db.list_units(conn), [])
        conn.close()

    def test_csv_roundtrip(self):
        """Экспорт → импорт в другой список: единицы появляются в его справочнике."""
        conn = self.open("a.db")
        uid = db.add_unit(conn, "Розница")
        db.add_unit(conn, "Неиспользуемая")
        tid = db.add_task(conn, "отчёт")
        db.set_task_unit(conn, tid, uid)
        db.add_task(conn, "звонок")
        path = self.dir / "x.csv"
        self.T.write_csv(path, self.T.CSV_COLUMNS, self.T.export_rows(conn))
        other = self.open("b.db")
        tasks, notes = self.T.prepare_import(other, self.T.read_csv(path))
        self.assertEqual(len(notes), 1)
        db.import_tasks(other, tasks)
        self.assertEqual(names(other), ["Розница"])  # неиспользуемая не переносится
        got = {title: uid for title, uid in other.execute("SELECT title, unit_id FROM tasks")}
        self.assertEqual(got, {"отчёт": db.unit_by_name(other, "Розница"), "звонок": None})
        conn.close()
        other.close()

    # --- письмо ---

    def test_email_unit_line(self):
        _, text = self.T.build_email(5, "Отчёт", "Новая", "", "", "", "16.10", False, unit="Розница")
        self.assertIn("Бизнес-единица: Розница", text)
        _, text = self.T.build_email(5, "Отчёт", "Новая", "", "", "", "16.10", False)
        self.assertNotIn("Бизнес-единица", text)

    # --- поиск, сортировка, карточка ---

    def test_search_by_unit(self):
        conn = self.open("a.db")
        app = self.fake_app(conn)
        app.unit_names = {1: "Розница Москва"}
        app.search_query = "москва"
        row = (1, "Отчёт", False, None, None, None, False, False, "", 1)
        self.assertTrue(app.found(row))
        self.assertFalse(app.found((2,) + row[1:]))
        conn.close()

    def test_sort_by_unit_empty_last(self):
        conn = self.open("a.db")
        app = self.fake_app(conn)
        app.unit_names = {1: "опт", 2: "Аренда", 4: "Розница"}
        rows = [(i, "т", False, None, None, None, False, False, "", 1) for i in (3, 4, 1, 2)]
        statuses = [(1, "Новая")]
        app.column_sort = ["unit", False]
        self.assertEqual([r[0] for r in app.sort_rows(rows, statuses)], [2, 1, 4, 3])
        app.column_sort = ["unit", True]
        self.assertEqual([r[0] for r in app.sort_rows(rows, statuses)], [4, 1, 2, 3])
        conn.close()

    def test_form_data_and_people(self):
        conn = self.open("a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "отчёт")
        app = self.fake_app(conn)
        self.assertIsNone(app.form_data(tid)["unit_id"])
        self.assertEqual(app.people(tid)["unit"], "")
        db.set_task_unit(conn, tid, uid)
        app.unit_names = {tid: "Розница"}
        self.assertEqual(app.form_data(tid)["unit_id"], uid)
        self.assertEqual(app.people(tid)["unit"], "Розница")
        conn.close()

    # --- apply_edit ---

    def test_apply_edit_sets_unit_personal(self):
        """В личном списке единица тоже сохраняется."""
        conn = self.open("a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "отчёт")
        app = self.fake_app(conn)
        before = version(conn, tid)
        self.assertTrue(app.apply_edit(tid, self.result(conn, tid, unit_id=uid)))
        self.assertEqual(unit_of(conn, tid), uid)
        self.assertEqual(version(conn, tid), before + 2)  # правка полей + смена единицы
        self.assertEqual(app.refreshed, [tid])

    def test_apply_edit_shared_with_version(self):
        conn = self.open("a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        app = self.fake_app(conn, shared=True, user="Борис")
        opened = version(conn, tid)
        self.assertTrue(app.apply_edit(tid, self.result(conn, tid, unit_id=uid), version=opened))
        meta = db.task_meta(conn, tid)
        self.assertEqual((meta["unit_id"], meta["updated_by"], meta["version"]), (uid, "Борис", opened + 2))

    def test_apply_edit_unit_deleted_meanwhile(self):
        """Пока форма была открыта, выбранную в ней единицу удалили из справочника —
        записывается «не указана», а не номер несуществующей единицы."""
        conn = self.open("a.db")
        retail, wholesale = db.add_unit(conn, "Розница"), db.add_unit(conn, "Опт")
        tid = db.add_task(conn, "отчёт")
        db.set_task_unit(conn, tid, wholesale)
        app = self.fake_app(conn)
        result = self.result(conn, tid, unit_id=retail)  # в форме выбрали «Розницу»
        db.delete_unit(conn, retail)                     # а её тем временем удалили
        self.assertTrue(app.apply_edit(tid, result))
        self.assertIsNone(unit_of(conn, tid))
        self.assertEqual(db.task_units(conn), {})

    def test_apply_edit_unit_deleted_task_already_none(self):
        """Задача и так без единицы, а в форме — удалённая: запись не падает, остаётся None."""
        conn = self.open("a.db")
        retail = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "отчёт")
        app = self.fake_app(conn)
        result = self.result(conn, tid, unit_id=retail)
        db.delete_unit(conn, retail)
        app.apply_edit(tid, result)
        self.assertIsNone(unit_of(conn, tid))

    def test_apply_edit_clear_unit(self):
        conn = self.open("a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "отчёт")
        db.set_task_unit(conn, tid, uid)
        app = self.fake_app(conn)
        app.apply_edit(tid, self.result(conn, tid, unit_id=None))
        self.assertIsNone(unit_of(conn, tid))

    def test_apply_edit_same_unit_no_extra_version(self):
        conn = self.open("a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "отчёт")
        db.set_task_unit(conn, tid, uid)
        app = self.fake_app(conn)
        before = version(conn, tid)
        app.apply_edit(tid, self.result(conn, tid))
        self.assertEqual(version(conn, tid), before + 1)  # только update_task
        self.assertEqual(unit_of(conn, tid), uid)

    def test_apply_edit_without_unit_key_keeps_unit(self):
        """Результат без ключа unit_id (старые места вызова) единицу не сбрасывает."""
        conn = self.open("a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "отчёт")
        db.set_task_unit(conn, tid, uid)
        app = self.fake_app(conn)
        result = self.result(conn, tid, title="новое")
        del result["unit_id"]
        app.apply_edit(tid, result)
        self.assertEqual(unit_of(conn, tid), uid)

    def test_apply_edit_conflict_keeps_unit(self):
        """Устаревшая форма не сохраняет и единицу."""
        conn = self.open("a.db")
        retail, wholesale = db.add_unit(conn, "Розница"), db.add_unit(conn, "Опт")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        app = self.fake_app(conn, shared=True)
        opened = version(conn, tid)
        db.set_task_unit(conn, tid, wholesale, by="Борис")
        self.assertFalse(app.apply_edit(tid, self.result(conn, tid, unit_id=retail), version=opened))
        self.assertEqual(unit_of(conn, tid), wholesale)

    def test_conflict_names_unit(self):
        conn = self.open("a.db")
        uid = db.add_unit(conn, "Розница")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        app = self.fake_app(conn, shared=True)
        initial = app.form_data(tid)
        db.set_task_unit(conn, tid, uid, by="Борис")
        seen = {}

        class FakeConflict:
            def __init__(self, root, title, who, when, changed, can_return):
                seen["changed"] = changed

            def show(self):
                return "theirs"

        app.root = None
        with mock.patch.object(self.T, "ConflictDialog", FakeConflict):
            app.resolve_conflict(tid, dict(initial), initial, can_return=True)
        self.assertEqual(seen["changed"], ["бизнес-единицу"])

    # --- «Взять из списка…» ---

    def test_units_list_conn_shared_offline(self):
        """Общий список при недоступной папке — OSError (окно покажет предупреждение),
        к сети не обращаемся."""
        conn = self.open("a.db")
        app = self.fake_app(conn)
        app.lists = [{"id": "team", "shared": True}, {"id": "home", "shared": False}]
        app.share_online = lambda: False
        app.list_conn = mock.Mock(return_value="соединение")
        with self.assertRaises(OSError):
            app.units_list_conn("team")
        app.list_conn.assert_not_called()
        self.assertEqual(app.units_list_conn("home"), "соединение")
        app.share_online = lambda: True
        self.assertEqual(app.units_list_conn("team"), "соединение")
        conn.close()


# ---------- окна Tk (за краем экрана) ----------

class TkCase(unittest.TestCase):
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


class UnitsFormTests(TkCase):
    """Поле «Бизнес-единица» в форме задачи."""

    def setUp(self):
        self.top = tk.Toplevel(self.root)
        self.top.geometry(OFFSCREEN)

    def tearDown(self):
        self.top.destroy()
        self.root.update()

    def task(self, unit_id=None):
        return dict(title="Отчёт", body="", due_at=None, remind_before=None, urgent=0, important=0,
                    status_id=1, assignee=None, initiator=None, unit_id=unit_id, version=3)

    def form(self, task, units=None, compact=False):
        form = self.T.TaskForm(self.top, task, STATUSES, on_save=lambda r: None,
                               on_cancel=lambda: None, compact=compact, units=units)
        form.pack(fill="both")
        self.top.update()
        return form

    def labels(self, form):
        return [w.cget("text") for w in form.winfo_children() if isinstance(w, tk.ttk.Label)]

    def test_empty_dictionary_no_field(self):
        """Справочник пуст (или не передан) — поля нет, а прежняя единица задачи сохраняется."""
        for units in (None, []):
            form = self.form(self.task(unit_id=7), units=units)
            self.assertIsNone(form.unit)
            self.assertNotIn("Бизнес-единица", self.labels(form))
            self.assertEqual(form.values()["unit_id"], 7)
            self.assertFalse(form.dirty())
            form.destroy()

    def test_task_without_unit_key(self):
        task = self.task()
        del task["unit_id"]
        form = self.form(task)
        self.assertIsNone(form.values()["unit_id"])
        form.destroy()
        form = self.form(task, units=[(1, "Розница")])
        self.assertEqual(form.unit.get(), self.T.NO_UNIT)
        self.assertIsNone(form.values()["unit_id"])

    def test_field_with_dictionary(self):
        units = [(1, "Розница"), (2, "Опт")]
        for compact in (False, True):
            form = self.form(self.task(unit_id=2), units=units, compact=compact)
            self.assertIn("Бизнес-единица", self.labels(form))
            self.assertEqual(list(form.unit.cget("values")), [self.T.NO_UNIT, "Розница", "Опт"])
            self.assertEqual(str(form.unit.cget("state")), "readonly")
            self.assertEqual(form.unit.get(), "Опт")
            self.assertEqual(form.values()["unit_id"], 2)
            self.assertFalse(form.dirty())
            form.unit.set("Розница")
            self.assertEqual(form.values()["unit_id"], 1)
            self.assertTrue(form.dirty())
            form.unit.set(self.T.NO_UNIT)
            self.assertIsNone(form.values()["unit_id"])
            form.destroy()

    def test_unknown_unit_shows_not_set(self):
        """Единицы задачи уже нет в справочнике — в поле «не указана»."""
        form = self.form(self.task(unit_id=99), units=[(1, "Розница")])
        self.assertEqual(form.unit.get(), self.T.NO_UNIT)
        self.assertIsNone(form.values()["unit_id"])


class FakeNameDialog:
    """Вместо окна ввода названия: отдаёт ответы по очереди и запоминает, с чем его открыли."""
    answers = []
    calls = []

    def __init__(self, parent, title, heading, value="", hint="", ok_text="Сохранить"):
        FakeNameDialog.calls.append(value)

    def show(self):
        return FakeNameDialog.answers.pop(0)


class FakeDeleteDialog:
    answer = None
    calls = []

    def __init__(self, parent, name, count, others):
        FakeDeleteDialog.calls.append((name, count, others))

    def show(self):
        return FakeDeleteDialog.answer


class UnitsDialogTests(TkCase, TempDir):
    """Окно «Бизнес-единицы»: методы на настоящем окне за краем экрана."""

    def setUp(self):
        TempDir.setUp(self)
        self.conn = db.connect(self.dir / "a.db")
        self.other = db.connect(self.dir / "b.db")
        FakeNameDialog.answers, FakeNameDialog.calls = [], []
        FakeDeleteDialog.answer, FakeDeleteDialog.calls = None, []
        self.ui = {}
        for name in ("showinfo", "showwarning", "showerror", "askyesno"):
            patcher = mock.patch.object(self.T.ui, name, return_value=True)
            self.ui[name] = patcher.start()
            self.addCleanup(patcher.stop)
        for name, fake in (("NameDialog", FakeNameDialog), ("UnitDeleteDialog", FakeDeleteDialog)):
            patcher = mock.patch.object(self.T, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.dialogs = []

    def tearDown(self):
        for dialog in self.dialogs:
            try:
                dialog.destroy()
            except tk.TclError:
                pass
        self.root.update()
        self.conn.close()
        self.other.close()
        TempDir.tearDown(self)

    def dialog(self, other_lists=(("b", "Работа"),), units_from=None):
        dialog = self.T.UnitsDialog(self.root, self.conn, "Личный", "Анна", list(other_lists),
                                    units_from or (lambda list_id: self.other))
        dialog.geometry(OFFSCREEN)
        dialog.update()
        self.dialogs.append(dialog)
        return dialog

    def select(self, dialog, index):
        dialog.listbox.selection_clear(0, "end")
        dialog.listbox.selection_set(index)
        dialog.update_buttons()

    def shown(self, dialog):
        return list(dialog.listbox.get(0, "end"))

    def disabled(self, dialog, key):
        return dialog.buttons[key].instate(["disabled"])

    def test_opens_with_dictionary(self):
        db.add_unit(self.conn, "Розница")
        db.add_unit(self.conn, "Опт")
        dialog = self.dialog()
        self.assertEqual(self.shown(dialog), ["Розница", "Опт"])
        for key in ("rename", "delete", "up", "down"):  # ничего не выбрано
            self.assertTrue(self.disabled(dialog, key), key)
        self.assertFalse(self.disabled(dialog, "copy"))

    def test_copy_disabled_without_other_lists(self):
        self.assertTrue(self.disabled(self.dialog(other_lists=()), "copy"))

    def test_add(self):
        FakeNameDialog.answers = ["Розница"]
        dialog = self.dialog()
        dialog.add()
        self.assertEqual(names(self.conn), ["Розница"])
        self.assertEqual(self.shown(dialog), ["Розница"])
        self.assertEqual(dialog.listbox.curselection(), (0,))  # новая выбрана
        self.ui["showwarning"].assert_not_called()

    def test_add_cancel(self):
        FakeNameDialog.answers = [None]
        dialog = self.dialog()
        dialog.add()
        self.assertEqual(db.list_units(self.conn), [])

    def test_add_duplicate_asks_again(self):
        """Повтор названия (в другом регистре) — предупреждение и снова окно ввода с тем же
        текстом; второе, новое название добавляется."""
        db.add_unit(self.conn, "Розница")
        FakeNameDialog.answers = ["РОЗНИЦА", "Опт"]
        dialog = self.dialog()
        dialog.add()
        self.ui["showwarning"].assert_called_once()
        self.assertIn("уже есть", self.ui["showwarning"].call_args[0][1])
        self.assertEqual(FakeNameDialog.calls, ["", "РОЗНИЦА"])
        self.assertEqual(names(self.conn), ["Розница", "Опт"])

    def test_add_duplicate_then_cancel(self):
        db.add_unit(self.conn, "Розница")
        FakeNameDialog.answers = ["розница", None]
        dialog = self.dialog()
        dialog.add()
        self.assertEqual(names(self.conn), ["Розница"])

    def test_rename(self):
        uid = db.add_unit(self.conn, "Розница")
        db.add_unit(self.conn, "Опт")
        FakeNameDialog.answers = ["Розничные продажи"]
        dialog = self.dialog()
        self.select(dialog, 0)
        dialog.rename()
        self.assertEqual(FakeNameDialog.calls, ["Розница"])  # в окне — прежнее название
        self.assertEqual(db.list_units(self.conn)[0], (uid, "Розничные продажи"))
        self.assertEqual(dialog.listbox.curselection(), (0,))

    def test_rename_to_other_existing(self):
        db.add_unit(self.conn, "Розница")
        db.add_unit(self.conn, "Опт")
        FakeNameDialog.answers = ["опт", None]
        dialog = self.dialog()
        self.select(dialog, 0)
        dialog.rename()
        self.ui["showwarning"].assert_called_once()
        self.assertEqual(names(self.conn), ["Розница", "Опт"])

    def test_rename_same_name_other_case(self):
        """Своё же название в другом регистре — не повтор."""
        db.add_unit(self.conn, "розница")
        FakeNameDialog.answers = ["Розница"]
        dialog = self.dialog()
        self.select(dialog, 0)
        dialog.rename()
        self.ui["showwarning"].assert_not_called()
        self.assertEqual(names(self.conn), ["Розница"])

    def test_rename_nothing_selected(self):
        db.add_unit(self.conn, "Розница")
        dialog = self.dialog()
        dialog.rename()
        dialog.delete()
        dialog.move(1)
        self.assertEqual(FakeNameDialog.calls, [])
        self.assertEqual(names(self.conn), ["Розница"])

    def test_delete_unused(self):
        db.add_unit(self.conn, "Розница")
        db.add_unit(self.conn, "Опт")
        dialog = self.dialog()
        self.select(dialog, 0)
        self.ui["askyesno"].return_value = False
        dialog.delete()
        self.assertEqual(names(self.conn), ["Розница", "Опт"])
        self.ui["askyesno"].return_value = True
        dialog.delete()
        self.assertEqual(names(self.conn), ["Опт"])
        self.assertEqual(self.shown(dialog), ["Опт"])
        self.assertEqual(FakeDeleteDialog.calls, [])  # без задач — простой вопрос

    def test_delete_used_move_to_other(self):
        retail, wholesale = db.add_unit(self.conn, "Розница"), db.add_unit(self.conn, "Опт")
        tasks = [db.add_task(self.conn, str(i)) for i in range(3)]
        for tid in tasks:
            db.set_task_unit(self.conn, tid, retail)
        FakeDeleteDialog.answer = ("ok", wholesale)
        dialog = self.dialog()
        self.select(dialog, 0)
        dialog.delete()
        self.assertEqual(FakeDeleteDialog.calls, [("Розница", 3, [(wholesale, "Опт")])])
        self.ui["askyesno"].assert_not_called()
        self.assertEqual(names(self.conn), ["Опт"])
        self.assertEqual({unit_of(self.conn, t) for t in tasks}, {wholesale})
        self.assertEqual(db.task_meta(self.conn, tasks[0])["updated_by"], "Анна")

    def test_delete_used_move_to_not_set(self):
        retail = db.add_unit(self.conn, "Розница")
        tid = db.add_task(self.conn, "1")
        db.set_task_unit(self.conn, tid, retail)
        FakeDeleteDialog.answer = ("ok", None)
        dialog = self.dialog()
        self.select(dialog, 0)
        dialog.delete()
        self.assertEqual(FakeDeleteDialog.calls, [("Розница", 1, [])])
        self.assertEqual(db.list_units(self.conn), [])
        self.assertIsNone(unit_of(self.conn, tid))

    def test_delete_used_cancel(self):
        retail = db.add_unit(self.conn, "Розница")
        tid = db.add_task(self.conn, "1")
        db.set_task_unit(self.conn, tid, retail)
        FakeDeleteDialog.answer = None
        dialog = self.dialog()
        self.select(dialog, 0)
        dialog.delete()
        self.assertEqual(names(self.conn), ["Розница"])
        self.assertEqual(unit_of(self.conn, tid), retail)

    def test_move_and_buttons(self):
        for name in ("А", "Б", "В"):
            db.add_unit(self.conn, name)
        dialog = self.dialog()
        self.select(dialog, 0)
        self.assertTrue(self.disabled(dialog, "up"))
        self.assertFalse(self.disabled(dialog, "down"))
        dialog.move(1)
        self.assertEqual(names(self.conn), ["Б", "А", "В"])
        self.assertEqual(dialog.listbox.curselection(), (1,))  # выделение едет за единицей
        dialog.move(1)
        self.assertEqual(self.shown(dialog), ["Б", "В", "А"])
        self.assertTrue(self.disabled(dialog, "down"))
        self.assertFalse(self.disabled(dialog, "up"))
        dialog.move(1)  # уже последняя
        self.assertEqual(names(self.conn), ["Б", "В", "А"])
        dialog.move(-1)
        self.assertEqual(names(self.conn), ["Б", "А", "В"])

    def test_copy_from(self):
        db.add_unit(self.conn, "Розница")
        db.add_unit(self.other, "розница")
        db.add_unit(self.other, "Опт")
        asked = []
        dialog = self.dialog(units_from=lambda list_id: asked.append(list_id) or self.other)
        dialog.copy_from("b", "Работа")
        self.assertEqual(asked, ["b"])
        self.assertEqual(self.shown(dialog), ["Розница", "Опт"])
        self.assertIn("Добавлено из списка «Работа»: 1", self.ui["showinfo"].call_args[0][1])
        dialog.copy_from("b", "Работа")  # второй раз — нечего добавлять
        self.assertIn("уже есть", self.ui["showinfo"].call_args[0][1])
        self.assertEqual(names(self.conn), ["Розница", "Опт"])

    def test_copy_from_error(self):
        """Список недоступен (нет сети, испорченный файл) — предупреждение, справочник цел."""
        db.add_unit(self.conn, "Розница")
        for error in (OSError("общая папка сейчас недоступна"), sqlite3.DatabaseError("file is not a database")):
            def broken(list_id, error=error):
                raise error
            dialog = self.dialog(units_from=broken)
            self.ui["showwarning"].reset_mock()
            dialog.copy_from("b", "Команда")
            self.ui["showwarning"].assert_called_once()
            self.assertIn("Команда", self.ui["showwarning"].call_args[0][1])
            self.assertIn(str(error), self.ui["showwarning"].call_args[0][1])
            self.ui["showinfo"].assert_not_called()
            self.assertEqual(names(self.conn), ["Розница"])

    def test_buttons_report_db_error_and_close(self):
        """Файл списка стал недоступен: кнопка «Добавить…» показывает предупреждение и окно
        закрывается, а не падает с ошибкой."""
        FakeNameDialog.answers = ["Розница"]
        dialog = self.dialog()
        with mock.patch.object(self.T.db, "add_unit",
                               side_effect=sqlite3.OperationalError("disk I/O error")):
            dialog.buttons["add"].invoke()
        self.ui["showwarning"].assert_called_once()
        self.assertIn("disk I/O error", self.ui["showwarning"].call_args[0][1])
        self.assertFalse(dialog.winfo_exists())

    def unavailable_dialog(self, name):
        """Окно со справочником А, Б, В, выбрана «Б»; потом соединение закрывается
        (файл списка «пропал»)."""
        conn = db.connect(self.dir / name)
        for unit in ("А", "Б", "В"):
            db.add_unit(conn, unit)
        dialog = self.T.UnitsDialog(self.root, conn, "Личный", None, [], lambda i: None)
        dialog.geometry(OFFSCREEN)
        dialog.update()
        self.dialogs.append(dialog)
        self.select(dialog, 1)
        conn.close()
        self.ui["showwarning"].reset_mock()
        return dialog

    def test_all_buttons_wrapped(self):
        """«Добавить», «Переименовать», «Удалить», ↑/↓ при закрытом соединении —
        предупреждение и закрытие окна."""
        for key in ("add", "rename", "delete", "up", "down"):
            with self.subTest(key=key):
                FakeNameDialog.answers = ["Г"]
                dialog = self.unavailable_dialog(f"{key}.db")
                dialog.buttons[key].invoke()
                self.ui["showwarning"].assert_called_once()
                self.assertFalse(dialog.winfo_exists())

    def test_double_click_wrapped(self):
        """Двойной щелчок по единице (переименование) при недоступном файле."""
        FakeNameDialog.answers = ["Г"]
        dialog = self.unavailable_dialog("dbl.db")
        dialog.listbox.event_generate("<ButtonPress-1>", x=5, y=5)
        dialog.listbox.event_generate("<ButtonRelease-1>", x=5, y=5)
        dialog.listbox.event_generate("<ButtonPress-1>", x=5, y=5)  # второе нажатие — двойной щелчок
        self.root.update()
        self.ui["showwarning"].assert_called_once()
        self.assertFalse(dialog.winfo_exists())

    def test_delete_key_wrapped(self):
        """Клавиша Delete в списке при недоступном файле."""
        dialog = self.unavailable_dialog("del.db")
        dialog.listbox.focus_force()
        dialog.listbox.event_generate("<Delete>")
        self.root.update()
        self.ui["showwarning"].assert_called_once()
        self.assertFalse(dialog.winfo_exists())

    def test_no_unit_name_forbidden(self):
        """Название «— не указана —» (в любом регистре, с лишними пробелами) занято: форма так
        обозначает задачу без единицы. Предупреждение и окно ввода снова."""
        variants = [self.T.NO_UNIT, "  " + self.T.NO_UNIT.upper().replace(" ", "   ") + " "]
        for bad in variants:
            with self.subTest(bad=bad):
                FakeNameDialog.answers, FakeNameDialog.calls = [bad, "Опт"], []
                self.ui["showwarning"].reset_mock()
                dialog = self.dialog()
                dialog.add()
                self.ui["showwarning"].assert_called_once()
                self.assertEqual(len(FakeNameDialog.calls), 2)
                self.assertEqual(names(self.conn), ["Опт"])
                db.delete_unit(self.conn, db.unit_by_name(self.conn, "Опт"))

    def test_rename_to_no_unit_forbidden(self):
        db.add_unit(self.conn, "Розница")
        FakeNameDialog.answers = [self.T.NO_UNIT.lower(), None]
        dialog = self.dialog()
        self.select(dialog, 0)
        dialog.rename()
        self.ui["showwarning"].assert_called_once()
        self.assertEqual(names(self.conn), ["Розница"])

    def test_copy_menu_lists_other_lists(self):
        items = []

        class FakeMenu:
            def command(self, text, action, **_):
                items.append((text, action))
                return self

            def popup(self, *args):
                pass

        dialog = self.dialog(other_lists=[("b", "Работа"), ("c", "Дом")])
        db.add_unit(self.other, "Опт")
        with mock.patch.object(self.T, "PopupMenu", FakeMenu):
            dialog.copy_menu()
        self.assertEqual([t for t, _ in items], ["Работа", "Дом"])
        items[0][1]()
        self.assertEqual(names(self.conn), ["Опт"])


class UnitsPhoneTests(unittest.TestCase):
    """Правка задачи с телефона (он про бизнес-единицы не знает) единицу не сбрасывает."""

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

    def check(self, list_id, path):
        task = self.call("POST", f"/api/v1/lists/{list_id}/tasks", {"title": "Позвонить"})[1]["task"]
        conn = db.connect(path)
        uid = db.add_unit(conn, "Розница")
        db.set_task_unit(conn, task["id"], uid)
        task_version = db.task_meta(conn, task["id"])["version"]
        conn.close()
        # телефон присылает и чужие поля — они ничего не меняют
        status, answer = self.call("PATCH", f"/api/v1/lists/{list_id}/tasks/{task['id']}",
                                   {"version": task_version, "title": "Позвонить в банк",
                                    "done": True, "unit_id": None, "unit": ""})
        self.assertEqual(status, 200, answer)
        conn = db.connect(path)
        try:
            self.assertEqual(db.get_task(conn, task["id"])[0], "Позвонить в банк")
            self.assertEqual(unit_of(conn, task["id"]), uid)
            self.assertEqual(db.list_units(conn), [(uid, "Розница")])
        finally:
            conn.close()

    def test_personal_list(self):
        self.check("personal", self.prefs_path)

    def test_shared_list(self):
        self.check(self.item["id"], self.list_path)


class UnitDeleteDialogTests(TkCase):
    def test_choices_and_result(self):
        dialog = self.T.UnitDeleteDialog(self.root, "Розница", 3, [(2, "Опт"), (5, "Интернет")])
        try:
            dialog.geometry(OFFSCREEN)
            self.assertEqual(list(dialog.choice.cget("values")), [self.T.NO_UNIT, "Опт", "Интернет"])
            self.assertEqual(dialog.choice.get(), self.T.NO_UNIT)
            dialog.choice.set("Интернет")
            dialog.ok()
            self.assertEqual(dialog.result, ("ok", 5))
        finally:
            try:
                dialog.destroy()
            except tk.TclError:
                pass

    def test_not_set_choice(self):
        dialog = self.T.UnitDeleteDialog(self.root, "Розница", 1, [])
        dialog.geometry(OFFSCREEN)
        dialog.ok()
        self.assertEqual(dialog.result, ("ok", None))


# ---------- столбец в настоящем окне ----------

from tests import test_column_order as tco  # noqa: E402


class UnitColumnWindowTests(unittest.TestCase):
    """Настоящий TodoApp на временной базе (подготовка — как в test_column_order)."""

    setUp = tco.ColumnDragWindowTests.setUp
    tearDown = tco.ColumnDragWindowTests.tearDown
    make_app = tco.ColumnDragWindowTests.make_app
    pump = tco.ColumnDragWindowTests.pump

    def values(self, app, task_id):
        item = next(i for i in app.tree.get_children() if app.tree.item(i, "values")[0] == f"#{task_id}")
        return dict(zip(app.tree["columns"], app.tree.item(item, "values")))

    def test_hidden_while_dictionary_empty(self):
        app = self.make_app()
        self.assertIn("unit", app.column_order)
        self.assertNotIn("unit", app.shown_columns())
        self.assertEqual(app.units, {})

    def test_shown_with_dictionary_and_hidden_again(self):
        app = self.make_app()
        uid = db.add_unit(app.conn, "Розница")
        app.refresh()
        self.pump(app)
        self.assertIn("unit", app.shown_columns())
        self.assertEqual(app.shown_columns()[-2:], ["unit", "created"])
        self.assertEqual(self.values(app, 1)["unit"], "")
        db.set_task_unit(app.conn, 1, uid)
        app.refresh()
        self.assertEqual(self.values(app, 1)["unit"], "Розница")
        self.assertEqual(app.unit_names, {1: "Розница"})
        self.assertEqual(app.people(1)["unit"], "Розница")
        db.delete_unit(app.conn, uid)
        app.refresh()
        self.assertNotIn("unit", app.shown_columns())
        self.assertEqual(app.unit_names, {})

    def test_dangling_unit_ignored(self):
        """Номер единицы, которой нет в справочнике, — столбец не показывается, ячейка пустая."""
        app = self.make_app()
        with app.conn:
            app.conn.execute("UPDATE tasks SET unit_id = 42 WHERE id = 1")
        app.refresh()
        self.assertNotIn("unit", app.shown_columns())
        self.assertEqual(app.unit_names, {})

    def test_show_units_refreshes(self):
        """☰ Меню → «Бизнес-единицы…»: после закрытия окна таблица перечитывается."""
        app = self.make_app()
        seen = {}

        class FakeUnits:
            def __init__(self, parent, conn, list_name, by, others, units_from):
                seen.update(conn=conn, name=list_name, by=by, others=others)

            def show(self):
                db.add_unit(seen["conn"], "Розница")

        with mock.patch.object(tco.todoro, "UnitsDialog", FakeUnits):
            app.show_units()
        self.pump(app)
        self.assertIs(seen["conn"], app.conn)
        self.assertIsNone(seen["by"])  # личный список — без автора
        self.assertNotIn(app.list_id, [i for i, _ in seen["others"]])
        self.assertIn("unit", app.shown_columns())


if __name__ == "__main__":
    unittest.main()
