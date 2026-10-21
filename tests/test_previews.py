"""Превью картинок во вкладке «Файлы» карточки задачи: картинка читается и уменьшается в фоновом
потоке (db.read_attachment, todoro.small_picture), окно только ставит готовое превью на место
значка. Плюс проверка версии Pillow перед сборкой установщика (tools/build_installer.check_pillow).

Окна Tk не открываются: методы TaskCard вызываются на заглушке, «окно» для in_background —
заглушка с очередью after. Все файлы — во временной папке.
"""
import io
import os
import sqlite3
import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import db  # noqa: E402
import team  # noqa: E402
import todoro  # noqa: E402
from tests.test_core import TempDir  # noqa: E402

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def png_bytes(width=200, height=100, color=(200, 30, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, "PNG")
    return buffer.getvalue()


def file_state(path):
    stat = os.stat(path)
    return stat.st_size, stat.st_mtime_ns, Path(path).read_bytes()


class ReadAttachmentTests(TempDir):
    def make_list(self, name="list.db", data=b"hello"):
        path = self.dir / name
        conn = db.connect(path)
        task = db.add_task(conn, "задача")
        attachment = db.add_attachment(conn, task, "a.bin", data)
        conn.close()
        return path, attachment

    def test_reads_data(self):
        path, attachment = self.make_list(data=b"\x00\x01content")
        self.assertEqual(db.read_attachment(path, attachment), b"\x00\x01content")
        self.assertEqual(db.read_attachment(str(path), attachment, timeout=1), b"\x00\x01content")

    def test_missing_file_gives_none_and_is_not_created(self):
        path = self.dir / "нет" / "missing.db"
        self.assertIsNone(db.read_attachment(path, 1))
        self.assertFalse(path.exists())
        self.assertFalse(path.parent.exists())
        flat = self.dir / "missing.db"
        self.assertIsNone(db.read_attachment(flat, 1))
        self.assertFalse(flat.exists())

    def test_unknown_id_gives_none(self):
        path, attachment = self.make_list()
        self.assertIsNone(db.read_attachment(path, attachment + 100))
        self.assertIsNone(db.read_attachment(path, -1))

    def test_file_not_changed(self):
        """Чтение превью ничего не пишет: другие участники общего списка не перечитывают его."""
        path, attachment = self.make_list(data=b"x" * 50000)
        before = file_state(path)
        time.sleep(0.05)
        db.read_attachment(path, attachment)
        db.read_attachment(path, attachment + 1)
        self.assertEqual(file_state(path), before)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["list.db"])

    def test_big_attachment(self):
        data = os.urandom(3 * 1024 * 1024)
        path, attachment = self.make_list(data=data)
        self.assertEqual(db.read_attachment(path, attachment), data)


@unittest.skipUnless(HAVE_PIL, "нужен Pillow")
class SmallPictureTests(unittest.TestCase):
    def test_shrinks_to_56(self):
        image = todoro.small_picture(png_bytes(400, 100))
        self.assertIsNotNone(image)
        self.assertLessEqual(max(image.size), 56)
        self.assertEqual(image.size, (56, 14))

    def test_tall_and_custom_size(self):
        image = todoro.small_picture(png_bytes(30, 300), size=20)
        self.assertLessEqual(max(image.size), 20)

    def test_small_not_enlarged(self):
        self.assertEqual(todoro.small_picture(png_bytes(10, 8)).size, (10, 8))

    def test_garbage_gives_none(self):
        for data in (None, b"", b"not a picture", png_bytes()[:40], b"\x89PNG\r\n\x1a\n" + b"\0" * 10):
            with self.subTest(data=data[:12] if data else data):
                self.assertIsNone(todoro.small_picture(data))

    def test_huge_picture_gives_none(self):
        """Картинка-«бомба» (слишком много пикселей) — без превью, а не падение."""
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 100):
            self.assertIsNone(todoro.small_picture(png_bytes(200, 200)))


