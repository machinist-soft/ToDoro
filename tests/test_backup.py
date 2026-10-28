"""Резервные копии (backup.py) и восстановление из копии в окне (TodoApp.restore_entries,
daily_backup, ChecklistDialog). Всё — на временных файлах: db.DATA_DIR, DB_PATH, LISTS_DIR и
OLD_DB_PATHS подменены, сообщения ui.* подменены."""
import json
import shutil
import sqlite3
import sys
import tkinter as tk
import unittest
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import backup  # noqa: E402
import db  # noqa: E402
from tests.test_core import TempDir  # noqa: E402


class BackupCase(TempDir):
    """Временная папка данных программы: todoro.db, lists\\, backups\\ — всё в ней."""

    def setUp(self):
        super().setUp()
        self.conns = []
        self.works = []
        for name, value in (("DATA_DIR", self.dir), ("DB_PATH", self.dir / "todoro.db"),
                            ("LISTS_DIR", self.dir / "lists"), ("OLD_DB_PATHS", [])):
            patch = mock.patch.object(db, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.temp = self.dir / "temp"  # вместо %TEMP%\ToDoro
        patch = mock.patch.object(backup, "TEMP_DIR", self.temp)
        patch.start()
        self.addCleanup(patch.stop)
        self.prefs = self.connect(db.DB_PATH)

    def tearDown(self):
        for conn in self.conns:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        for work in self.works:
            shutil.rmtree(work, ignore_errors=True)
        super().tearDown()

    def connect(self, path, **kwargs):
        conn = db.connect(path, **kwargs)
        self.conns.append(conn)
        return conn

    def open_backup(self, path):
        work, created, entries = backup.open_backup(path)
        self.works.append(work)
        return work, created, entries

    def titles(self, conn):
        return sorted(r[0] for r in conn.execute("SELECT title FROM tasks"))

    def add_list(self, name):
        """Новый личный список в реестре; возвращает (item, соединение)."""
        file = db.new_list_file()
        item = {"id": file.removesuffix(".db"), "name": name, "file": file}
        db.save_registry(self.prefs, db.list_registry(self.prefs) + [item])
        return item, self.connect(db.LISTS_DIR / file)


class WriteZipTests(BackupCase):
    def test_zip_has_lists_and_manifest(self):
        db.add_task(self.prefs, "личная")
        item, work = self.add_list("Работа")
        db.add_task(work, "рабочая")
        target = self.dir / "копия.zip"
        count = backup.write_zip(target, backup.personal_sources(self.prefs), created="2026-10-28 12:00")
        self.assertEqual(count, 2)
        with zipfile.ZipFile(target) as archive:
            manifest = json.loads(archive.read(backup.MANIFEST).decode("utf-8"))
            names = set(archive.namelist())
        self.assertEqual(manifest["format"], backup.FORMAT)
        self.assertEqual(manifest["created"], "2026-10-28 12:00")
        self.assertEqual([(e["id"], e["name"], e["shared"]) for e in manifest["lists"]],
                         [(db.PERSONAL, "Личный", False), (item["id"], "Работа", False)])
        self.assertTrue({e["file"] for e in manifest["lists"]} <= names)
        self.assertFalse((self.dir / "копия.zip.part").exists())

    def test_missing_file_is_skipped(self):
        db.add_task(self.prefs, "личная")
        sources = [({"id": db.PERSONAL, "name": "Личный"}, db.DB_PATH),
                   ({"id": "gone", "name": "Нет файла"}, self.dir / "lists" / "gone.db")]
        target = self.dir / "копия.zip"
        self.assertEqual(backup.write_zip(target, sources), 1)
        self.assertFalse((self.dir / "lists" / "gone.db").exists())  # пустой файл не создан
        _, _, entries = self.open_backup(target)
        self.assertEqual([e["name"] for e in entries], ["Личный"])

    def test_failed_write_keeps_old_file(self):
        """Ошибка посреди записи: прежний файл с тем же именем цел, .part не остаётся."""
        target = self.dir / "копия.zip"
        target.write_bytes(b"old")
        with mock.patch.object(backup, "copy_db", side_effect=sqlite3.OperationalError("занято")):
            with self.assertRaises(sqlite3.OperationalError):
                backup.write_zip(target, backup.personal_sources(self.prefs))
        self.assertEqual(target.read_bytes(), b"old")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir() if p.name.startswith("копия")),
                         ["копия.zip"])

    def test_copy_while_list_is_open_has_all_tasks(self):
        """Копия берётся через sqlite backup — видна и запись из открытого соединения."""
        for n in range(50):
            db.add_task(self.prefs, f"задача {n}")
        target = self.dir / "копия.zip"
        backup.write_zip(target, backup.personal_sources(self.prefs))
        _, _, entries = self.open_backup(target)
        self.assertEqual(entries[0]["tasks"], 50)

    def test_attachments_and_comments_go_into_copy(self):
        tid = db.add_task(self.prefs, "с файлом")
        db.add_attachment(self.prefs, tid, "отчёт.txt", b"x" * 1000, by="Анна")
        db.add_comment(self.prefs, tid, "привет", by="Анна")
        target = self.dir / "копия.zip"
        backup.write_zip(target, backup.personal_sources(self.prefs))
        _, _, entries = self.open_backup(target)
        copy = self.connect(entries[0]["path"])
        self.assertEqual(db.attachment_data(copy, 1), b"x" * 1000)
        self.assertEqual([c[2] for c in db.list_comments(copy, tid)], ["привет"])


