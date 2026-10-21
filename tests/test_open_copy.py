"""Открытие файла задачи (GitHub #8): копия во временной папке не перезаписывается, если она уже
та же, а занятая другой программой — не мешает (новая копия ложится в подпапку «2», «3»…).
Текст ошибок для окон (error_text): причина по-русски, путь без удвоенных «\\».
Только временные папки; os.startfile и ui.* подменены."""

import errno
import os
import sqlite3
import stat
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_core import TempDir  # noqa: E402


def lock(test, path):
    """Файл «занят»: только для чтения — запись в него даёт PermissionError, как у письма,
    открытого в Outlook. Снимается в tearDown (LockTempDir), иначе временную папку не удалить."""
    os.chmod(path, stat.S_IREAD)


class LockTempDir(TempDir):
    def tearDown(self):
        for path in self.dir.rglob("*"):  # снять «только чтение» до удаления папки
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        super().tearDown()


class TempCopyTests(LockTempDir):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def test_first_copy_goes_to_folder(self):
        path = self.T.temp_copy(self.dir / "3-42", "письмо.msg", b"data")
        self.assertEqual(path, self.dir / "3-42" / "письмо.msg")
        self.assertEqual(path.read_bytes(), b"data")

    def test_same_copy_is_reused_without_writing(self):
        """Повторное открытие того же файла — та же копия, без записи (Outlook держит её занятой)."""
        first = self.T.temp_copy(self.dir, "письмо.msg", b"data")
        lock(self, first)
        with mock.patch.object(Path, "write_bytes") as write:
            again = self.T.temp_copy(self.dir, "письмо.msg", b"data")
        self.assertEqual(again, first)
        write.assert_not_called()

    def test_reused_copy_gets_fresh_date(self):
        """Повторно открытую копию уборка временных файлов не должна счесть старой."""
        first = self.T.temp_copy(self.dir, "письмо.msg", b"data")
        os.utime(first, (1, 1))
        self.T.temp_copy(self.dir, "письмо.msg", b"data")
        self.assertGreater(first.stat().st_mtime, 1_000_000_000)

    def test_reopen_locked_copy_same_data_no_error(self):
        """Сама ошибка #8: копия занята, файл тот же — раньше «[Errno 13] Permission denied»."""
        first = self.T.temp_copy(self.dir, "письмо.msg", b"data")
        lock(self, first)
        self.assertEqual(self.T.temp_copy(self.dir, "письмо.msg", b"data"), first)

    def test_locked_copy_with_other_data_goes_to_subfolder_2(self):
        first = self.T.temp_copy(self.dir, "письмо.msg", b"old")
        lock(self, first)
        second = self.T.temp_copy(self.dir, "письмо.msg", b"new")
        self.assertEqual(second, self.dir / "2" / "письмо.msg")
        self.assertEqual(second.read_bytes(), b"new")
        self.assertEqual(first.read_bytes(), b"old")  # занятую копию не тронули

    def test_free_copy_with_other_data_is_overwritten_in_place(self):
        first = self.T.temp_copy(self.dir, "отчёт.txt", b"old")
        second = self.T.temp_copy(self.dir, "отчёт.txt", b"new")
        self.assertEqual(second, first)
        self.assertEqual(first.read_bytes(), b"new")
        self.assertFalse((self.dir / "2").exists())

    def test_copy_in_subfolder_reused(self):
        """Первая копия занята другим содержимым, во «2» уже лежит нужная — её и отдаём."""
        first = self.T.temp_copy(self.dir, "a.msg", b"old")
        lock(self, first)
        second = self.T.temp_copy(self.dir, "a.msg", b"new")
        lock(self, second)
        self.assertEqual(self.T.temp_copy(self.dir, "a.msg", b"new"), second)
        third = self.T.temp_copy(self.dir, "a.msg", b"newest")
        self.assertEqual(third, self.dir / "3" / "a.msg")

    def test_all_tries_busy_raises(self):
        for place in (self.dir, self.dir / "2", self.dir / "3"):
            place.mkdir(exist_ok=True)
            (place / "a.msg").write_bytes(b"old")
            lock(self, place / "a.msg")
        with self.assertRaises(PermissionError):
            self.T.temp_copy(self.dir, "a.msg", b"new", tries=3)
        self.assertFalse((self.dir / "4").exists())

    def test_one_try_raises_at_once(self):
        (self.dir / "a.msg").write_bytes(b"old")
        lock(self, self.dir / "a.msg")
        with self.assertRaises(PermissionError):
            self.T.temp_copy(self.dir, "a.msg", b"new", tries=1)
        self.assertFalse((self.dir / "2").exists())

    def test_bad_and_empty_names(self):
        path = self.T.temp_copy(self.dir, 'а/б:в?.txt', b"x")
        self.assertEqual(path.parent, self.dir)
        self.assertEqual(path.name, self.T.file_name_for_disk('а/б:в?.txt'))
        self.assertEqual(self.T.temp_copy(self.dir, "", b"x").name, "файл")
        self.assertEqual(self.T.temp_copy(self.dir, None, b"y").name, "файл")

    def test_empty_data(self):
        path = self.T.temp_copy(self.dir, "пусто.txt", b"")
        self.assertEqual(path.read_bytes(), b"")
        lock(self, path)
        self.assertEqual(self.T.temp_copy(self.dir, "пусто.txt", b""), path)

    def test_large_data(self):
        data = os.urandom(5 * 1024 * 1024)
        path = self.T.temp_copy(self.dir, "big.bin", data)
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(self.T.temp_copy(self.dir, "big.bin", data), path)

    def test_other_errors_not_swallowed(self):
        """Не «занято», а другая ошибка (например, на месте подпапки — файл) — сразу наружу."""
        (self.dir / "a.msg").write_bytes(b"old")
        lock(self, self.dir / "a.msg")
        (self.dir / "2").write_bytes(b"not a folder")
        with self.assertRaises(OSError):
            self.T.temp_copy(self.dir, "a.msg", b"new")


