"""Значки типа файла во вкладке «Файлы» карточки задачи: file_type_icon берёт значок из
Проводника Windows (через ctypes), а при любой беде возвращает None — тогда карточка покажет
плашку с расширением. Окна не открываются, файлы не создаются."""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import todoro  # noqa: E402

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

ON_WINDOWS = sys.platform == "win32"


@unittest.skipUnless(ON_WINDOWS, "значки Проводника есть только в Windows")
@unittest.skipUnless(HAVE_PIL, "нужен Pillow")
class FileTypeIconWindowsTests(unittest.TestCase):
    NAMES = [
        "доклад.pptx",
        "бюджет.xlsx",
        "договор.PDF",
        "README",                                  # без расширения
        'странный.a<b>:c|d?*',                     # запрещённые в Windows знаки
        "очень." + "x" * 300,                      # очень длинное расширение
        "а" * 5000 + ".docx",                      # очень длинное имя
        "",                                        # пустое имя
        None,                                      # имени нет вовсе
        "точка в конце.txt. ",                     # Windows молча обрезает точки и пробелы
    ]

    def check_icon(self, image):
        self.assertIsNotNone(image)
        self.assertEqual(image.mode, "RGBA")
        self.assertIn(image.size, [(48, 48), (32, 32)])
        alphas = set(image.getchannel("A").getdata())
        self.assertIn(0, alphas, "у значка нет прозрачного фона")
        self.assertTrue(any(a > 0 for a in alphas), "значок целиком прозрачный")

    def test_icons_for_various_names(self):
        for name in self.NAMES:
            with self.subTest(name=name if name is None or len(name) < 40 else name[:40] + "…"):
                self.check_icon(todoro.file_type_icon(name))

    def test_icon_has_opaque_pixels(self):
        """У настоящего значка есть совсем непрозрачная середина, а не только полупрозрачные края."""
        image = todoro.file_type_icon("отчёт.pdf")
        self.check_icon(image)
        self.assertIn(255, set(image.getchannel("A").getdata()))

    def test_repeated_calls_do_not_leak(self):
        """Много вызовов подряд (значки уничтожаются через DestroyIcon) — без сбоев."""
        for _ in range(50):
            self.check_icon(todoro.file_type_icon("a.xlsx"))

    def test_fallback_32_when_shell_gives_small_icon(self):
        """Если большой список значков недоступен — годится значок 32×32."""
        real = todoro._shell_icon_handle

        def small_only(ext):
            icon, size = real(ext)
            if size == 48:
                todoro.ctypes.WinDLL("user32").DestroyIcon(todoro.ctypes.c_void_p(icon))
            return real_small(ext)

        def real_small(ext):
            shell32 = todoro.ctypes.WinDLL("shell32")
            info = todoro._SHFileInfo()
            ok = shell32.SHGetFileInfoW("file" + ext, 0x80, todoro.ctypes.byref(info),
                                        todoro.ctypes.sizeof(info), 0x10 | 0x100)
            return (info.hIcon, 32) if ok and info.hIcon else (None, 0)

        with mock.patch.object(todoro, "_shell_icon_handle", side_effect=small_only):
            image = todoro.file_type_icon("x.pdf")
        self.check_icon(image)
        self.assertEqual(image.size, (32, 32))


class FileTypeIconFailureTests(unittest.TestCase):
    def test_exception_inside_gives_none(self):
        with mock.patch.object(todoro, "_shell_icon_handle", side_effect=OSError("сломалось")):
            self.assertIsNone(todoro.file_type_icon("a.pptx"))

    def test_no_icon_from_windows_gives_none(self):
        with mock.patch.object(todoro, "_shell_icon_handle", return_value=(None, 0)):
            self.assertIsNone(todoro.file_type_icon("a.pptx"))

    def test_drawing_failure_gives_none(self):
        """Не удалось нарисовать значок — None, а сам значок всё равно уничтожен."""
        destroyed = []
        fake_user32 = types.SimpleNamespace(DestroyIcon=lambda h: destroyed.append(h))
        real_windll = todoro.ctypes.WinDLL

        def windll(name, *args, **kwargs):
            return fake_user32 if name == "user32" else real_windll(name, *args, **kwargs)

        with mock.patch.object(todoro, "_shell_icon_handle", return_value=(12345, 48)), \
                mock.patch.object(todoro, "_draw_icon", return_value=None), \
                mock.patch.object(todoro.ctypes, "WinDLL", side_effect=windll):
            self.assertIsNone(todoro.file_type_icon("a.pptx"))
        self.assertEqual(len(destroyed), 1)

    def test_not_windows_gives_none(self):
        with mock.patch.object(todoro.sys, "platform", "linux"), \
                mock.patch.object(todoro, "_shell_icon_handle") as handle:
            self.assertIsNone(todoro.file_type_icon("a.pptx"))
        handle.assert_not_called()

    def test_no_pillow_gives_none(self):
        with mock.patch.dict(sys.modules, {"PIL": None}), \
                mock.patch.object(todoro, "_shell_icon_handle", return_value=(1, 48)) as handle:
            self.assertIsNone(todoro.file_type_icon("a.pptx"))
        handle.assert_not_called()

    def test_strange_extension_becomes_generic(self):
        """Слишком длинное расширение или с пробелом в Windows не уходит; запрещённые знаки
        заменяются на «_», как при сохранении файла."""
        seen = []

        def handle(ext):
            seen.append(ext)
            return None, 0

        with mock.patch.object(todoro, "_shell_icon_handle", side_effect=handle), \
                mock.patch.object(todoro.sys, "platform", "win32"):
            for name in ["a.pptx", "a.PDF", "README", "a.x" + "y" * 100, "a.b c", "a.<>", None]:
                todoro.file_type_icon(name)
        self.assertEqual(seen, [".pptx", ".pdf", ".file", ".file", ".file", ".__", ".file"])


class TypeIconCacheTests(unittest.TestCase):
    """TaskCard.type_icon спрашивает Проводник один раз на расширение."""

    def card(self):
        return types.SimpleNamespace(type_icons={})

    def test_one_call_per_extension(self):
        card = self.card()
        fake_photo = mock.MagicMock(side_effect=lambda img: ("photo", img))
        with mock.patch.object(todoro, "file_type_icon", side_effect=lambda n: "img:" + n) as icon, \
                mock.patch("PIL.ImageTk.PhotoImage", fake_photo):
            first = todoro.TaskCard.type_icon(card, "a.pptx")
            second = todoro.TaskCard.type_icon(card, "b.PPTX")
            third = todoro.TaskCard.type_icon(card, "c.xlsx")
        self.assertIs(first, second)
        self.assertIsNot(first, third)
        self.assertEqual(icon.call_count, 2)
        self.assertEqual(set(card.type_icons), {".pptx", ".xlsx"})

    def test_none_is_cached_too(self):
        card = self.card()
        with mock.patch.object(todoro, "file_type_icon", return_value=None) as icon:
            self.assertIsNone(todoro.TaskCard.type_icon(card, "a.zip"))
            self.assertIsNone(todoro.TaskCard.type_icon(card, "b.zip"))
        self.assertEqual(icon.call_count, 1)
        self.assertEqual(card.type_icons, {".zip": None})

    def test_photo_failure_gives_none(self):
        card = self.card()
        with mock.patch.object(todoro, "file_type_icon", return_value="img"), \
                mock.patch("PIL.ImageTk.PhotoImage", side_effect=RuntimeError("нет Tk")):
            self.assertIsNone(todoro.TaskCard.type_icon(card, "a.doc"))


if __name__ == "__main__":
    unittest.main()