class DailyTests(BackupCase):
    def test_once_a_day(self):
        db.add_task(self.prefs, "личная")
        today = date(2026, 10, 28)
        made = backup.daily_personal(backup.personal_sources(self.prefs), today=today)
        self.assertEqual(made, self.dir / "backups" / "ToDoro 2026-10-28.zip")
        self.assertTrue(made.exists())
        before = made.stat().st_mtime_ns
        self.assertIsNone(backup.daily_personal(backup.personal_sources(self.prefs), today=today))
        self.assertEqual(made.stat().st_mtime_ns, before)
        nxt = backup.daily_personal(backup.personal_sources(self.prefs), today=today + timedelta(days=1))
        self.assertEqual(nxt.name, "ToDoro 2026-10-29.zip")

    def test_old_auto_copies_removed_others_kept(self):
        folder = self.dir / "backups"
        folder.mkdir()
        today = date(2026, 10, 28)
        old = today - timedelta(days=backup.BACKUP_DAYS + 1)
        edge = today - timedelta(days=backup.BACKUP_DAYS)
        files = {
            f"ToDoro {old.isoformat()}.zip": False,                         # старая ежедневная
            f"ToDoro перед восстановлением {old.isoformat()} 10-00-00.zip": False,
            f"ToDoro {edge.isoformat()}.zip": True,                         # ровно 14 дней — ещё нужна
            "ToDoro копия 28.10.2026.zip": True,                            # сохранил пользователь
            "ToDoro копия 01.01.2020.zip": True,
            "Отчёт 2020-01-01.zip": True,                                   # чужой файл
            f"ToDoro {old.isoformat()}.zip.part": False,                    # недописанная старая
            f"ToDoro {(today - timedelta(days=1)).isoformat()}.zip.part": True,  # недописанная свежая
        }
        for name in files:
            (folder / name).write_bytes(b"x")
        (folder / "ToDoro 2020-01-01.zip").mkdir()  # папка с похожим именем — не трогаем
        backup.daily_personal(backup.personal_sources(self.prefs), today=today)
        for name, kept in files.items():
            self.assertEqual((folder / name).exists(), kept, name)
        self.assertTrue((folder / "ToDoro 2020-01-01.zip").is_dir())
        self.assertTrue((folder / "ToDoro 2026-10-28.zip").exists())

    def test_safety_copy(self):
        db.add_task(self.prefs, "личная")
        target = backup.safety_copy(backup.personal_sources(self.prefs))
        self.assertEqual(target.parent, self.dir / "backups")
        self.assertRegex(target.name, r"^ToDoro перед восстановлением \d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}\.zip$")
        self.assertTrue(backup.AUTO_NAME.match(target.name))  # её тоже удалят через 14 дней
        _, _, entries = self.open_backup(target)
        self.assertEqual(entries[0]["tasks"], 1)


