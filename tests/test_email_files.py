"""Письмо по задаче с её файлами (GitHub #16): write_draft с вложениями, db.read_attachments и
логика кнопки «Письмо» (TodoApp.email / ask_email_files / open_email).
Временные файлы; окна Tk не открываются; os.startfile, ui.* и in_background подменены;
данные пользователя не трогаются."""

import email
import email.policy
import sqlite3
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import todoro  # noqa: E402
from tests.test_core import TempDir  # noqa: E402
from tests.test_previews import file_state  # noqa: E402

T = todoro


def parse(path):
    return email.message_from_bytes(Path(path).read_bytes(), policy=email.policy.default)


def attachments_of(message):
    return [(part.get_filename(), part.get_content()) for part in message.iter_attachments()]


class DraftsDir(TempDir):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(T, "DRAFTS_DIR", self.dir / "drafts")
        patcher.start()
        self.addCleanup(patcher.stop)


# ---------- write_draft с файлами ----------

class WriteDraftFilesTests(DraftsDir):
    def test_files_attached_with_cyrillic_names(self):
        files = [("отчёт за май.pdf", b"%PDF-1.4\x00\xff"), ("фото.png", bytes(range(256)) * 10)]
        path = T.write_draft(5, "Задача 5", "строка 1\r\nстрока 2", "ivan@example.com", files)
        message = parse(path)
        self.assertEqual(message["X-Unsent"], "1")
        self.assertEqual(message["Subject"], "Задача 5")
        self.assertEqual(message["To"].addresses[0].addr_spec, "ivan@example.com")
        self.assertEqual(attachments_of(message), files)
        for part in message.iter_attachments():
            self.assertEqual(part.get_content_type(), "application/octet-stream")
        self.assertEqual(message.get_body(("plain",)).get_content().replace("\r\n", "\n"),
                         "строка 1\nстрока 2\n")

    def test_without_files_as_before(self):
        """Без файлов — простое письмо из одной части, как до изменения."""
        message = parse(T.write_draft(6, "Тема", "текст"))
        self.assertFalse(message.is_multipart())
        self.assertEqual(attachments_of(message), [])
        self.assertEqual(message.get_content().strip(), "текст")
        self.assertEqual(message["X-Unsent"], "1")

    def test_empty_and_same_named_files(self):
        files = [("пусто.txt", b""), ("a.txt", b"1"), ("a.txt", b"2")]
        self.assertEqual(attachments_of(parse(T.write_draft(7, "Т", "т", files=files))), files)

    def test_big_file(self):
        data = bytes(range(256)) * (8 * 1024)  # 2 МБ
        self.assertEqual(attachments_of(parse(T.write_draft(8, "Т", "т", files=[("big.bin", data)]))),
                         [("big.bin", data)])


# ---------- db.read_attachments ----------

class ReadAttachmentsTests(TempDir):
    def make_list(self):
        path = self.dir / "list.db"
        conn = db.connect(path)
        task = db.add_task(conn, "задача")
        ids = [db.add_attachment(conn, task, f"{n}.bin", data)
               for n, data in enumerate((b"one", b"\x00two", b"x" * 50000))]
        conn.close()
        return path, ids

    def test_order_and_missing(self):
        path, ids = self.make_list()
        self.assertEqual(db.read_attachments(path, [ids[2], ids[0], ids[1]]),
                         [b"x" * 50000, b"one", b"\x00two"])
        self.assertEqual(db.read_attachments(str(path), [ids[0], 9999, ids[1]], timeout=1),
                         [b"one", None, b"\x00two"])
        self.assertEqual(db.read_attachments(path, []), [])

    def test_no_list_file(self):
        path = self.dir / "нет" / "missing.db"
        self.assertIsNone(db.read_attachments(path, [1, 2]))
        self.assertFalse(path.parent.exists())

    def test_file_not_changed(self):
        """Чтение ничего не пишет: другие участники общего списка не перечитывают его."""
        path, ids = self.make_list()
        before = file_state(path)
        time.sleep(0.05)
        db.read_attachments(path, ids + [12345])
        self.assertEqual(file_state(path), before)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["list.db"])


# ---------- TodoApp.email / ask_email_files / open_email ----------

def sync_background(root, work, done):
    """in_background без потока: сразу work(), потом done(результат, ошибка)."""
    try:
        result = work()
    except Exception as error:  # noqa: BLE001
        done(None, error)
    else:
        done(result, None)