class OpenFileTests(LockTempDir):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def app(self, data):
        return SimpleNamespace(attachment_name=lambda i: "письмо.msg", file_data=lambda i: data,
                               list_id=3, root=None)

    def open(self, data):
        with mock.patch.object(self.T, "DRAFTS_DIR", self.dir), \
                mock.patch.object(self.T.os, "startfile", create=True) as startfile, \
                mock.patch.object(self.T.ui, "showerror") as showerror:
            self.T.TodoApp.open_file(self.app(data), 42)
        return startfile, showerror

    def test_reopen_busy_msg_opens_same_copy(self):
        """GitHub #8: письмо открыто в Outlook (копия занята) — второе открытие без ошибки."""
        startfile, _ = self.open(b"mail")
        path = self.dir / "3-42" / "письмо.msg"
        startfile.assert_called_once_with(path)
        lock(self, path)
        startfile, showerror = self.open(b"mail")
        startfile.assert_called_once_with(path)
        showerror.assert_not_called()

    def test_busy_copy_with_new_data_opens_from_subfolder(self):
        self.open(b"old")
        lock(self, self.dir / "3-42" / "письмо.msg")
        startfile, showerror = self.open(b"new")
        startfile.assert_called_once_with(self.dir / "3-42" / "2" / "письмо.msg")
        showerror.assert_not_called()

    def test_error_shown_in_russian_without_double_slashes(self):
        busy = PermissionError(errno.EACCES, "Permission denied", r"C:\Temp\ToDoro\3-42\письмо.msg")
        with mock.patch.object(self.T, "DRAFTS_DIR", self.dir), \
                mock.patch.object(self.T, "temp_copy", side_effect=busy), \
                mock.patch.object(self.T.os, "startfile", create=True) as startfile, \
                mock.patch.object(self.T.ui, "showerror") as showerror:
            self.T.TodoApp.open_file(self.app(b"x"), 42)
        startfile.assert_not_called()
        text = showerror.call_args[0][1]
        self.assertIn("нет доступа", text.lower())
        self.assertIn(r"C:\Temp\ToDoro\3-42\письмо.msg", text)
        self.assertNotIn("\\\\", text)
        self.assertNotIn("Errno", text)


class ErrorTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def test_permission_denied_in_russian_with_path(self):
        error = PermissionError(errno.EACCES, "Permission denied", r"C:\Users\a\b.msg")
        lines = self.T.error_text(error).split("\n")
        self.assertEqual(lines[1], r"C:\Users\a\b.msg")
        self.assertTrue(lines[0].startswith("Нет доступа"))
        self.assertNotIn("\\\\", self.T.error_text(error))

    def test_every_known_reason_capitalized(self):
        for number, reason in self.T.ERROR_REASONS.items():
            text = self.T.error_text(OSError(number, "english"))
            self.assertEqual(text, reason[:1].upper() + reason[1:])

    def test_unknown_errno_keeps_system_text(self):
        self.assertEqual(self.T.error_text(OSError(9999, "something odd", "f.txt")),
                         "Something odd\nf.txt")

    def test_two_paths(self):
        error = FileExistsError(errno.EEXIST, "File exists", r"D:\a.txt", None, r"D:\b.txt")
        self.assertEqual(self.T.error_text(error), "Такой файл уже есть\nD:\\a.txt\nD:\\b.txt")

    def test_real_missing_file(self):
        missing = Path(r"C:\нет-такой-папки-todoro\файл.txt")
        try:
            missing.read_bytes()
        except OSError as error:
            text = self.T.error_text(error)
        self.assertEqual(text, "Файл или папка не найдены\n" + str(missing))

    def test_oserror_without_errno(self):
        self.assertEqual(self.T.error_text(OSError("просто текст")), "просто текст")
        self.assertEqual(self.T.error_text(OSError()), "")

    def test_not_oserror(self):
        self.assertEqual(self.T.error_text(ValueError("плохо")), "плохо")
        self.assertEqual(self.T.error_text(sqlite3.OperationalError("database is locked")),
                         "database is locked")

    def test_empty_filename_skipped(self):
        self.assertEqual(self.T.error_text(OSError(errno.ENOSPC, "No space", "")),
                         "На диске закончилось место")

    def test_windows_error(self):
        """Ошибка Windows «файл занят другим процессом» (winerror 32) — текст Windows и путь, без «Errno»."""
        error = OSError(None, "The process cannot access the file", r"C:\a.msg", 32)
        text = self.T.error_text(error)
        self.assertEqual(text.split("\n")[-1], r"C:\a.msg")
        self.assertNotIn("Errno", text)

    def test_windows_error_keeps_windows_text(self):
        """Ошибки Windows без своего errno (Python даёт им EINVAL) — текстом Windows,
        а не «Недопустимое имя файла»."""
        for code in (59, 64, 1155, 1223):
            error = OSError(None, "Сетевое имя более недоступно", r"\\srv\share\a.csv", code)
            self.assertEqual(error.errno, errno.EINVAL)
            text = self.T.error_text(error)
            self.assertNotIn("Недопустимое имя", text)
            self.assertEqual(text, "Сетевое имя более недоступно\n" + r"\\srv\share\a.csv")


if __name__ == "__main__":
    unittest.main()