class PreviewSourceTests(unittest.TestCase):
    def app(self, item, online=False):
        app = types.SimpleNamespace()
        app.current_list = lambda: item
        app.share_online = lambda: online
        app.team = types.SimpleNamespace(path=lambda i: Path("Z:/общая/lists") / i["file"])
        return app

    def source(self, app):
        return todoro.TodoApp.preview_source(app)

    def test_personal_main(self):
        tmp = Path("C:/tmp-fake/todoro.db")
        with mock.patch.object(db, "DB_PATH", tmp):
            app = self.app({"id": None, "file": None, "shared": False})
            self.assertEqual(self.source(app), (tmp, 5))

    def test_personal_other(self):
        lists = Path("C:/tmp-fake/lists")
        with mock.patch.object(db, "LISTS_DIR", lists):
            app = self.app({"id": "x", "file": "abc.db", "shared": False})
            self.assertEqual(self.source(app), (lists / "abc.db", 5))

    def test_personal_ignores_online(self):
        app = self.app({"id": "x", "file": "abc.db", "shared": False}, online=False)
        app.share_online = mock.Mock(return_value=False)
        self.assertIsNotNone(self.source(app))

    def test_shared_online(self):
        app = self.app({"id": "t1", "file": "t1.db", "shared": True}, online=True)
        self.assertEqual(self.source(app), (Path("Z:/общая/lists/t1.db"), team.TIMEOUT))

    def test_shared_offline(self):
        app = self.app({"id": "t1", "file": "t1.db", "shared": True}, online=False)
        app.team = mock.Mock()
        self.assertIsNone(self.source(app))
        app.team.path.assert_not_called()


class FakeRoot:
    """Вместо окна Tk для in_background: after складывает вызовы в очередь, pump их выполняет."""

    def __init__(self):
        self.queue = []

    def after(self, ms, func):
        self.queue.append(func)

    def pump(self, limit=5.0):
        end = time.time() + limit
        while self.queue and time.time() < end:
            self.queue.pop(0)()
            time.sleep(0.01)
        return not self.queue


class FakeLabel:
    def __init__(self):
        self.exists = True
        self.config = {}

    def winfo_exists(self):
        return self.exists

    def configure(self, **kw):
        self.config.update(kw)