class EmailTests(DraftsDir):
    def setUp(self):
        super().setUp()
        self.path = self.dir / "list.db"
        self.conn = db.connect(self.path)
        self.task = db.add_task(self.conn, "Сдать отчёт")
        self.app = self.make_app()
        self.startfile = mock.MagicMock()
        self.show = mock.MagicMock(return_value=True)
        self.askyesno = mock.MagicMock(return_value=True)
        self.showinfo = mock.MagicMock()
        self.showwarning = mock.MagicMock()
        self.wait = mock.MagicMock()  # окно «Подождите…» — без настоящего окна Tk
        for patcher in (mock.patch.object(T.os, "startfile", self.startfile, create=True),
                        mock.patch.object(T.ui, "_show", self.show),
                        mock.patch.object(T.ui, "askyesno", self.askyesno),
                        mock.patch.object(T.ui, "showinfo", self.showinfo),
                        mock.patch.object(T.ui, "showwarning", self.showwarning),
                        mock.patch.object(T.ui, "showerror", mock.MagicMock()),
                        mock.patch.object(T, "in_background", sync_background),
                        mock.patch.object(T, "WaitDialog", self.wait)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.conn.close()
        db.forget_attachment_info()
        super().tearDown()

    def make_app(self):
        test = self

        class App:
            email = T.TodoApp.email
            ask_email_files = T.TodoApp.ask_email_files
            open_email = T.TodoApp.open_email
            root = None
            conn = self.conn

            def selected(self):
                return (test.task,)

            def task_info(self, task_id):
                return dict(title="Сдать отчёт", status_name="Новая", priority="Обычная", due="",
                            remind="", created="2026-11-11 10:00", urgent=0, important=0,
                            body="описание", author="", assignee="", unit="", repeat="")

            def preview_source(self):
                return test.source

            def copy_text(self, text):
                test.copied = text

        self.source = (self.path, 5)
        self.copied = None
        return App()

    def add(self, name, data):
        return db.add_attachment(self.conn, self.task, name, data)

    def opened_draft(self):
        """Сообщение из черновика, который открыли через os.startfile."""
        self.startfile.assert_called_once()
        path = self.startfile.call_args[0][0]
        self.assertTrue(str(path).endswith(".eml"), path)
        return parse(path)

    def test_no_files_no_question(self):
        self.app.email()
        self.show.assert_not_called()
        self.askyesno.assert_not_called()
        self.wait.assert_not_called()
        self.assertEqual(attachments_of(self.opened_draft()), [])

    def test_list_attachments_error_opens_without_files(self):
        self.add("a.txt", b"1")
        with mock.patch.object(T.db, "list_attachments", side_effect=sqlite3.OperationalError("locked")):
            self.app.email()
        self.show.assert_not_called()
        self.assertEqual(attachments_of(self.opened_draft()), [])

    def test_attach(self):
        files = [("отчёт.docx", b"PK\x03\x04data"), ("смета.xlsx", b"\x00" * 1000)]
        for name, data in files:
            self.add(name, data)
        self.show.return_value = True
        self.app.email()
        self.show.assert_called_once()
        self.askyesno.assert_not_called()
        self.wait.return_value.close.assert_called_once()
        self.assertEqual(attachments_of(self.opened_draft()), files)

    def test_without_files_button(self):
        self.add("a.txt", b"1")
        self.show.return_value = False
        self.app.email()
        self.assertEqual(attachments_of(self.opened_draft()), [])

    def test_escape_opens_nothing(self):
        self.add("a.txt", b"1")
        self.show.return_value = None
        self.app.email()
        self.startfile.assert_not_called()
        self.askyesno.assert_not_called()
        self.wait.assert_not_called()
        self.assertFalse((self.dir / "drafts").exists())

    def test_shared_offline_asks(self):
        self.add("a.txt", b"1")
        self.source = None
        self.askyesno.return_value = True
        self.app.email()
        self.assertIn("Нет связи", self.askyesno.call_args[0][1])
        self.assertEqual(attachments_of(self.opened_draft()), [])

    def test_shared_offline_declined(self):
        self.add("a.txt", b"1")
        self.source = None
        self.askyesno.return_value = False
        self.app.email()
        self.askyesno.assert_called_once()
        self.startfile.assert_not_called()

    def test_read_error_asks(self):
        self.add("a.txt", b"1")
        with mock.patch.object(T.db, "read_attachments",
                               side_effect=sqlite3.OperationalError("database is locked")):
            self.app.email()
        text = self.askyesno.call_args[0][1]
        self.assertIn("Не удалось прочитать файлы", text)
        self.assertIn("database is locked", text)
        self.wait.return_value.close.assert_called_once()  # окно ожидания закрыто и при ошибке
        self.assertEqual(attachments_of(self.opened_draft()), [])

    def test_read_error_declined(self):
        self.add("a.txt", b"1")
        self.askyesno.return_value = False
        with mock.patch.object(T.db, "read_attachments", side_effect=OSError("сеть")):
            self.app.email()
        self.startfile.assert_not_called()

    def test_file_deleted_meanwhile_asks(self):
        """Файл удалил другой участник, пока шёл вопрос: читается None — спрашиваем."""
        first = self.add("a.txt", b"1")
        self.add("b.txt", b"2")
        self.show.side_effect = lambda *a: db.delete_attachment(self.conn, first) or True
        self.app.email()
        self.assertIn("Не удалось прочитать файлы", self.askyesno.call_args[0][1])
        self.assertEqual(attachments_of(self.opened_draft()), [])

    def test_list_file_gone_asks(self):
        self.add("a.txt", b"1")
        self.source = (self.dir / "нет" / "list.db", 5)
        self.app.email()
        self.askyesno.assert_called_once()
        self.assertEqual(attachments_of(self.opened_draft()), [])

    def test_question_small(self):
        self.add("отчёт.pdf", b"x" * 2048)
        self.app.email()
        title, message, kind, buttons, default, cancel, _ = self.show.call_args[0]
        self.assertEqual(kind, "question")
        self.assertIn("1 шт., 2,0 КБ", message)
        self.assertIn("• отчёт.pdf", message)
        self.assertNotIn("Письмо может не уйти", message)
        self.assertEqual([b[:2] for b in buttons], [("Приложить", True), ("Без файлов", False)])
        self.assertEqual((default, cancel), (True, None))

    def test_question_big_warns(self):
        self.add("big1.bin", b"x" * (T.MAIL_FILES_WARN // 2))
        self.add("big2.bin", b"y" * (T.MAIL_FILES_WARN // 2 + 1))
        self.show.return_value = False
        self.app.email()
        _, message, kind, *_ = self.show.call_args[0]
        self.assertEqual(kind, "warning")
        self.assertIn("Письмо может не уйти", message)
        self.assertIn("20 МБ", message)

    def test_question_exactly_limit_no_warning(self):
        self.add("big.bin", b"x" * T.MAIL_FILES_WARN)
        self.show.return_value = False
        self.app.email()
        _, message, kind, *_ = self.show.call_args[0]
        self.assertEqual(kind, "question")
        self.assertNotIn("Письмо может не уйти", message)

    def test_question_many_files(self):
        for n in range(8):
            self.add(f"файл{n}.txt", b"1")
        self.show.return_value = False
        self.app.email()
        message = self.show.call_args[0][1]
        self.assertIn("8 шт.", message)
        for n in range(5):
            self.assertIn(f"• файл{n}.txt", message)
        self.assertNotIn("файл5.txt", message)
        self.assertIn("… и ещё 3", message)

    def test_mailto_fallback_hint_about_files(self):
        """.eml открыть нечем — открывается mailto:, и говорим, что файлы надо добавить вручную."""
        self.add("a.txt", b"1")
        self.startfile.side_effect = [OSError("нет программы для .eml"), None]
        self.app.email()
        self.assertEqual(self.startfile.call_count, 2)
        self.assertTrue(self.startfile.call_args[0][0].startswith("mailto:"))
        self.showinfo.assert_called_once()
        self.assertIn("добавьте их вручную", self.showinfo.call_args[0][1])

    def test_mailto_fallback_without_files_silent(self):
        self.startfile.side_effect = [OSError("нет программы для .eml"), None]
        self.app.email()
        self.assertTrue(self.startfile.call_args[0][0].startswith("mailto:"))
        self.showinfo.assert_not_called()

    def test_mailto_long_body_hint_about_files(self):
        """Длинный текст копируется в буфер — в том же сообщении подсказка про файлы."""
        self.add("a.txt", b"1")
        self.startfile.side_effect = [OSError("нет программы для .eml"), None]
        long_body = "очень длинное описание " * 200
        with mock.patch.object(T, "build_email", return_value=("Тема", long_body)):
            self.app.email()
        self.assertEqual(self.copied, long_body)
        self.showinfo.assert_called_once()
        text = self.showinfo.call_args[0][1]
        self.assertIn("Ctrl+V", text)
        self.assertIn("добавьте их вручную", text)

    def test_no_mail_program_at_all(self):
        self.add("a.txt", b"1")
        self.startfile.side_effect = OSError("ничего нет")
        self.app.email()
        self.showwarning.assert_called_once()
        self.assertIn("описание", self.copied)  # тема и текст — в буфере обмена


if __name__ == "__main__":
    unittest.main()