class OpenBackupTests(BackupCase):
    def make_zip(self, manifest, files=None, raw_manifest=None):
        path = self.dir / "копия.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(backup.MANIFEST, raw_manifest if raw_manifest is not None
                             else json.dumps(manifest, ensure_ascii=False))
            for name, data in (files or {}).items():
                archive.writestr(name, data)
        return path

    def list_bytes(self, *titles):
        path = self.dir / "src.db"
        path.unlink(missing_ok=True)
        conn = db.connect(path)
        for title in titles:
            db.add_task(conn, title)
        conn.close()
        return path.read_bytes()

    def test_roundtrip(self):
        db.add_task(self.prefs, "один")
        db.add_task(self.prefs, "два")
        target = self.dir / "копия.zip"
        backup.write_zip(target, backup.personal_sources(self.prefs), created="2026-10-28 09:15")
        work, created, entries = self.open_backup(target)
        self.assertEqual(created, "2026-10-28 09:15")
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual((entry["id"], entry["name"], entry["shared"], entry["tasks"]),
                         (db.PERSONAL, "Личный", False, 2))
        self.assertEqual(Path(entry["path"]).parent, work)

    def test_not_todoro_zip(self):
        path = self.dir / "фото.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("a.txt", "hello")
        with self.assertRaises(backup.BackupError) as caught:
            self.open_backup(path)
        self.assertIn("не резервная копия", str(caught.exception))

    def test_newer_format(self):
        path = self.make_zip({"format": backup.FORMAT + 1, "lists": []})
        with self.assertRaises(backup.BackupError) as caught:
            self.open_backup(path)
        self.assertIn("более новой версией", str(caught.exception))

    def test_broken_manifest_json(self):
        path = self.make_zip(None, raw_manifest="{не json")
        with self.assertRaises(backup.BackupError) as caught:
            self.open_backup(path)
        self.assertIn("повреждён", str(caught.exception))

    def test_manifest_not_object(self):
        """Опись — не словарь (испорченный файл): понятная ошибка, а не падение."""
        path = self.make_zip(None, raw_manifest="[1, 2]")
        with self.assertRaises(backup.BackupError):
            self.open_backup(path)

    def test_manifest_format_not_number(self):
        path = self.make_zip({"format": "2", "lists": []})
        with self.assertRaises(backup.BackupError):
            self.open_backup(path)

    def test_empty_backup(self):
        path = self.make_zip({"format": 1, "lists": []})
        with self.assertRaises(backup.BackupError) as caught:
            self.open_backup(path)
        self.assertIn("нет ни одного списка", str(caught.exception))

    def test_bad_inner_names_ignored(self):
        """Внутри копии берутся только файлы вида 01.db — никаких путей в чужие папки."""
        data = self.list_bytes("задача")
        path = self.make_zip(
            {"format": 1, "lists": [
                {"id": "a", "name": "Путь наверх", "file": "../evil.db"},
                {"id": "b", "name": "Папка", "file": "sub/02.db"},
                {"id": "c", "name": "Не db", "file": "03.txt"},
                {"id": "d", "name": "Нет в архиве", "file": "09.db"},
                {"id": "e", "name": "Нормальный", "file": "04.db"}]},
            {"../evil.db": data, "sub/02.db": data, "03.txt": data, "04.db": data})
        work, _, entries = self.open_backup(path)
        self.assertEqual([e["name"] for e in entries], ["Нормальный"])
        self.assertFalse((self.dir / "evil.db").exists())
        self.assertFalse((work.parent / "evil.db").exists())

    def test_inner_file_not_sqlite(self):
        path = self.make_zip({"format": 1, "lists": [{"id": "a", "name": "Битый", "file": "01.db"}]},
                             {"01.db": b"not a database at all" * 100})
        with self.assertRaises(backup.BackupError) as caught:
            self.open_backup(path)
        self.assertIn("«Битый»", str(caught.exception))

    def test_inner_sqlite_without_tasks(self):
        other = self.dir / "other.db"
        conn = sqlite3.connect(other)
        conn.execute("CREATE TABLE x (a)")
        conn.commit()
        conn.close()
        path = self.make_zip({"format": 1, "lists": [{"id": "a", "name": "Чужой", "file": "01.db"}]},
                             {"01.db": other.read_bytes()})
        with self.assertRaises(backup.BackupError):
            self.open_backup(path)

    def test_corrupt_zip(self):
        good = self.dir / "good.zip"
        backup.write_zip(good, backup.personal_sources(self.prefs))
        bad = self.dir / "bad.zip"
        bad.write_bytes(good.read_bytes()[: len(good.read_bytes()) // 2])
        with self.assertRaises(backup.BackupError):
            self.open_backup(bad)

    def test_temp_folder_removed_on_error(self):
        path = self.make_zip({"format": 1, "lists": []})
        with self.assertRaises(backup.BackupError):
            backup.open_backup(path)
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_work_folders_inside_temp_dir(self):
        """Рабочие папки — в TEMP_DIR (%TEMP%\\ToDoro), после записи копии их не остаётся."""
        db.add_task(self.prefs, "x")
        backup.write_zip(self.dir / "копия.zip", backup.personal_sources(self.prefs))
        self.assertEqual(list(self.temp.iterdir()), [])
        work, _, _ = self.open_backup(self.dir / "копия.zip")
        self.assertEqual(work.parent, self.temp)

    def test_manifest_lists_not_list(self):
        path = self.make_zip({"format": 1, "lists": "01.db"})
        with self.assertRaises(backup.BackupError):
            self.open_backup(path)

    def test_manifest_entry_not_object(self):
        data = self.list_bytes("x")
        path = self.make_zip({"format": 1, "lists": ["01.db", 5, {"id": "a", "name": "Ок", "file": "01.db"}]},
                             {"01.db": data})
        _, _, entries = self.open_backup(path)
        self.assertEqual([e["name"] for e in entries], ["Ок"])

    def test_missing_single_file(self):
        """Файла нет — понятная ошибка, и пустой файл на его месте не появляется."""
        src = self.dir / "нет.db"
        with self.assertRaises(backup.BackupError) as caught:
            self.open_backup(src)
        self.assertIn("не найден", str(caught.exception))
        self.assertFalse(src.exists())

    def test_single_personal_db(self):
        src = self.dir / "copy" / "todoro.db"
        src.parent.mkdir()
        conn = db.connect(src)
        db.add_task(conn, "раз")
        conn.close()
        _, created, entries = self.open_backup(src)
        self.assertIsNone(created)
        self.assertEqual((entries[0]["id"], entries[0]["name"], entries[0]["tasks"]),
                         (db.PERSONAL, "Личный", 1))
        self.assertFalse(entries[0]["shared"], "todoro.db — личный список, не общий")

    def test_single_list_db(self):
        for stem, shared in (("t1a2b3c4", True), ("0f1e2d3c4b5a", False)):
            src = self.dir / f"{stem}.db"
            db.connect(src).close()
            _, _, entries = self.open_backup(src)
            self.assertEqual((entries[0]["id"], entries[0]["name"], entries[0]["shared"]),
                             (stem, stem, shared))

    def test_single_file_not_sqlite(self):
        src = self.dir / "заметки.db"
        src.write_text("просто текст " * 200, encoding="utf-8")
        with self.assertRaises(backup.BackupError) as caught:
            self.open_backup(src)
        self.assertIn("не файл списка", str(caught.exception))

    def test_single_empty_file(self):
        src = self.dir / "пусто.db"
        src.write_bytes(b"")
        with self.assertRaises(backup.BackupError):
            self.open_backup(src)

    def test_old_version_copy_gets_new_columns(self):
        """Копия из старой версии (без новых столбцов и таблиц) — читается и дополняется."""
        old = self.dir / "old.db"
        conn = sqlite3.connect(old)
        conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                     "done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO tasks (title, done) VALUES ('старая', 0)")
        conn.commit()
        conn.close()
        path = self.make_zip({"format": 1, "lists": [{"id": db.PERSONAL, "name": "Личный", "file": "01.db"}]},
                             {"01.db": old.read_bytes()})
        _, _, entries = self.open_backup(path)
        self.assertEqual(entries[0]["tasks"], 1)
        check = sqlite3.connect(entries[0]["path"])
        cols = {r[1] for r in check.execute("PRAGMA table_info(tasks)")}
        check.close()
        self.assertTrue({"version", "unit_id", "repeat"} <= cols)
        # и восстанавливается в текущий список
        backup.restore_list(self.prefs, entries[0]["path"])
        self.assertEqual(self.titles(self.prefs), ["старая"])

    def test_missing_name_and_id(self):
        data = self.list_bytes("x")
        path = self.make_zip({"format": 1, "lists": [{"file": "01.db"}]}, {"01.db": data})
        _, _, entries = self.open_backup(path)
        self.assertEqual((entries[0]["id"], entries[0]["name"]), ("", "Список"))


class RestoreListTests(BackupCase):
    def make_copy(self):
        target = self.dir / "копия.zip"
        backup.write_zip(target, backup.personal_sources(self.prefs))
        return self.open_backup(target)[2]

    def test_replaces_content_keeps_settings(self):
        tid = db.add_task(self.prefs, "из копии")
        db.add_comment(self.prefs, tid, "комментарий", by="Анна")
        db.add_attachment(self.prefs, tid, "a.txt", b"abc")
        db.add_unit(self.prefs, "Отдел А")
        item, _ = self.add_list("Работа")
        db.set_setting(self.prefs, "user_name", "Анна")
        entries = self.make_copy()
        # после копии всё поменялось
        db.delete_task(self.prefs, tid)
        db.add_task(self.prefs, "новая после копии")
        db.add_status(self.prefs, "Лишняя колонка", "#000000")
        db.set_setting(self.prefs, "user_name", "Борис")
        item2, _ = self.add_list("Дом")
        backup.restore_list(self.prefs, entries[0]["path"])
        self.assertEqual(self.titles(self.prefs), ["из копии"])
        self.assertEqual([c[2] for c in db.list_comments(self.prefs, tid)], ["комментарий"])
        self.assertEqual(db.attachment_data(self.prefs, 1), b"abc")
        self.assertEqual([u[1] for u in db.list_units(self.prefs)], ["Отдел А"])
        self.assertNotIn("Лишняя колонка", [s[1] for s in db.list_statuses(self.prefs)])
        # настройки и реестр списков — нынешние, а не из копии
        self.assertEqual(db.get_setting(self.prefs, "user_name"), "Борис")
        self.assertEqual([i["name"] for i in db.list_registry(self.prefs)], ["Личный", "Работа", "Дом"])
        self.assertFalse(self.prefs.in_transaction)
        self.assertEqual([r[1] for r in self.prefs.execute("PRAGMA database_list")], ["main"])  # отключена

    def test_versions_higher_than_before(self):
        tid = db.add_task(self.prefs, "задача")
        entries = self.make_copy()
        for n in range(5):
            db.update_task(self.prefs, tid, f"правка {n}", None, None)
        top = db.task_meta(self.prefs, tid)["version"]
        opened = top  # кто-то открыл форму до восстановления
        backup.restore_list(self.prefs, entries[0]["path"])
        self.assertGreater(db.task_meta(self.prefs, tid)["version"], top)
        # его правка не запишется молча поверх восстановленной задачи
        self.assertFalse(db.update_task(self.prefs, tid, "поверх", None, None, version=opened))

    def test_restore_into_empty_list_and_from_empty_copy(self):
        entries = self.make_copy()  # в копии нет задач
        db.add_task(self.prefs, "будет удалена")
        backup.restore_list(self.prefs, entries[0]["path"])
        self.assertEqual(self.titles(self.prefs), [])
        self.assertTrue(db.list_statuses(self.prefs))  # колонки доски из копии на месте

    def test_inside_open_transaction(self):
        db.add_task(self.prefs, "из копии")
        entries = self.make_copy()
        self.prefs.execute("SELECT 1 FROM tasks").fetchall()
        self.prefs.execute("UPDATE settings SET value = value WHERE key = 'x'")  # открыта транзакция
        backup.restore_list(self.prefs, entries[0]["path"])
        self.assertEqual(self.titles(self.prefs), ["из копии"])

    def test_shared_connection(self):
        """Общий список (SharedConnection с окном): чтения в транзакции не мешают ATTACH."""
        shared_path = self.dir / "share" / "t123.db"
        shared_path.parent.mkdir()
        conn = self.connect(shared_path, shared=True)
        db.add_task(conn, "из копии")
        target = self.dir / "копия.zip"
        backup.write_zip(target, [({"id": "t123", "name": "Команда", "shared": True}, shared_path)])
        _, _, entries = self.open_backup(target)
        self.assertTrue(entries[0]["shared"])
        db.add_task(conn, "лишняя")
        idle = []
        conn.root = SimpleNamespace(after_idle=idle.append)
        conn.execute("SELECT COUNT(*) FROM tasks").fetchone()  # окно читает — открыта транзакция
        self.assertTrue(conn.in_transaction)
        backup.restore_list(conn, entries[0]["path"])
        for job in idle:
            job()
        conn.root = None
        self.assertEqual(self.titles(conn), ["из копии"])
        self.assertFalse(conn.in_transaction)
        other = self.connect(shared_path)  # другой участник видит восстановленное
        self.assertEqual(self.titles(other), ["из копии"])

    def test_old_attachment_column_order(self):
        """В старых списках у attachments другой порядок столбцов — копируется по именам."""
        old = self.dir / "old.db"
        conn = sqlite3.connect(old)
        conn.executescript(
            "CREATE TABLE attachments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL, "
            "name TEXT NOT NULL, size INTEGER NOT NULL, data BLOB NOT NULL, added_by TEXT, "
            "added_at TEXT NOT NULL);"
            "INSERT INTO attachments (task_id, name, size, data, added_by, added_at) "
            "VALUES (1, 'a.txt', 3, X'616263', 'Анна', '2026-01-01 10:00:00');")
        conn.close()
        oldconn = self.connect(old)
        db.add_task(oldconn, "задача")
        oldconn.close()
        backup.restore_list(self.prefs, old)
        self.assertEqual(db.attachment_data(self.prefs, 1), b"abc")
        row = self.prefs.execute("SELECT name, added_by, added_at FROM attachments").fetchone()
        self.assertEqual(tuple(row), ("a.txt", "Анна", "2026-01-01 10:00:00"))

    def test_past_reminders_marked_shown(self):
        """После восстановления не всплывают напоминания, время которых уже прошло."""
        past = db.add_task(self.prefs, "прошло")
        db.update_task(self.prefs, past, "прошло", "2020-01-01 10:00", 30)
        future = db.add_task(self.prefs, "будет")
        db.update_task(self.prefs, future, "будет", "2099-01-01 10:00", 30)
        soon = db.add_task(self.prefs, "скоро")
        due = (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")
        db.update_task(self.prefs, soon, "скоро", due, 120)  # срок впереди, напоминание уже прошло
        plain = db.add_task(self.prefs, "без напоминания")
        db.update_task(self.prefs, plain, "без напоминания", "2020-01-01 10:00", None)
        entries = self.make_copy()
        backup.restore_list(self.prefs, entries[0]["path"])
        reminded = dict(self.prefs.execute("SELECT id, reminded FROM tasks").fetchall())
        self.assertEqual(reminded, {past: 1, future: 0, soon: 1, plain: 0})
        self.assertEqual(db.due_reminders(self.prefs), [])

    def test_restore_file_own_connection(self):
        item, conn = self.add_list("Работа")
        db.add_task(conn, "из копии")
        target = self.dir / "копия.zip"
        backup.write_zip(target, [(dict(item, shared=False), db.list_path(item))])
        db.add_task(conn, "потом")
        _, _, entries = self.open_backup(target)
        backup.restore_file(db.list_path(item), entries[0]["path"])
        self.assertEqual(self.titles(conn), ["из копии"])


class ScrubTests(BackupCase):
    """Настройки (ключ телефона, путь к общей папке) не попадают ни в zip, ни в новый список."""
    TOKEN = "секретный-ключ-телефона-1234567890"

    def setUp(self):
        super().setUp()
        db.set_setting(self.prefs, "phone_token", self.TOKEN)
        db.set_setting(self.prefs, "shared_folder", "\\\\server\\share\\ToDoro")
        db.add_task(self.prefs, "личная")

    def assert_clean(self, data, where=""):
        self.assertNotIn(self.TOKEN.encode("utf-8"), data, where)
        self.assertNotIn(b"phone_token", data, where)
        self.assertNotIn(b"\\\\server", data, where)

    def test_token_not_in_zip_bytes(self):
        target = self.dir / "копия.zip"
        backup.write_zip(target, backup.personal_sources(self.prefs))
        with zipfile.ZipFile(target) as archive:
            for name in archive.namelist():
                self.assert_clean(archive.read(name), name)
        self.assertEqual(db.get_setting(self.prefs, "phone_token"), self.TOKEN)  # в самом списке остался

    def test_daily_and_safety_copies_scrubbed(self):
        for target in (backup.daily_personal(backup.personal_sources(self.prefs), today=date(2026, 10, 28)),
                       backup.safety_copy(backup.personal_sources(self.prefs))):
            with zipfile.ZipFile(target) as archive:
                for name in archive.namelist():
                    self.assert_clean(archive.read(name), name)

    def test_old_copy_with_settings_scrubbed_on_open(self):
        """Копия, сделанная до очистки (настройки внутри): при открытии они убираются,
        новый список из неё — без ключа телефона."""
        raw = self.dir / "raw.zip"
        snapshot = self.dir / "snap.db"
        backup.copy_db(db.DB_PATH, snapshot)
        with zipfile.ZipFile(raw, "w") as archive:
            archive.writestr(backup.MANIFEST, json.dumps(
                {"format": 1, "lists": [{"id": "gone", "name": "Старый", "file": "01.db"}]}))
            archive.write(snapshot, "01.db")
        _, _, entries = self.open_backup(raw)
        self.assert_clean(Path(entries[0]["path"]).read_bytes())
        item = backup.add_as_new_list(self.prefs, entries[0], "Старый")
        new = db.list_path(item)
        self.assert_clean(new.read_bytes())
        conn = self.connect(new)
        self.assertIsNone(db.get_setting(conn, "phone_token"))
        self.assertEqual(self.titles(conn), ["личная"])

    def test_single_db_scrubbed_but_source_untouched(self):
        src = self.dir / "copy" / "todoro.db"
        src.parent.mkdir()
        backup.copy_db(db.DB_PATH, src)
        before = src.read_bytes()
        _, _, entries = self.open_backup(src)
        self.assert_clean(Path(entries[0]["path"]).read_bytes())
        self.assertEqual(src.read_bytes(), before)  # сам выбранный файл не меняется

    def test_restore_keeps_own_token(self):
        target = self.dir / "копия.zip"
        backup.write_zip(target, backup.personal_sources(self.prefs))
        _, _, entries = self.open_backup(target)
        backup.restore_list(self.prefs, entries[0]["path"])
        self.assertEqual(db.get_setting(self.prefs, "phone_token"), self.TOKEN)

    def test_scrub_file_without_settings(self):
        path = self.dir / "x.db"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE tasks (id INTEGER)")
        conn.commit()
        conn.close()
        backup.scrub(path)  # таблицы settings нет — не падает


class AddAsNewListTests(BackupCase):
    def test_copy_as_new_list_and_item(self):
        db.add_task(self.prefs, "личная")
        target = self.dir / "копия.zip"
        backup.write_zip(target, backup.personal_sources(self.prefs))
        _, _, entries = self.open_backup(target)
        file = backup.copy_as_new_list(entries[0])
        self.assertRegex(file, r"^[0-9a-f]{12}\.db$")
        self.assertTrue((db.LISTS_DIR / file).exists())
        self.assertEqual(backup.new_list_item(file, "Имя"),
                         {"id": file.removesuffix(".db"), "name": "Имя", "file": file})
        self.assertEqual([i["id"] for i in db.list_registry(self.prefs)], [db.PERSONAL])  # реестр не тронут

    def test_new_personal_list(self):
        src_item, src = self.add_list("Работа")
        db.add_task(src, "рабочая")
        target = self.dir / "копия.zip"
        backup.write_zip(target, backup.personal_sources(self.prefs))
        _, _, entries = self.open_backup(target)
        entry = next(e for e in entries if e["name"] == "Работа")
        item = backup.add_as_new_list(self.prefs, entry, "Работа (из копии)")
        self.assertNotEqual(item["id"], src_item["id"])
        registry = db.list_registry(self.prefs)
        self.assertEqual([i["name"] for i in registry], ["Личный", "Работа", "Работа (из копии)"])
        self.assertTrue((db.LISTS_DIR / item["file"]).exists())
        self.assertEqual(self.titles(self.connect(db.list_path(item))), ["рабочая"])


# ---------- окно: восстановление и копии из меню ----------

import todoro as T  # noqa: E402


def run_now(root, work, done):
    """in_background без потока: сразу work(), потом done(результат, ошибка)."""
    try:
        result, error = work(), None
    except Exception as problem:  # noqa: BLE001
        result, error = None, problem
    done(result, error)


class FakeRoot:
    def __init__(self):
        self.jobs = []

    def configure(self, **kwargs):
        pass

    def update_idletasks(self):
        pass

    def after(self, ms, func):
        self.jobs.append((ms, func))
        return f"after#{len(self.jobs)}"


class RestoreEntriesTests(BackupCase):
    """TodoApp.restore_entries на подставном окне: ChecklistDialog и ui.* подменены."""

    def setUp(self):
        super().setUp()
        self.ui = {}
        for name in ("showinfo", "showwarning", "showerror", "askyesno"):
            patch = mock.patch.object(T.ui, name, return_value=True)
            self.ui[name] = patch.start()
            self.addCleanup(patch.stop)
        self.waits = []

        def wait_dialog(parent, title, text):
            wait = mock.Mock(text=text)
            self.waits.append(wait)
            return wait
        for patch in (mock.patch.object(T, "in_background", run_now),
                      mock.patch.object(T, "WaitDialog", side_effect=wait_dialog)):
            patch.start()
            self.addCleanup(patch.stop)
        self.cleanups = 0
        self.online = False
        self.shared_items = []
        self.list_conns = {db.PERSONAL: self.prefs}
        app = SimpleNamespace(prefs=self.prefs, root=FakeRoot(), team=None, fresh_ids=[1],
                              list_counter=5, refreshed=0)
        app.share_online = lambda: self.online
        app.load_lists = lambda: setattr(app, "lists", [dict(i, shared=False) for i in
                                                        db.list_registry(self.prefs)] + self.shared_items)
        app.list_conn = self.list_conn
        app.list_file = lambda item: T.TodoApp.list_file(app, item)
        app.clear_selection = lambda: None
        app.show_list_name = lambda: None
        app.refresh = lambda: setattr(app, "refreshed", app.refreshed + 1)
        app.load_lists()
        self.app = app

    def list_conn(self, list_id):
        if list_id not in self.list_conns:
            item = next(i for i in self.app.lists if i["id"] == list_id)
            self.list_conns[list_id] = self.connect(db.list_path(item))
        return self.list_conns[list_id]

    def restore(self, path, picked):
        """Открыть копию и «отметить» пункты picked (None — всё доступное)."""
        _, created, entries = self.open_backup(path)
        dialog = mock.Mock()

        def make(parent, title, heading, choices, ok_text, hint=""):
            dialog.choices, dialog.hint = choices, hint
            keys = [k for k, _, enabled in choices if enabled] if picked is None else picked
            return mock.Mock(show=mock.Mock(return_value=keys))
        def cleanup():
            self.cleanups += 1
        with mock.patch.object(T, "ChecklistDialog", side_effect=make):
            T.TodoApp.restore_entries(self.app, created, entries, cleanup)
        self.assertEqual(self.cleanups, 1, "cleanup() — ровно один раз при любом исходе")
        for wait in self.waits:
            wait.close.assert_called_once()
        return dialog, entries

    def backups(self):
        folder = self.dir / "backups"
        return sorted(p.name for p in folder.iterdir()) if folder.exists() else []

    def test_replace_existing_with_confirmation_and_safety_copy(self):
        db.add_task(self.prefs, "из копии")
        db.set_setting(self.prefs, "user_name", "Анна")
        path = self.dir / "копия.zip"
        backup.write_zip(path, backup.personal_sources(self.prefs), created="2026-10-28 09:15")
        db.add_task(self.prefs, "потом")
        db.set_setting(self.prefs, "user_name", "Борис")
        dialog, _ = self.restore(path, None)
        self.assertIn("заменит задачи списка «Личный»", dialog.choices[0][1])
        self.assertIn("Копия сделана 28.10.2026 в 09:15", dialog.hint)
        self.ui["askyesno"].assert_called_once()
        self.assertIn("«Личный»", self.ui["askyesno"].call_args[0][1])
        self.assertEqual(self.titles(self.prefs), ["из копии"])
        self.assertEqual(db.get_setting(self.prefs, "user_name"), "Борис")
        safety = [n for n in self.backups() if n.startswith("ToDoro перед восстановлением")]
        self.assertEqual(len(safety), 1)
        _, _, saved = self.open_backup(self.dir / "backups" / safety[0])
        self.assertEqual(saved[0]["tasks"], 2)  # прежнее состояние — с задачей «потом»
        self.ui["showinfo"].assert_called_once()
        self.assertIn("Восстановлено: «Личный»", self.ui["showinfo"].call_args[0][1])
        self.assertEqual((self.app.fresh_ids, self.app.list_counter, self.app.refreshed), ([], None, 1))

    def test_declined_confirmation_changes_nothing(self):
        db.add_task(self.prefs, "из копии")
        path = self.dir / "копия.zip"
        backup.write_zip(path, backup.personal_sources(self.prefs))
        db.add_task(self.prefs, "потом")
        self.ui["askyesno"].return_value = False
        self.restore(path, None)
        self.assertEqual(self.titles(self.prefs), ["из копии", "потом"])
        self.assertEqual(self.backups(), [])
        self.ui["showinfo"].assert_not_called()

    def test_nothing_picked(self):
        db.add_task(self.prefs, "из копии")
        path = self.dir / "копия.zip"
        backup.write_zip(path, backup.personal_sources(self.prefs))
        db.add_task(self.prefs, "потом")
        self.restore(path, [])
        self.assertEqual(len(self.titles(self.prefs)), 2)
        self.ui["askyesno"].assert_not_called()

    def test_missing_list_added_as_new_with_suffix(self):
        """Списка из копии уже нет — становится новым личным; имя занято — « (из копии)»;
        без замены не спрашиваем и копию «перед восстановлением» не делаем."""
        old_item, old = self.add_list("Работа")
        db.add_task(old, "старая рабочая")
        path = self.dir / "копия.zip"
        backup.write_zip(path, [(dict(old_item, shared=False), db.list_path(old_item))])
        # список удалили и завели новый с тем же именем
        db.save_registry(self.prefs, [i for i in db.list_registry(self.prefs) if i["id"] != old_item["id"]])
        self.add_list("Работа")
        self.app.load_lists()
        dialog, _ = self.restore(path, None)
        self.assertIn("станет новым личным списком", dialog.choices[0][1])
        self.ui["askyesno"].assert_not_called()
        self.assertEqual(self.backups(), [])
        names = [i["name"] for i in db.list_registry(self.prefs)]
        self.assertEqual(names, ["Личный", "Работа", "Работа (из копии)"])
        added = db.list_registry(self.prefs)[-1]
        self.assertEqual(self.titles(self.connect(db.list_path(added))), ["старая рабочая"])
        self.assertIn("«Работа (из копии)»", self.ui["showinfo"].call_args[0][1])

    def test_missing_list_keeps_free_name(self):
        item, conn = self.add_list("Дом")
        path = self.dir / "копия.zip"
        backup.write_zip(path, [(dict(item, shared=False), db.list_path(item))])
        db.save_registry(self.prefs, [i for i in db.list_registry(self.prefs) if i["id"] != item["id"]])
        self.app.load_lists()
        self.restore(path, None)
        self.assertEqual([i["name"] for i in db.list_registry(self.prefs)], ["Личный", "Дом"])

    def test_shared_list_offline_not_available(self):
        share = self.dir / "share"
        share.mkdir()
        conn = self.connect(share / "t777.db")
        db.add_task(conn, "общая")
        path = self.dir / "копия.zip"
        backup.write_zip(path, [({"id": "t777", "name": "Команда", "shared": True}, share / "t777.db")])
        self.shared_items = [{"id": "t777", "name": "Команда", "shared": True, "file": "t777.db"}]
        self.app.load_lists()
        self.online = False
        dialog, _ = self.restore(path, None)
        self.assertEqual(len(dialog.choices), 1)
        key, text, enabled = dialog.choices[0]
        self.assertFalse(enabled)
        self.assertIn("нет связи", text)

    def test_shared_list_online_replaced_with_warning(self):
        share = self.dir / "share"
        share.mkdir()
        conn = self.connect(share / "t777.db", shared=True)
        db.add_task(conn, "общая из копии")
        path = self.dir / "копия.zip"
        backup.write_zip(path, [({"id": "t777", "name": "Команда", "shared": True}, share / "t777.db")])
        db.add_task(conn, "лишняя")
        self.shared_items = [{"id": "t777", "name": "Команда", "shared": True, "file": "t777.db"}]
        self.app.team = SimpleNamespace(path=lambda item: share / item["file"])
        self.online = True
        self.app.load_lists()
        self.list_conns["t777"] = conn
        self.restore(path, None)
        self.assertIn("изменится у всех участников", self.ui["askyesno"].call_args[0][1])
        self.assertEqual(self.titles(conn), ["общая из копии"])
        self.assertTrue(any(n.startswith("ToDoro перед восстановлением") for n in self.backups()))

    def test_safety_copy_failure_cancels_restore(self):
        db.add_task(self.prefs, "из копии")
        path = self.dir / "копия.zip"
        backup.write_zip(path, backup.personal_sources(self.prefs))
        db.add_task(self.prefs, "потом")
        with mock.patch.object(backup, "safety_copy", side_effect=OSError(28, "No space left on device")):
            self.restore(path, None)
        self.assertEqual(self.titles(self.prefs), ["из копии", "потом"])
        self.ui["showerror"].assert_called_once()
        self.assertIn("восстановление отменено", self.ui["showerror"].call_args[0][1])

    def test_failed_list_reported(self):
        db.add_task(self.prefs, "из копии")
        path = self.dir / "копия.zip"
        backup.write_zip(path, backup.personal_sources(self.prefs))
        with mock.patch.object(backup, "restore_list", side_effect=sqlite3.OperationalError("database is locked")):
            self.restore(path, None)
        self.ui["showwarning"].assert_called_once()
        self.assertIn("Не удалось восстановить", self.ui["showwarning"].call_args[0][1])
        self.ui["showinfo"].assert_not_called()

    def test_work_runs_in_background_with_wait_dialog(self):
        db.add_task(self.prefs, "из копии")
        path = self.dir / "копия.zip"
        backup.write_zip(path, backup.personal_sources(self.prefs))
        with mock.patch.object(backup, "restore_list", wraps=backup.restore_list) as restore:
            self.restore(path, None)
        self.assertEqual(len(self.waits), 1)
        self.assertIn("Восстанавливаю", self.waits[0].text)
        restore.assert_called_once()
        self.assertIsNot(restore.call_args[0][0], self.prefs)  # своё соединение, не соединение окна

    def test_unexpected_error_closes_wait_and_cleans(self):
        item, conn = self.add_list("Дом")
        path = self.dir / "копия.zip"
        backup.write_zip(path, [(dict(item, shared=False), db.list_path(item))])
        db.save_registry(self.prefs, [i for i in db.list_registry(self.prefs) if i["id"] != item["id"]])
        self.app.load_lists()
        with mock.patch.object(backup, "copy_as_new_list", side_effect=RuntimeError("сбой")):
            self.restore(path, None)  # helper проверяет cleanup и закрытие WaitDialog
        self.ui["showerror"].assert_called_once()
        self.assertEqual([i["name"] for i in db.list_registry(self.prefs)], ["Личный"])

    def test_shared_from_copy_offline_unknown_list(self):
        """Общая папка задана, связи нет (team is None) — общего списка нет в self.lists,
        но из копии он не должен стать «новым личным»."""
        share = self.dir / "share"
        share.mkdir()
        db.connect(share / "t555.db").close()
        path = self.dir / "копия.zip"
        backup.write_zip(path, [({"id": "t555", "name": "Команда", "shared": True}, share / "t555.db")])
        db.set_setting(self.prefs, "shared_folder", str(share))
        dialog, _ = self.restore(path, [])
        self.assertFalse(dialog.choices[0][2])
        self.assertIn("нет связи", dialog.choices[0][1])

    def test_shared_from_copy_without_shared_folder_becomes_personal(self):
        share = self.dir / "share"
        share.mkdir()
        conn = self.connect(share / "t555.db")
        db.add_task(conn, "общая")
        path = self.dir / "копия.zip"
        backup.write_zip(path, [({"id": "t555", "name": "Команда", "shared": True}, share / "t555.db")])
        dialog, _ = self.restore(path, None)
        self.assertTrue(dialog.choices[0][2])
        self.assertIn("станет новым личным списком", dialog.choices[0][1])
        added = db.list_registry(self.prefs)[-1]
        self.assertEqual(added["name"], "Команда")
        self.assertIsNotNone(added["file"])
        self.assertEqual(self.titles(self.connect(db.list_path(added))), ["общая"])

    def test_name_suffix_numbers(self):
        """Заняты «Работа» и «Работа (из копии)» — новый получает «Работа (из копии 2)»;
        два одноимённых списка из одной копии тоже получают разные имена."""
        a, ca = self.add_list("Работа")
        b, cb = self.add_list("Работа")
        db.add_task(ca, "a")
        db.add_task(cb, "b")
        path = self.dir / "копия.zip"
        backup.write_zip(path, [(dict(a, shared=False), db.list_path(a)), (dict(b, shared=False), db.list_path(b))])
        db.save_registry(self.prefs, [{"id": db.PERSONAL, "name": "Личный", "file": None},
                                      {"id": "x1", "name": "Работа", "file": "x1.db"},
                                      {"id": "x2", "name": "Работа (из копии)", "file": "x2.db"}])
        self.app.load_lists()
        self.restore(path, None)
        names = [i["name"] for i in db.list_registry(self.prefs)]
        self.assertEqual(names, ["Личный", "Работа", "Работа (из копии)", "Работа (из копии 2)",
                                 "Работа (из копии 3)"])

    def test_attachment_names_from_copy_after_restore(self):
        """Копия с другого компьютера: те же номера задачи и вложения, но другой файл.
        После восстановления list_attachments берёт имена из копии, а не запомненные прежние."""
        tid = db.add_task(self.prefs, "здесь")
        db.add_attachment(self.prefs, tid, "старое.txt", b"old")
        self.assertEqual([a[1] for a in db.list_attachments(self.prefs, tid)], ["старое.txt"])  # запомнено
        (self.dir / "другой").mkdir()
        other = self.connect(self.dir / "другой" / "todoro.db")
        other_tid = db.add_task(other, "там")
        db.add_attachment(other, other_tid, "из копии.txt", b"new")
        self.assertEqual(other_tid, tid)
        path = self.dir / "копия.zip"
        backup.write_zip(path, [({"id": db.PERSONAL, "name": "Личный", "shared": False},
                                 self.dir / "другой" / "todoro.db")])
        self.restore(path, None)
        self.assertEqual(self.titles(self.prefs), ["там"])
        self.assertEqual([a[1:3] for a in db.list_attachments(self.prefs, tid)], [("из копии.txt", 3)])
        self.assertEqual(db.attachment_data(self.prefs, 1), b"new")

    def test_attachment_cache_forgotten_on_restore(self):
        """restore_entries вызывает db.forget_attachment_info после восстановления."""
        db.add_task(self.prefs, "задача")
        path = self.dir / "копия.zip"
        backup.write_zip(path, backup.personal_sources(self.prefs))
        with mock.patch.object(db, "forget_attachment_info", wraps=db.forget_attachment_info) as forget:
            self.restore(path, None)
        forget.assert_called_once_with()


class DailyBackupWindowTests(BackupCase):
    def test_daily_backup_runs_in_background_and_repeats_hourly(self):
        db.add_task(self.prefs, "личная")
        app = SimpleNamespace(prefs=self.prefs, root=FakeRoot(), BACKUP_CHECK_MS=T.TodoApp.BACKUP_CHECK_MS,
                              restoring=False)
        app.daily_backup = lambda: T.TodoApp.daily_backup(app)
        calls = []

        def run_now(root, work, done):
            calls.append(work)
            result = work()
            done(result, None)
        with mock.patch.object(T, "in_background", run_now):
            T.TodoApp.daily_backup(app)
        self.assertEqual(len(calls), 1)
        self.assertTrue((self.dir / "backups" / f"ToDoro {date.today().isoformat()}.zip").exists())
        self.assertEqual(app.root.jobs[0][0], 60 * 60 * 1000)

    def test_daily_backup_error_is_silent(self):
        app = SimpleNamespace(prefs=self.prefs, root=FakeRoot(), BACKUP_CHECK_MS=T.TodoApp.BACKUP_CHECK_MS,
                              restoring=False)
        app.daily_backup = lambda: T.TodoApp.daily_backup(app)

        def run_now(root, work, done):
            done(None, OSError("диск полон"))
        with mock.patch.object(T, "in_background", run_now), \
                mock.patch.object(T.ui, "showerror") as error:
            T.TodoApp.daily_backup(app)
        error.assert_not_called()

    def test_timers_skip_work_while_restoring(self):
        """Пока идёт восстановление, таймеры окна файлы списков не читают, но перезапускаются."""
        app = SimpleNamespace(prefs=self.prefs, root=FakeRoot(), BACKUP_CHECK_MS=T.TodoApp.BACKUP_CHECK_MS,
                              restoring=True, team=None, probe=None)
        app.daily_backup = app.check_reminders = app.watch_changes = lambda: None
        touched = mock.Mock(side_effect=AssertionError("файлы списков читать нельзя"))
        app.do_check_reminders = app.check_local_changes = app.go_offline = touched
        with mock.patch.object(T, "in_background", touched):
            T.TodoApp.daily_backup(app)
            T.TodoApp.check_reminders(app)
            T.TodoApp.watch_changes(app)
        touched.assert_not_called()
        self.assertEqual(len(app.root.jobs), 3)


class MenuCommandTests(BackupCase):
    """save_backup и restore_backup: окно выбора файла, WaitDialog, in_background и ui.* подменены."""

    def setUp(self):
        super().setUp()
        self.ui = {}
        for name in ("showinfo", "showwarning", "showerror", "askyesno"):
            patch = mock.patch.object(T.ui, name, return_value=True)
            self.ui[name] = patch.start()
            self.addCleanup(patch.stop)
        self.waits = []

        def wait_dialog(parent, title, text):
            self.waits.append(mock.Mock(text=text))
            return self.waits[-1]
        for patch in (mock.patch.object(T, "in_background", run_now),
                      mock.patch.object(T, "WaitDialog", side_effect=wait_dialog)):
            patch.start()
            self.addCleanup(patch.stop)
        app = SimpleNamespace(prefs=self.prefs, root=FakeRoot(), team=None)
        app.finish_editing = lambda: None
        app.share_online = lambda: False
        app.lists = [dict(i, shared=False) for i in db.list_registry(self.prefs)]
        app.load_lists = lambda: None
        app.list_file = lambda item: T.TodoApp.list_file(app, item)
        self.app = app

    def checklist(self, picked):
        return mock.patch.object(T, "ChecklistDialog",
                                 return_value=mock.Mock(show=mock.Mock(return_value=picked)))

    def test_save_backup(self):
        db.add_task(self.prefs, "личная")
        target = self.dir / "моя копия.zip"
        with self.checklist([db.PERSONAL]), \
                mock.patch.object(T.filedialog, "asksaveasfilename", return_value=str(target)) as ask:
            T.TodoApp.save_backup(self.app)
        self.assertRegex(ask.call_args.kwargs["initialfile"], r"^ToDoro копия \d\d\.\d\d\.\d{4}\.zip$")
        self.assertTrue(target.exists())
        self.waits[0].close.assert_called_once()
        self.ui["showinfo"].assert_called_once()
        self.assertIn("списков: 1", self.ui["showinfo"].call_args[0][1])

    def test_save_backup_cancelled_file_dialog(self):
        with self.checklist([db.PERSONAL]), \
                mock.patch.object(T.filedialog, "asksaveasfilename", return_value=""):
            T.TodoApp.save_backup(self.app)
        self.assertEqual(self.waits, [])
        self.ui["showinfo"].assert_not_called()

    def test_save_backup_error(self):
        target = self.dir / "нет папки" / "копия.zip"
        with self.checklist([db.PERSONAL]), \
                mock.patch.object(T.filedialog, "asksaveasfilename", return_value=str(target)):
            T.TodoApp.save_backup(self.app)
        self.waits[0].close.assert_called_once()
        self.ui["showerror"].assert_called_once()
        self.assertIn("Не удалось сохранить", self.ui["showerror"].call_args[0][1])

    def test_restore_backup_bad_file(self):
        bad = self.dir / "не копия.zip"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("a.txt", "x")
        self.app.restore_entries = mock.Mock()
        with mock.patch.object(T.filedialog, "askopenfilename", return_value=str(bad)):
            T.TodoApp.restore_backup(self.app)
        self.waits[0].close.assert_called_once()
        self.ui["showerror"].assert_called_once()
        self.assertIn("не резервная копия", self.ui["showerror"].call_args[0][1])
        self.app.restore_entries.assert_not_called()
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_restore_backup_cleanup_removes_work_folder(self):
        db.add_task(self.prefs, "личная")
        path = self.dir / "копия.zip"
        backup.write_zip(path, backup.personal_sources(self.prefs))
        got = {}

        def entries(created, items, cleanup):
            got["work"] = Path(items[0]["path"]).parent
            self.assertTrue(got["work"].exists())
            cleanup()
        self.app.restore_entries = entries
        with mock.patch.object(T.filedialog, "askopenfilename", return_value=str(path)):
            T.TodoApp.restore_backup(self.app)
        self.assertFalse(got["work"].exists())

    def test_restore_backup_cancelled_file_dialog(self):
        with mock.patch.object(T.filedialog, "askopenfilename", return_value=""):
            T.TodoApp.restore_backup(self.app)
        self.assertEqual(self.waits, [])


class ChecklistDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.geometry("300x200+-5000+-5000")
        T.setup_style(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def make(self, choices):
        dialog = T.ChecklistDialog(self.root, "Резервная копия", "Какие списки", choices, "Сохранить…", "подсказка")
        dialog.withdraw()
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        return dialog

    def test_enabled_checked_disabled_not(self):
        dialog = self.make([("a", "Личный", True), ("b", "Команда · общий", False), ("c", "Дом", True)])
        self.assertEqual([var.get() for _, var in dialog.marks], [True, False, True])
        with mock.patch.object(T.ui, "showwarning") as warn:
            dialog.ok()
        warn.assert_not_called()
        self.assertEqual(dialog.result, ["a", "c"])

    def test_nothing_picked_warns_and_stays_open(self):
        dialog = self.make([("a", "Личный", True)])
        dialog.marks[0][1].set(False)
        with mock.patch.object(T.ui, "showwarning") as warn:
            dialog.ok()
        warn.assert_called_once()
        self.assertIn("хотя бы один", warn.call_args[0][1])
        self.assertIsNone(dialog.result)
        self.assertTrue(dialog.winfo_exists())

    def test_all_disabled(self):
        dialog = self.make([("b", "Команда · общий", False)])
        with mock.patch.object(T.ui, "showwarning") as warn:
            dialog.ok()
        warn.assert_called_once()

    def test_wait_dialog_close(self):
        """WaitDialog: крестик не закрывает, close() закрывает, повторный close() не падает."""
        wait = T.WaitDialog(self.root, "Резервная копия", "Сохраняю…")
        wait.geometry("+-5000+-5000")
        self.addCleanup(lambda: wait.winfo_exists() and wait.destroy())
        wait.update_idletasks()
        wait.tk.call(wait.protocol("WM_DELETE_WINDOW"))  # «нажали крестик»
        self.assertTrue(wait.winfo_exists())
        wait.close()
        self.assertFalse(wait.winfo_exists())
        wait.close()


if __name__ == "__main__":
    unittest.main()