@unittest.skipUnless(HAVE_PIL, "нужен Pillow")
class TaskCardThumbnailTests(TempDir):
    def setUp(self):
        super().setUp()
        self.root = FakeRoot()
        self.photo = mock.patch("PIL.ImageTk.PhotoImage",
                                side_effect=lambda image, master=None: ("photo", image.size))
        self.photo.start()
        self.addCleanup(self.photo.stop)

    def card(self):
        card = types.SimpleNamespace(thumbs={}, file_previews={}, alive=True)
        card._root = lambda: self.root
        card.winfo_exists = lambda: card.alive
        card.thumbnail = todoro.TaskCard.thumbnail.__get__(card)
        card.thumbnail_ready = todoro.TaskCard.thumbnail_ready.__get__(card)
        return card

    def make_list(self, name, picture):
        path = self.dir / name
        conn = db.connect(path)
        task = db.add_task(conn, "задача")
        attachment = db.add_attachment(conn, task, "pic.png", picture)
        conn.close()
        return path, attachment

    def show(self, card, attachment, name, source):
        """Как draw_files: превью (или None — значок), метка запоминается для фонового чтения."""
        thumb = card.thumbnail(attachment, name, source)
        label = FakeLabel()
        if source is not None:
            card.file_previews[(source[0], attachment)] = label
        return thumb, label

    def test_icon_first_then_picture(self):
        path, attachment = self.make_list("a.db", png_bytes(300, 150))
        card = self.card()
        thumb, label = self.show(card, attachment, "pic.png", (path, 5))
        self.assertIsNone(thumb)  # пока — значок типа файла
        self.assertEqual(label.config, {})
        self.assertTrue(self.root.pump())
        self.assertEqual(label.config["image"], ("photo", (56, 28)))
        self.assertEqual(card.thumbs[(path, attachment)], ("photo", (56, 28)))
        # следующая отрисовка берёт готовое превью сразу
        self.assertEqual(card.thumbnail(attachment, "pic.png", (path, 5)), ("photo", (56, 28)))

    def test_no_second_read(self):
        path, attachment = self.make_list("a.db", png_bytes())
        card = self.card()
        with mock.patch.object(db, "read_attachment", wraps=db.read_attachment) as read:
            self.show(card, attachment, "pic.png", (path, 5))
            self.show(card, attachment, "pic.png", (path, 5))  # повтор, пока фон ещё читает
            self.root.pump()
            self.show(card, attachment, "pic.png", (path, 5))  # и после
            self.root.pump()
        self.assertEqual(read.call_count, 1)

    def test_broken_picture_read_once_and_stays_icon(self):
        path, attachment = self.make_list("a.db", b"not a picture")
        card = self.card()
        with mock.patch.object(db, "read_attachment", wraps=db.read_attachment) as read:
            _, label = self.show(card, attachment, "pic.png", (path, 5))
            self.root.pump()
            self.assertIsNone(self.show(card, attachment, "pic.png", (path, 5))[0])
            self.root.pump()
        self.assertEqual(read.call_count, 1)
        self.assertEqual(label.config, {})

    def test_read_error_retried_on_next_draw(self):
        """Чтение сорвалось (файл занят, оборвалась связь) — при следующей отрисовке пробуем снова."""
        path, attachment = self.make_list("a.db", b"not a picture")
        card = self.card()
        with mock.patch.object(db, "read_attachment", side_effect=sqlite3.OperationalError("locked")) as read:
            self.show(card, attachment, "pic.png", (path, 5))
            self.root.pump()
            self.assertNotIn((path, attachment), card.thumbs)
            self.show(card, attachment, "pic.png", (path, 5))
            self.root.pump()
        self.assertEqual(read.call_count, 2)

    def test_no_source_no_read(self):
        card = self.card()
        with mock.patch.object(todoro, "in_background") as background, \
                mock.patch.object(db, "read_attachment") as read:
            self.assertIsNone(card.thumbnail(1, "pic.png", None))
        background.assert_not_called()
        read.assert_not_called()
        self.assertEqual(card.thumbs, {})  # при появлении связи попробуем снова

    def test_not_image_no_read(self):
        card = self.card()
        with mock.patch.object(todoro, "in_background") as background:
            self.assertIsNone(card.thumbnail(1, "отчёт.docx", (self.dir / "a.db", 5)))
            self.assertIsNone(card.thumbnail(2, "без_расширения", (self.dir / "a.db", 5)))
        background.assert_not_called()

    def test_uppercase_extension(self):
        path, attachment = self.make_list("a.db", png_bytes())
        card = self.card()
        _, label = self.show(card, attachment, "PIC.PNG", (path, 5))
        self.root.pump()
        self.assertIn("image", label.config)

    def test_same_id_different_lists(self):
        """id вложений в разных файлах списков совпадают — превью не путаются."""
        red_path, red_id = self.make_list("red.db", png_bytes(100, 100))
        blue_path, blue_id = self.make_list("blue.db", png_bytes(100, 50))
        self.assertEqual(red_id, blue_id)
        card = self.card()
        _, red_label = self.show(card, red_id, "pic.png", (red_path, 5))
        self.root.pump()
        # карточку переоткрыли в другом списке: тот же id, но другой файл — читаем заново
        thumb, blue_label = self.show(card, blue_id, "pic.png", (blue_path, 5))
        self.assertIsNone(thumb)
        self.root.pump()
        self.assertEqual(red_label.config["image"], ("photo", (56, 56)))
        self.assertEqual(blue_label.config["image"], ("photo", (56, 28)))
        self.assertEqual(card.thumbs[(red_path, red_id)], ("photo", (56, 56)))
        self.assertEqual(card.thumbs[(blue_path, blue_id)], ("photo", (56, 28)))

    def test_ready_after_card_destroyed(self):
        path, attachment = self.make_list("a.db", png_bytes())
        card = self.card()
        _, label = self.show(card, attachment, "pic.png", (path, 5))
        card.alive = False
        label.exists = False
        self.root.pump()  # не падает
        self.assertEqual(label.config, {})

    def test_ready_after_label_redrawn(self):
        """Метка уже уничтожена (список файлов перерисован), а карточка жива — без ошибок."""
        path, attachment = self.make_list("a.db", png_bytes())
        card = self.card()
        _, label = self.show(card, attachment, "pic.png", (path, 5))
        label.exists = False
        self.root.pump()
        self.assertEqual(label.config, {})
        self.assertIsNotNone(card.thumbs[(path, attachment)])

    def test_ready_without_label(self):
        card = self.card()
        card.thumbnail_ready(("x.db", 1), Image.new("RGB", (5, 5)))
        self.assertEqual(card.thumbs[("x.db", 1)], ("photo", (5, 5)))

    def test_ready_with_none_image(self):
        card = self.card()
        card.thumbs[("x.db", 1)] = None
        card.thumbnail_ready(("x.db", 1), None)
        self.assertIsNone(card.thumbs[("x.db", 1)])

    def test_photo_failure_keeps_icon(self):
        card = self.card()
        label = FakeLabel()
        card.file_previews[("x.db", 1)] = label
        with mock.patch("PIL.ImageTk.PhotoImage", side_effect=RuntimeError("нет Tk")):
            card.thumbnail_ready(("x.db", 1), Image.new("RGB", (5, 5)))
        self.assertEqual(label.config, {})

    def test_missing_list_file(self):
        """Файл списка пропал — превью нет, файл не создаётся."""
        path = self.dir / "gone.db"
        card = self.card()
        _, label = self.show(card, 1, "pic.png", (path, 5))
        self.root.pump()
        self.assertEqual(label.config, {})
        self.assertFalse(path.exists())

    def test_list_file_unchanged(self):
        path, attachment = self.make_list("a.db", png_bytes())
        before = file_state(path)
        card = self.card()
        self.show(card, attachment, "pic.png", (path, 5))
        self.root.pump()
        self.assertEqual(file_state(path), before)


class CheckPillowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_installer
        cls.B = build_installer

    def check(self, version):
        fake = types.SimpleNamespace(__version__=version)
        with mock.patch.dict(sys.modules, {"PIL": fake}):
            self.B.check_pillow()

    def test_old_versions_stop(self):
        for version in ("12.9.9", "9.5.0", "12.0", "1.0", "12.99.0.dev0"):
            with self.subTest(version=version), self.assertRaises(SystemExit) as stop:
                self.check(version)
            self.assertIn("устарел", str(stop.exception.code))

    def test_new_versions_pass(self):
        for version in ("13.0.0", "13.0", "13.1.2", "14.0.0.dev0", "20.0"):
            with self.subTest(version=version):
                self.check(version)

    def test_not_installed(self):
        with mock.patch.dict(sys.modules, {"PIL": None}), self.assertRaises(SystemExit) as stop:
            self.B.check_pillow()
        self.assertIn("Не установлен Pillow", str(stop.exception.code))

    def test_main_checks_first(self):
        """main() останавливается на проверке Pillow, ничего не собирая."""
        with mock.patch.object(self.B, "check_pillow", side_effect=SystemExit("стоп")), \
                mock.patch.object(self.B, "app_version") as version, \
                mock.patch.object(self.B.subprocess, "run") as run, \
                mock.patch.object(self.B.subprocess, "check_call", create=True) as call:
            with self.assertRaises(SystemExit):
                self.B.main()
        version.assert_not_called()
        run.assert_not_called()
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
