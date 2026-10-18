"""Автоматические проверки ToDoro (без окон): база, общие списки, CSV, обновления, поиск.

Запуск из папки проекта:  python -m unittest discover tests
Работают на временных файлах — данные пользователя не трогают.
"""
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import outlook  # noqa: E402
import team  # noqa: E402
import updater  # noqa: E402


class TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-test-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class DatabaseTests(TempDir):
    def test_new_list_has_default_columns(self):
        conn = db.connect(self.dir / "a.db")
        self.assertEqual([s[1] for s in db.list_statuses(conn)], ["Новая", "В работе", "Выполнено"])

    def test_opening_list_writes_nothing(self):
        """Открытие списка не должно ничего записывать: в общих списках любая запись
        заставляет программы остальных участников перечитывать список."""
        path = self.dir / "a.db"
        db.add_task(db.connect(path), "задача")
        first = db.connect(path)
        before = first.execute("PRAGMA data_version").fetchone()[0]
        db.connect(path)  # «другой участник» открывает тот же список
        self.assertEqual(first.execute("PRAGMA data_version").fetchone()[0], before)

    def test_task_row_and_people(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт", created_by="Анна")
        db.set_assignee(conn, tid, "Борис", by="Анна")
        self.assertEqual(db.get_task_row(conn, tid)[:2], (tid, "отчёт"))
        self.assertIsNone(db.get_task_row(conn, 999))
        self.assertEqual(db.task_people(conn), ({tid: "Анна"}, {tid: "Борис"}))

    def test_version_protects_from_overwrite(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "отчёт")
        opened = db.task_meta(conn, tid)["version"]  # Анна открыла форму
        db.update_task(conn, tid, "отчёт", "2030-01-01 09:00", None, by="Борис")  # Борис поменял срок
        saved = db.update_task(conn, tid, "отчёт v2", None, None, by="Анна", version=opened)
        self.assertFalse(saved)  # правка Анны не затёрла правку Бориса
        meta = db.task_meta(conn, tid)
        self.assertEqual((meta["updated_by"], db.get_task(conn, tid)[0]), ("Борис", "отчёт"))

    def test_done_moves_to_done_column_and_back(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "задача")
        self.assertTrue(db.set_done(conn, tid, True))
        self.assertEqual(db.count_done_today(conn), 1)
        db.set_done(conn, tid, False)
        self.assertEqual(db.count_done_today(conn), 0)

    def test_move_task_between_lists_keeps_fields(self):
        src, dst = db.connect(self.dir / "a.db"), db.connect(self.dir / "b.db")
        tid = db.add_task(src, "перенести", created_by="Анна")
        db.update_task(src, tid, "перенести", "2030-01-01 09:00", 60, True, False, "описание")
        db.set_assignee(src, tid, "Борис")
        new = db.move_task_to(src, tid, dst)
        self.assertIsNone(db.get_task(src, tid))
        self.assertEqual(db.get_task(dst, new), ("перенести", "2030-01-01 09:00", 60, 1, 0, "описание"))
        self.assertEqual(db.task_people(dst), ({new: "Анна"}, {new: "Борис"}))

    def test_shared_reminders_go_to_assignee(self):
        conn = db.connect(self.dir / "a.db")
        past = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
        tid = db.add_task(conn, "звонок", created_by="Анна")
        db.update_task(conn, tid, "звонок", past, 30)
        self.assertEqual(len(db.shared_reminders(conn, "Анна")), 1)  # исполнителя нет — автору
        db.set_assignee(conn, tid, "Борис")
        self.assertEqual(len(db.shared_reminders(conn, "Анна")), 0)
        self.assertEqual(len(db.shared_reminders(conn, "Борис")), 1)


    def test_broken_reminder_does_not_break_others(self):
        """Огромное число минут (из CSV, с телефона, из другой версии в общем списке) раньше
        роняло проверку напоминаний — и напоминаний не было совсем."""
        conn = db.connect(self.dir / "a.db")
        broken = db.add_task(conn, "испорчена", created_by="Аня")
        fine = db.add_task(conn, "нормальная", created_by="Аня")
        db.update_task(conn, broken, "испорчена", "2026-01-01 10:00", 10**15)
        db.update_task(conn, fine, "нормальная", "2026-01-01 10:00", 30)
        now = datetime(2026, 1, 2)
        self.assertEqual([t[0] for t in db.due_reminders(conn, now)], [fine])
        self.assertEqual([t[1] for t in db.shared_reminders(conn, "Аня", now)], [fine])
        self.assertEqual([t[0] for t in db.pending_tasks(conn, now=now)], [fine])

    def test_attachment_info_without_reading_files(self):
        """Содержимое файла — последний столбец (новые списки), а в старых списках сведения
        о вложении читаются один раз: иначе SQLite каждый раз читал бы весь файл."""
        conn = db.connect(self.dir / "new.db")
        columns = [row[1] for row in conn.execute("PRAGMA table_info(attachments)")]
        self.assertEqual(columns[-1], "data")
        old = sqlite3.connect(self.dir / "old.db")  # таблица в порядке столбцов версий до 2.17
        old.execute("CREATE TABLE attachments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER "
                    "NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL, data BLOB NOT NULL, "
                    "added_by TEXT, added_at TEXT NOT NULL)")
        old.commit()
        old.close()
        conn = db.connect(self.dir / "old.db")
        task = db.add_task(conn, "с файлами")
        first = db.add_attachment(conn, task, "большой.bin", b"x" * 300_000, by="Аня")
        second = db.add_attachment(conn, task, "ещё.txt", b"y", by="Борис")
        self.assertEqual([a[:4] for a in db.list_attachments(conn, task)],
                         [(first, "большой.bin", 300_000, "Аня"), (second, "ещё.txt", 1, "Борис")])
        queries = []
        conn.set_trace_callback(queries.append)
        self.assertEqual(len(db.list_attachments(conn, task)), 2)
        self.assertFalse([q for q in queries if "added_by" in q])  # второй раз — из памяти
        conn.set_trace_callback(None)
        db.delete_attachment(conn, first)
        self.assertEqual([a[0] for a in db.list_attachments(conn, task)], [second])

    def test_attachments_and_comments(self):
        conn = db.connect(self.dir / "a.db")
        task = db.add_task(conn, "с файлами")
        other = db.add_task(conn, "без файлов")
        file_id = db.add_attachment(conn, task, "отчёт.pdf", b"%PDF-1.4 data", by="Аня")
        db.add_comment(conn, task, "первый", by="Аня")
        db.add_comment(conn, task, "второй", by="Борис")
        self.assertEqual(db.attachment_data(conn, file_id), b"%PDF-1.4 data")
        self.assertEqual([a[1:4] for a in db.list_attachments(conn, task)], [("отчёт.pdf", 13, "Аня")])
        self.assertEqual([c[2] for c in db.list_comments(conn, task)], ["первый", "второй"])
        self.assertEqual(db.extras_counts(conn), {task: (1, 2)})
        # при переносе в другой список файлы и комментарии едут вместе с задачей
        dst = db.connect(self.dir / "b.db")
        new_id = db.move_task_to(conn, task, dst)
        self.assertEqual(db.extras_counts(dst), {new_id: (1, 2)})
        self.assertEqual(db.attachment_data(dst, db.list_attachments(dst, new_id)[0][0]), b"%PDF-1.4 data")
        self.assertEqual(db.extras_counts(conn), {})  # в старом списке ничего не осталось
        # удаление задачи убирает и её файлы с комментариями
        db.add_comment(dst, new_id, "третий")
        db.delete_task(dst, new_id)
        self.assertEqual(dst.execute("SELECT COUNT(*) FROM attachments").fetchone()[0], 0)
        self.assertEqual(dst.execute("SELECT COUNT(*) FROM comments").fetchone()[0], 0)
        self.assertEqual(db.list_tasks(conn)[0][0], other)
        # файлы и комментарии соседней задачи при этом остаются
        db.add_comment(conn, other, "свой")
        gone = db.add_task(conn, "удалить")
        db.add_comment(conn, gone, "чужой")
        db.delete_task(conn, gone)
        self.assertEqual(db.extras_counts(conn), {other: (0, 1)})

    def test_examples_have_files_and_comments(self):
        from examples import make_examples
        from PIL import Image
        conn = db.connect(self.dir / "a.db")
        db.add_examples(conn, make_examples())
        (task, (files, comments)), = db.extras_counts(conn).items()
        self.assertEqual((files, comments), (2, 2))
        picture = db.list_attachments(conn, task)[0]
        Image.open(__import__("io").BytesIO(db.attachment_data(conn, picture[0]))).verify()  # PNG читается
        db.delete_examples(conn)  # вместе с примерами уходят и их файлы с комментариями
        self.assertEqual(db.extras_counts(conn), {})


    def test_pending_tasks(self):
        conn = db.connect(self.dir / "p.db")
        now = datetime(2026, 10, 17, 12, 0)

        def task(title, due_hours, remind=None, by=None):
            tid = db.add_task(conn, title, created_by=by)
            due = (now + timedelta(hours=due_hours)).strftime("%Y-%m-%d %H:%M")
            conn.execute("UPDATE tasks SET due_at = ?, remind_before = ? WHERE id = ?", (due, remind, tid))
            return tid

        late = task("просрочена", -2)
        soon = task("напомнить пора", 1, remind=120, by="Анна")
        task("рано", 1, remind=30)
        done = task("выполнена", -1)
        db.set_done(conn, done, True)
        self.assertEqual([t[0] for t in db.pending_tasks(conn, now=now)], [late, soon])
        self.assertEqual([t[0] for t in db.pending_tasks(conn, "Анна", now=now)], [soon])


class TeamTests(TempDir):
    def test_shared_lists_members_and_backup(self):
        first = team.Team(self.dir)
        item = first.add_list("Команда", "Анна")
        second = team.Team(self.dir)  # второй участник видит список
        second.touch_member("Борис")
        self.assertEqual([i["name"] for i in second.lists()], ["Команда"])
        first.rename_list(item["id"], "Команда А")
        self.assertEqual(second.lists()[0]["name"], "Команда А")
        self.assertEqual(second.members(), ["Борис"])
        first.backup_daily()
        backups = list((self.dir / "ToDoro" / "backups").iterdir())
        self.assertEqual(len(backups), 1)
        first.delete_list(item)
        self.assertEqual(second.lists(), [])
        first.close(); second.close()

    def test_probe_notices_lost_and_restored_folder(self):
        team.Team(self.dir).close()
        probe = team.Probe(self.dir)
        probe.EVERY = 0.05
        try:
            self.assertTrue(self.wait_for(probe, True))
            moved = self.dir / "ToDoro"
            moved.rename(self.dir / "away")  # «пропала сеть»
            self.assertTrue(self.wait_for(probe, False))
            (self.dir / "away").rename(moved)  # «сеть вернулась»
            self.assertTrue(self.wait_for(probe, True))
            probe.started = team.time.monotonic() - probe.HANG - 1  # проверка «повисла»
            self.assertFalse(probe.online())
        finally:
            probe.stop()

    @staticmethod
    def wait_for(probe, online, seconds=5):
        deadline = team.time.monotonic() + seconds
        while team.time.monotonic() < deadline:
            if probe.online() == online:
                return True
            team.time.sleep(0.02)
        return False

    def test_shared_connection_batches_reads(self):
        class FakeRoot:  # вместо окна Tk: after_idle просто запоминает, что вызвать
            idle = []
            def after_idle(self, func):
                self.idle.append(func)

        path = self.dir / "list.db"
        mine = db.connect(path, timeout=1, shared=True)
        other = db.connect(path, timeout=1)
        mine.root = root = FakeRoot()
        task = db.add_task(mine, "Первая")
        self.assertFalse(mine.in_transaction)  # запись сохранена сразу
        root.idle.clear()
        db.list_tasks(mine)
        db.list_tasks(mine)
        self.assertTrue(mine.in_transaction)  # оба чтения — в одной транзакции
        self.assertEqual(len(root.idle), 1)
        db.set_task_status(mine, task, db.list_statuses(mine)[1][0])  # запись закрывает чтение
        self.assertFalse(mine.in_transaction)
        db.list_tasks(mine)
        for func in root.idle:  # окно освободилось
            func()
        self.assertFalse(mine.in_transaction)
        before = team.change_counter(path)
        db.add_task(other, "Вторая")  # другой участник может писать
        self.assertEqual(team.change_counter(path), before + 1)  # счётчик видит чужую запись
        self.assertEqual(len(db.list_tasks(mine)), 2)
        writes = mine.own_writes
        db.add_task(mine, "Третья")
        self.assertEqual(mine.own_writes, writes + 1)  # свои записи считаем
        self.assertEqual(team.change_counter(path), before + 2)
        mine.close()
        root.idle[-1]()  # отложенное закрытие транзакции после close не падает
        other.close()

    def test_unreachable_folder_gives_clear_error(self):
        blocker = self.dir / "file"
        blocker.write_text("not a folder")
        with self.assertRaises(team.TeamError):
            team.Team(blocker)


class UpdaterTests(unittest.TestCase):
    def test_versions(self):
        self.assertTrue(updater.is_newer("2.10", "2.9"))
        self.assertTrue(updater.is_newer("v2.1", "2.0"))
        self.assertFalse(updater.is_newer("2.0", "2.0"))
        self.assertFalse(updater.is_newer("", "1.0"))

    def test_update_only_from_github_with_checksum(self):
        good = {"asset_url": "https://github.com/machinist-soft/ToDoro/releases/download/v9/"
                             "ToDoro-Setup-9.exe", "sha256": "ab" * 32}
        updater.check_release(good)  # всё в порядке — без ошибки
        for wrong in ({"asset_url": good["asset_url"].replace("https", "http")},
                      {"asset_url": "https://github.com.evil.example/ToDoro-Setup-9.exe"},
                      {"asset_url": "file:///C:/ToDoro-Setup-9.exe"},
                      {"sha256": None}):
            with self.assertRaises(updater.UpdateError):
                updater.check_release({**good, **wrong})

    def test_feedback_url_has_version(self):
        url = updater.feedback_url("bug", "2.2")
        self.assertIn("template=bug_report.yml", url)
        self.assertIn("version=2.2", url)


class AppHelpersTests(TempDir):
    """Функции из todoro.py, которым не нужно окно."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def test_search_stems(self):
        stems = self.T.search_stems("Исполнитель отчёт")
        self.assertTrue(all(any(s in word for s in stems[:1]) for word in ("исполнителя", "исполнителю")))
        self.assertIn("отчё", stems[1])

    def test_remind_labels(self):
        self.assertEqual(self.T.remind_label(60), "За 1 час")
        self.assertEqual(self.T.remind_label(90), "За 1 ч 30 мин")
        self.assertEqual(self.T.remind_label(3 * 24 * 60), "За 3 дн")

    def test_risky_files(self):
        """Программу не спрятать точкой или пробелом в конце имени: Windows их убирает."""
        for name in ("отчёт.exe", "отчёт.EXE", "отчёт.exe.", "отчёт.exe . .", "диск.iso", "ссылка.url"):
            self.assertTrue(self.T.is_risky_file(name), name)
        for name in ("отчёт.pdf", "фото.png", "без расширения", "отчёт.pdf."):
            self.assertFalse(self.T.is_risky_file(name), name)
        self.assertEqual(self.T.file_name_for_disk("a:b.exe. "), "a_b.exe")
        self.assertEqual(self.T.file_name_for_disk(" . "), "файл")

    def test_csv_roundtrip(self):
        conn = db.connect(self.dir / "a.db")
        tid = db.add_task(conn, "Сдать отчёт", created_by="Анна")
        db.update_task(conn, tid, "Сдать отчёт", "2030-01-02 18:00", 60, True, True, "строка 1\nстрока 2")
        db.set_assignee(conn, tid, "Борис")
        path = self.dir / "x.csv"
        self.T.write_csv(path, self.T.CSV_COLUMNS, self.T.export_rows(conn))
        tasks, notes = self.T.prepare_import(conn, self.T.read_csv(path))
        self.assertEqual(notes, [])
        t = tasks[0]
        self.assertEqual((t["title"], t["body"], t["due_at"], t["remind_before"], t["urgent"],
                          t["important"], t["created_by"], t["assignee"]),
                         ("Сдать отчёт", "строка 1\nстрока 2", "2030-01-02 18:00", 60, 1, 1, "Анна", "Борис"))

    def test_csv_remind_limit(self):
        self.assertEqual(self.T.parse_csv_remind("525600"), 525600)  # год — можно
        with self.assertRaises(ValueError):
            self.T.parse_csv_remind("79991234567")  # например, номер телефона не в том столбце

    def test_csv_from_russian_excel(self):
        """Русский Excel сохраняет CSV в кодировке Windows-1251; даты — как 5.1.2027 7:05."""
        path = self.dir / "excel.csv"
        path.write_bytes("Задача;Срок;Напоминание\r\nПозвонить;5.1.2027 7:05;за 1 час\r\n".encode("cp1251"))
        conn = db.connect(self.dir / "a.db")
        tasks, notes = self.T.prepare_import(conn, self.T.read_csv(path))
        self.assertEqual((tasks[0]["title"], tasks[0]["due_at"], tasks[0]["remind_before"]),
                         ("Позвонить", "2027-01-05 07:05", 60))


class OutlookTests(TempDir):
    """Разбор письма Outlook (без самого Outlook) и поиск задачи по письму."""

    def test_subject_prefixes_removed(self):
        self.assertEqual(outlook.clean_subject("RE: Fw: Отв: Пересл: Отчёт за май"), "Отчёт за май")
        self.assertEqual(outlook.clean_subject("RE[2]: счёт"), "счёт")
        self.assertEqual(outlook.clean_subject("Ремонт: смета"), "Ремонт: смета")

    def test_quoted_history_cut(self):
        body = ("Сделайте, пожалуйста, до пятницы.\r\n\r\n\r\n\r\nСпасибо\r\n\r\n"
                "От: Иванов Иван\r\nОтправлено: 16 октября 2026 г. 10:00\r\nТема: отчёт\r\n\r\nстарое")
        self.assertEqual(outlook.clean_body(body), "Сделайте, пожалуйста, до пятницы.\n\nСпасибо")
        self.assertIn("старое", outlook.clean_body("От: Иванов\nОтправлено: вчера\n\nстарое"))

    def test_link_addresses_removed(self):
        self.assertEqual(outlook.clean_body("Смотрите сайт <https://example.com/?a=1> и [cid:image001.png@01]"),
                         "Смотрите сайт и")

    def test_find_task_by_mail(self):
        conn = db.connect(self.dir / "a.db")
        task_id = db.add_task(conn, "из письма")
        db.set_mail_id(conn, task_id, "<abc@mail>")
        self.assertEqual(db.find_by_mail(conn, "<abc@mail>"), task_id)
        self.assertIsNone(db.find_by_mail(conn, "<other@mail>"))
        self.assertIsNone(db.find_by_mail(conn, ""))
        db.add_task(conn, "обычная")
        self.assertEqual(db.mail_task_ids(conn), {task_id})

    def test_sender_kept_and_moved(self):
        conn, other = db.connect(self.dir / "a.db"), db.connect(self.dir / "b.db")
        task_id = db.add_task(conn, "из письма")
        db.set_mail_id(conn, task_id, "<abc@mail>", "Иван Петров <ivan@example.com>")
        self.assertEqual(db.mail_from(conn, task_id), "Иван Петров <ivan@example.com>")
        self.assertEqual(db.mail_from(conn, db.add_task(conn, "обычная")), "")
        moved = db.move_task_to(conn, task_id, other)
        self.assertEqual(db.mail_from(other, moved), "Иван Петров <ivan@example.com>")
        self.assertEqual(db.find_by_mail(other, "<abc@mail>"), moved)

    def test_draft_addressed_to_sender(self):
        import email
        import todoro
        todoro.DRAFTS_DIR = self.dir
        path = todoro.write_draft(7, "Задача", "текст", "Иван Петров <ivan@example.com>")
        message = email.message_from_bytes(Path(path).read_bytes(), policy=email.policy.default)
        self.assertEqual(message["To"].addresses[0].addr_spec, "ivan@example.com")
        self.assertEqual(message["To"].addresses[0].display_name, "Иван Петров")
        self.assertNotIn("To", email.message_from_bytes(
            Path(todoro.write_draft(8, "Задача", "текст")).read_bytes()))


if __name__ == "__main__":
    unittest.main()
