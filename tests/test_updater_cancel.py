"""Обновление в медленной или «фильтрованной» сети (issue #2): проверка сертификата без строгого
режима Python 3.13+, ожидание ответа GitHub, «Отмена» скачивания (updater.Cancelled, параметр
cancelled у _fetch и download), окно UpdateDialog во время скачивания и окошко «Проверяю…».

Сеть не используется: updater._urlopen (или urllib.request.urlopen) подменяется; файлы — только
во временной папке. Окна Tk не открываются: методы окон вызываются на подставных объектах.
Запуск из папки проекта:  python -m unittest discover tests
"""
import io
import shutil
import ssl
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import updater  # noqa: E402
from test_updater_zip import (ARCHIVE, EXE_NAME, EXE_URL, FILTER_PAGE, INSTALLER, ZIP_NAME,  # noqa: E402
                              ZIP_URL, release, response, sha)


class TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-test-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class Flag:
    """cancelled() для тестов: «Отмена» нажимается после заданного числа проверок."""

    def __init__(self, after=None):
        self.after = after  # None — никогда не отменять
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.after is not None and self.calls > self.after


class SslContextTests(unittest.TestCase):
    def test_strict_flag_removed_but_certificate_still_checked(self):
        """Строгий режим снят, но сертификат и имя сервера проверяются как обычно."""
        context = updater._ssl_context()
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
        self.assertFalse(context.verify_flags & strict, "строгий режим должен быть снят")
        default = ssl.create_default_context().verify_flags
        self.assertEqual(context.verify_flags, default & ~strict,
                         "прочие флаги проверки — как в обычном контексте")

    def test_new_context_each_time(self):
        self.assertIsNot(updater._ssl_context(), updater._ssl_context())

    def test_urlopen_passes_context_and_timeout(self):
        with mock.patch.object(updater.urllib.request, "urlopen", return_value="ok") as urlopen:
            self.assertEqual(updater._urlopen(EXE_URL, {"User-Agent": "x"}, 7), "ok")
        kwargs = urlopen.call_args.kwargs
        self.assertEqual(kwargs["timeout"], 7)
        self.assertIsInstance(kwargs["context"], ssl.SSLContext)
        self.assertEqual(kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(kwargs["context"].check_hostname)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, EXE_URL)

    def test_urlopen_falls_back_to_windows_on_ssl_error(self):
        """Сертификат отвергнут напрямую — на Windows пробуем сетевую часть Windows, как раньше."""
        error = ssl.SSLCertVerificationError("certificate verify failed")
        with mock.patch.object(updater.urllib.request, "urlopen", side_effect=error), \
                mock.patch.object(updater.sys, "platform", "win32"), \
                mock.patch.object(updater, "_WinInetResponse", return_value="wininet") as wininet:
            self.assertEqual(updater._urlopen(EXE_URL, {}, 5), "wininet")
        wininet.assert_called_once_with(EXE_URL, {}, 5)

    def test_urlopen_both_fail_reports_both(self):
        with mock.patch.object(updater.urllib.request, "urlopen",
                               side_effect=ssl.SSLCertVerificationError("прямо-сбой")), \
                mock.patch.object(updater.sys, "platform", "win32"), \
                mock.patch.object(updater, "_WinInetResponse", side_effect=OSError("win-сбой")):
            with self.assertRaises(OSError) as caught:
                updater._urlopen(EXE_URL, {}, 5)
        self.assertIn("прямо-сбой", str(caught.exception))
        self.assertIn("win-сбой", str(caught.exception))


class FetchLatestTimeoutTests(unittest.TestCase):
    def test_default_timeout_is_20(self):
        with mock.patch.object(updater, "_urlopen",
                               return_value=response(b'{"tag_name": "v9.9", "assets": []}')) as opener:
            self.assertEqual(updater.fetch_latest()["version"], "9.9")
        self.assertEqual(opener.call_args.args[2], 20)

    def test_timeout_is_update_error(self):
        with mock.patch.object(updater, "_urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(updater.UpdateError) as caught:
                updater.fetch_latest()
        self.assertIn("timed out", str(caught.exception))


class SlowResponse(io.BytesIO):
    """Отдаёт файл маленькими порциями, перед каждой — on_read(номер порции)."""

    def __init__(self, data, on_read=None, chunk=10000):
        super().__init__(data)
        self.chunk = chunk
        self.headers = {"Content-Length": str(len(data))}
        self.on_read = on_read
        self.reads = 0

    def read(self, size=-1):
        self.reads += 1
        if self.on_read:
            self.on_read(self.reads)
        return super().read(self.chunk)


class FetchCancelTests(TempDir):
    def fetch(self, reply, cancelled, on_progress=None, magic=b"MZ"):
        path = self.dir / EXE_NAME
        with mock.patch.object(updater, "_urlopen", return_value=reply) as opener:
            try:
                updater._fetch(EXE_URL, path, len(INSTALLER), sha(INSTALLER), magic,
                               on_progress, 5, cancelled)
            finally:
                self.opener = opener
        return path

    def test_cancelled_is_not_update_error(self):
        """Отмена — не ошибка обновления: окно не должно её показывать и пробовать .zip."""
        self.assertFalse(issubclass(updater.Cancelled, updater.UpdateError))
        self.assertTrue(issubclass(updater.Cancelled, Exception))

    def test_cancelled_before_start_does_not_connect(self):
        with self.assertRaises(updater.Cancelled):
            self.fetch(response(INSTALLER), lambda: True)
        self.opener.assert_not_called()
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_cancel_midway_removes_partial_file(self):
        progress = []
        with self.assertRaises(updater.Cancelled):
            self.fetch(SlowResponse(INSTALLER), Flag(after=3),
                       on_progress=lambda *a: progress.append(a))
        chunks = [p for p in progress if p[0] > 0]
        self.assertEqual(len(chunks), 2, "после «Отмены» порции больше не принимаются")
        self.assertEqual(chunks[-1][0], 20000)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_zero_progress_before_and_after_connect(self):
        """В начале попытки (до соединения) и сразу после него — on_progress(0, …): окно
        сбрасывает отсчёт «давно нет данных», пока ждём ответа сервера."""
        events = []
        reply = SlowResponse(INSTALLER)

        def opener(*args):
            events.append("connect")
            return reply

        # размер в выпуске (12345) нарочно другой — видно, откуда взят total; в конце — «не полностью»
        with mock.patch.object(updater, "_urlopen", side_effect=opener),                 self.assertRaises(updater.UpdateError):
            updater._fetch(EXE_URL, self.dir / EXE_NAME, 12345, sha(INSTALLER), b"MZ",
                           lambda done, total: events.append((done, total)), 5)
        self.assertEqual(events[:3], [(0, 12345), "connect", (0, len(INSTALLER))],
                         "до соединения — размер из выпуска, после — из Content-Length")
        self.assertEqual(events[3], (10000, len(INSTALLER)))
        self.assertEqual(events[-1], (len(INSTALLER), len(INSTALLER)))

    def test_zero_progress_without_size(self):
        events = []
        reply = response(INSTALLER)
        reply.headers = {}
        with mock.patch.object(updater, "_urlopen", return_value=reply):
            updater._fetch(EXE_URL, self.dir / EXE_NAME, None, sha(INSTALLER), b"MZ",
                           lambda *a: events.append(a), 5)
        self.assertEqual(events[:2], [(0, 0), (0, 0)])

    def test_zero_progress_even_if_connect_fails(self):
        events = []
        with mock.patch.object(updater, "_urlopen", side_effect=OSError("нет сети")):
            with self.assertRaises(updater.DownloadError):
                updater._fetch(EXE_URL, self.dir / EXE_NAME, 7, sha(INSTALLER), b"MZ",
                               lambda *a: events.append(a), 5)
        self.assertEqual(events, [(0, 7)])

    def test_no_progress_if_cancelled_before_start(self):
        events = []
        with mock.patch.object(updater, "_urlopen") as opener:
            with self.assertRaises(updater.Cancelled):
                updater._fetch(EXE_URL, self.dir / EXE_NAME, 7, sha(INSTALLER), b"MZ",
                               lambda *a: events.append(a), 5, lambda: True)
        opener.assert_not_called()
        self.assertEqual(events, [])

    def test_not_cancelled_downloads_normally(self):
        flag = Flag()
        path = self.fetch(SlowResponse(INSTALLER), flag)
        self.assertEqual(path.read_bytes(), INSTALLER)
        self.assertGreater(flag.calls, 2, "cancelled() спрашивается перед каждой порцией")

    def test_none_cancelled_works_as_before(self):
        path = self.fetch(SlowResponse(INSTALLER), None)
        self.assertEqual(path.read_bytes(), INSTALLER)

    def test_network_error_after_cancel_is_cancelled(self):
        """Соединение оборвалось уже после «Отмены» — это отмена, а не «нет интернета»."""
        state = {"cancelled": False}

        def on_read(n):
            if n == 2:
                state["cancelled"] = True
                raise ConnectionResetError("оборвалось")

        with self.assertRaises(updater.Cancelled) as caught:
            self.fetch(SlowResponse(INSTALLER, on_read), lambda: state["cancelled"])
        self.assertIsInstance(caught.exception.__cause__, ConnectionResetError)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_network_error_without_cancel_is_download_error(self):
        def on_read(n):
            if n == 2:
                raise ConnectionResetError("оборвалось")

        with self.assertRaises(updater.DownloadError):
            self.fetch(SlowResponse(INSTALLER, on_read), Flag())
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_connect_error_after_cancel_is_cancelled(self):
        """«Отмена» нажата, пока ждали соединения, и оно не удалось — тоже Cancelled."""
        state = {"cancelled": False}

        def fail(*args):
            state["cancelled"] = True
            raise TimeoutError("timed out")

        with mock.patch.object(updater, "_urlopen", side_effect=fail):
            with self.assertRaises(updater.Cancelled):
                updater._fetch(EXE_URL, self.dir / EXE_NAME, None, sha(INSTALLER), b"MZ", None, 5,
                               lambda: state["cancelled"])

    def test_filter_page_still_blocked_error(self):
        with self.assertRaises(updater.BlockedError):
            self.fetch(response(FILTER_PAGE), Flag())
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_locked_partial_file_does_not_hide_cancel(self):
        """Недокачанный файл занят (его держит другая попытка) — всё равно Cancelled, не PermissionError."""
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("занят")):
            with self.assertRaises(updater.Cancelled):
                self.fetch(SlowResponse(INSTALLER), Flag(after=2))

    def test_locked_partial_file_does_not_hide_network_error(self):
        def on_read(n):
            raise ConnectionResetError("оборвалось")

        with mock.patch.object(Path, "unlink", side_effect=PermissionError("занят")):
            with self.assertRaises(updater.DownloadError):
                self.fetch(SlowResponse(INSTALLER, on_read), None)


class BlockingResponse(io.BytesIO):
    """Первая порция — сразу, вторая — только когда тест «отпустит» (поток ждёт сеть)."""

    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
        self.first_read = threading.Event()
        self.release = threading.Event()

    def read(self, size=-1):
        if self.tell():
            self.first_read.set()
            self.release.wait(10)
        return super().read(1000)


class PartFileTests(TempDir):
    """_fetch качает во временный «<имя>.<8 знаков>.part» и только после проверок переименовывает."""

    def fetch(self, reply, path=None, cancelled=None, size=len(INSTALLER), sha256=sha(INSTALLER)):
        path = path or self.dir / EXE_NAME
        opener = (dict(side_effect=reply) if isinstance(reply, BaseException)
                  else dict(return_value=reply))
        with mock.patch.object(updater, "_urlopen", **opener):
            updater._fetch(EXE_URL, path, size, sha256, b"MZ", None, 5, cancelled)
        return path

    def parts(self):
        return sorted(p.name for p in self.dir.glob("*.part"))

    def test_writes_to_part_then_renames(self):
        path = self.dir / EXE_NAME
        seen = []

        def look(n):
            if n == 2:
                seen.append((path.exists(), self.parts()))

        self.fetch(SlowResponse(INSTALLER, look), path)
        exists, parts = seen[0]
        self.assertFalse(exists, "пока качается, готового файла с настоящим именем нет")
        self.assertEqual(len(parts), 1)
        self.assertRegex(parts[0], r"^" + EXE_NAME.replace(".", r"\.") + r"\.[0-9a-f]{8}\.part$")
        self.assertEqual(path.read_bytes(), INSTALLER)
        self.assertEqual(self.parts(), [], "после успеха .part не остаётся")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), [EXE_NAME])

    def test_success_replaces_old_file(self):
        path = self.dir / EXE_NAME
        path.write_bytes(b"MZ old")
        self.fetch(response(INSTALLER), path)
        self.assertEqual(path.read_bytes(), INSTALLER)
        self.assertEqual(self.parts(), [])

    def test_nothing_left_after_error_or_cancel(self):
        """Ошибка или «Отмена» на любом шаге — ни .part, ни файла с настоящим именем."""
        def broken(n):
            if n == 2:
                raise ConnectionResetError("оборвалось")

        cases = {
            "фильтр": dict(reply=response(FILTER_PAGE)),
            "нет сети": dict(reply=OSError("нет сети")),
            "обрыв": dict(reply=SlowResponse(INSTALLER, broken)),
            "не полностью": dict(reply=response(INSTALLER[:5000])),
            "сумма": dict(reply=response(INSTALLER), sha256="00" * 32),
            "отмена": dict(reply=SlowResponse(INSTALLER), cancelled=Flag(after=3)),
            "отмена сразу": dict(reply=response(INSTALLER), cancelled=lambda: True),
        }
        for name, case in cases.items():
            with self.subTest(name):
                reply = case.pop("reply")
                with self.assertRaises((updater.UpdateError, updater.Cancelled)):
                    self.fetch(reply, **case)
                self.assertEqual(list(self.dir.iterdir()), [])

    def test_replace_error_is_update_error(self):
        with mock.patch.object(updater.os, "replace", side_effect=PermissionError("занят")):
            with self.assertRaises(updater.UpdateError) as caught:
                self.fetch(response(INSTALLER))
        self.assertNotIsInstance(caught.exception, updater.DownloadError)
        self.assertIn("Не удалось сохранить", str(caught.exception))
        self.assertIn("занят", str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, PermissionError)
        self.assertEqual(list(self.dir.iterdir()), [], ".part убран")

    def test_replace_error_falls_back_to_zip(self):
        """Не удалось сохранить .exe — download пробует архив (тоже через .part и replace)."""
        real_replace = updater.os.replace
        calls = []

        def replace(src, dst):
            calls.append(Path(dst).name)
            if len(calls) == 1:
                raise PermissionError("занят")
            return real_replace(src, dst)

        replies = {EXE_URL: INSTALLER, ZIP_URL: ARCHIVE}
        with mock.patch.object(updater.tempfile, "gettempdir", return_value=str(self.dir)), \
                mock.patch.object(updater, "_urlopen", side_effect=lambda u, h, t: response(replies[u])), \
                mock.patch.object(updater.os, "replace", side_effect=replace):
            path = updater.download(release())
        self.assertEqual(calls, [EXE_NAME, ZIP_NAME])
        self.assertEqual(path.read_bytes(), INSTALLER)
        self.assertEqual(sorted(p.name for p in (self.dir / "ToDoro-update").iterdir()), [EXE_NAME])

    def test_cancelled_attempt_does_not_touch_finished_file_of_next(self):
        """Гонка из issue #2: первая попытка отменена, но её поток ещё ждёт сеть; вторая успела
        докачать. Когда первая проснётся, готовый установщик второй должен остаться на месте."""
        path = self.dir / EXE_NAME
        slow = BlockingResponse(INSTALLER)
        replies = [slow, response(INSTALLER)]
        first_cancel = threading.Event()
        outcome = {}

        def first():
            try:
                updater._fetch(EXE_URL, path, len(INSTALLER), sha(INSTALLER), b"MZ", None, 5,
                               first_cancel.is_set)
            except BaseException as error:  # noqa: BLE001
                outcome["error"] = error

        with mock.patch.object(updater, "_urlopen", side_effect=lambda *a: replies.pop(0)):
            thread = threading.Thread(target=first, daemon=True)
            thread.start()
            try:
                self.assertTrue(slow.first_read.wait(10), "первая попытка не начала качать")
                first_cancel.set()  # «Отмена»
                updater._fetch(EXE_URL, path, len(INSTALLER), sha(INSTALLER), b"MZ", None, 5,
                               threading.Event().is_set)  # «Обновить» ещё раз — докачалось
                self.assertEqual(path.read_bytes(), INSTALLER)
            finally:
                slow.release.set()  # поток первой попытки «проснулся»
                thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(outcome.get("error"), updater.Cancelled)
        self.assertTrue(path.exists(), "отменённая попытка удалила готовый файл другой попытки")
        self.assertEqual(path.read_bytes(), INSTALLER)
        self.assertEqual(self.parts(), [])

    def test_remove_old_downloads_cleans_part(self):
        keep = self.dir / EXE_NAME
        old = [self.dir / f"{EXE_NAME}.0123abcd.part", self.dir / "ToDoro-Setup-9.8.zip.ffffffff.part",
               self.dir / "ToDoro-Setup-9.8.exe"]
        note = self.dir / "readme.txt"
        for f in (keep, note, *old):
            f.write_bytes(b"x")
        updater.remove_old_downloads(self.dir, keep=keep)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), sorted([EXE_NAME, "readme.txt"]))

    def test_download_removes_leftover_part_before_start(self):
        folder = self.dir / "ToDoro-update"
        folder.mkdir()
        (folder / f"{EXE_NAME}.deadbeef.part").write_bytes(b"MZ half")
        with mock.patch.object(updater.tempfile, "gettempdir", return_value=str(self.dir)), \
                mock.patch.object(updater, "_urlopen", return_value=response(INSTALLER)):
            updater.download(release())
        self.assertEqual(sorted(p.name for p in folder.iterdir()), [EXE_NAME])


class RemoveTests(TempDir):
    def test_remove_missing_and_locked(self):
        updater._remove(self.dir / "нет.exe")  # нет файла — молча
        target = self.dir / "a.exe"
        target.write_bytes(b"x")
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("занят")):
            updater._remove(target)
        self.assertTrue(target.exists())
        updater._remove(target)
        self.assertFalse(target.exists())


class DownloadCancelTests(TempDir):
    def run_download(self, replies, cancelled, rel=None):
        asked = []

        def fake_urlopen(url, headers, timeout):
            asked.append(url)
            reply = replies[url]
            if isinstance(reply, BaseException):
                raise reply
            return reply() if callable(reply) else response(reply)

        with mock.patch.object(updater.tempfile, "gettempdir", return_value=str(self.dir)), \
                mock.patch.object(updater, "_urlopen", side_effect=fake_urlopen):
            try:
                return updater.download(rel or release(), None, cancelled=cancelled), asked
            except (updater.UpdateError, updater.Cancelled) as error:
                return error, asked

    def files(self):
        return sorted(p.name for p in (self.dir / "ToDoro-update").iterdir())

    def test_cancel_during_exe_does_not_try_zip(self):
        result, asked = self.run_download({EXE_URL: lambda: SlowResponse(INSTALLER),
                                           ZIP_URL: ARCHIVE}, Flag(after=2))
        self.assertIsInstance(result, updater.Cancelled)
        self.assertEqual(asked, [EXE_URL], "после отмены архив .zip не качается")
        self.assertEqual(self.files(), [])

    def test_cancel_before_start(self):
        result, asked = self.run_download({EXE_URL: INSTALLER}, lambda: True)
        self.assertIsInstance(result, updater.Cancelled)
        self.assertEqual(asked, [])

    def test_cancel_during_zip(self):
        """Фильтр не дал .exe, во время скачивания архива нажали «Отмена» — архив убран."""
        state = {"cancelled": False}

        def zip_reply():
            return SlowResponse(ARCHIVE, lambda n: state.update(cancelled=n >= 2), chunk=50)

        result, asked = self.run_download({EXE_URL: FILTER_PAGE, ZIP_URL: zip_reply},
                                          lambda: state["cancelled"],
                                          release(zip_size=len(ARCHIVE)))
        self.assertIsInstance(result, updater.Cancelled)
        self.assertEqual(asked, [EXE_URL, ZIP_URL])
        self.assertEqual(self.files(), [])

    def test_network_error_after_cancel_does_not_try_zip(self):
        state = {"cancelled": False}

        def broken():
            def on_read(n):
                if n == 2:
                    state["cancelled"] = True
                    raise ConnectionResetError("оборвалось")
            return SlowResponse(INSTALLER, on_read)

        result, asked = self.run_download({EXE_URL: broken, ZIP_URL: ARCHIVE},
                                          lambda: state["cancelled"])
        self.assertIsInstance(result, updater.Cancelled)
        self.assertEqual(asked, [EXE_URL])

    def test_not_cancelled_falls_back_to_zip_as_before(self):
        result, asked = self.run_download({EXE_URL: FILTER_PAGE, ZIP_URL: ARCHIVE}, Flag())
        self.assertEqual(asked, [EXE_URL, ZIP_URL])
        self.assertEqual(result.read_bytes(), INSTALLER)
        self.assertEqual(self.files(), [EXE_NAME])

    def test_zip_attempt_starts_progress_from_zero(self):
        """.exe не скачался — перед архивом снова on_progress(0, zip_size): отсчёт «тишины»
        в окне начинается заново, а не продолжается с неудачной попытки."""
        events = []
        replies = {EXE_URL: FILTER_PAGE, ZIP_URL: ARCHIVE}

        def fake_urlopen(url, headers, timeout):
            events.append(("connect", url))
            return response(replies[url])

        with mock.patch.object(updater.tempfile, "gettempdir", return_value=str(self.dir)),                 mock.patch.object(updater, "_urlopen", side_effect=fake_urlopen):
            path = updater.download(release(), lambda *a: events.append(a))
        self.assertEqual(path.read_bytes(), INSTALLER)
        zip_start = events.index(("connect", ZIP_URL))
        self.assertEqual(events[zip_start - 1], (0, len(ARCHIVE)), "до соединения с архивом")
        self.assertEqual(events[zip_start + 1], (0, len(ARCHIVE)), "после соединения с архивом")
        self.assertEqual(events[0], (0, len(INSTALLER)), "попытка .exe тоже начинается с нуля")
        self.assertEqual(events[-1], (len(ARCHIVE), len(ARCHIVE)))

    def test_zip_attempt_zero_progress_without_zip_size(self):
        events = []
        replies = {EXE_URL: OSError("reset"), ZIP_URL: ARCHIVE}

        def fake_urlopen(url, headers, timeout):
            events.append(("connect", url))
            if isinstance(replies[url], BaseException):
                raise replies[url]
            return response(replies[url])

        with mock.patch.object(updater.tempfile, "gettempdir", return_value=str(self.dir)),                 mock.patch.object(updater, "_urlopen", side_effect=fake_urlopen):
            updater.download(release(zip_size=None), lambda *a: events.append(a))
        zip_start = events.index(("connect", ZIP_URL))
        self.assertEqual(events[zip_start - 1], (0, 0))
        self.assertEqual(events[zip_start + 1], (0, len(ARCHIVE)))

    def test_signature_defaults(self):
        """Старые вызовы download(release, on_progress) работают: cancelled необязателен."""
        result, _ = self.run_download({EXE_URL: INSTALLER}, None)
        self.assertEqual(result.name, EXE_NAME)
        self.assertNotIn(ZIP_NAME, self.files())


# ----------------------------------------------------------------- окна, без настоящего Tk

class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


class UpdateDialogDownloadTests(unittest.TestCase):
    """UpdateDialog.update_now / cancel_download / close_during_download на подставном окне."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro
        U = todoro.UpdateDialog

        class FakeDialog:
            STALL_S = U.STALL_S
            update_now = U.update_now
            restore_buttons = U.restore_buttons
            cancel_download = U.cancel_download
            close_during_download = U.close_during_download

            def __init__(self):
                self.release = release(url="https://github.com/r/v9.9")
                self.self_update = True
                # главное окно: его after собирает отложенные вызовы (тик скачивания)
                self.master = SimpleNamespace(after=mock.Mock(name="master.after"))
                self.ok_button = mock.Mock(name="ok")
                self.later_button = mock.Mock(name="later")
                self.progress = mock.MagicMock(name="progress")
                self.status = mock.Mock(name="status")
                self.protocol = mock.Mock(name="protocol")
                self.after = mock.Mock(name="after")
                self.update_idletasks = mock.Mock()
                self.explain_blocked = mock.Mock()
                self.on_close_app = mock.Mock()
                self.alive = True
                self.destroy = mock.Mock(side_effect=lambda: setattr(self, "alive", False))

            def winfo_exists(self):
                return self.alive

        cls.Fake = FakeDialog

    def setUp(self):
        self.clock = Clock()
        self.started = []  # (root, work, done) для каждой попытки
        patches = [
            mock.patch.object(self.T, "time_module", self.clock),
            mock.patch.object(self.T, "in_background",
                              side_effect=lambda root, work, done: self.started.append((root, work, done))),
            mock.patch.object(self.T.updater, "download", return_value=Path("C:/x/setup.exe")),
            mock.patch.object(self.T.updater, "run_installer"),
            mock.patch.object(self.T.tray, "stop"),
            mock.patch.object(self.T.webbrowser, "open"),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.download = self.T.updater.download
        self.run_installer = self.T.updater.run_installer
        self.dialog = self.Fake()

    def start(self):
        self.dialog.update_now()
        root, work, done = self.started[-1]
        return work, done

    def last_status(self):
        return self.dialog.status.configure.call_args.kwargs

    def assert_restored(self):
        d = self.dialog
        d.ok_button.state.assert_called_with(["!disabled"])
        d.later_button.state.assert_called_with(["!disabled"])
        d.later_button.configure.assert_called_with(text="Позже", command=d.destroy)
        d.protocol.assert_called_with("WM_DELETE_WINDOW", d.destroy)
        d.progress.pack_forget.assert_called()

    def test_download_turns_later_into_cancel(self):
        work, _ = self.start()
        d = self.dialog
        root = self.started[-1][0]
        self.assertIs(root, d.master, "поток ждётся через главное окно")
        d.ok_button.state.assert_called_with(["disabled"])
        d.later_button.configure.assert_called_with(text="Отмена", command=d.cancel_download)
        d.later_button.state.assert_not_called()  # «Отмена» доступна
        d.protocol.assert_called_with("WM_DELETE_WINDOW", d.close_during_download)
        self.assertTrue(d.downloading)
        self.assertFalse(d.cancel_event.is_set())
        work()
        args, kwargs = self.download.call_args
        self.assertIs(args[0], d.release)
        self.assertFalse(kwargs["cancelled"]())
        d.cancel_event.set()
        self.assertTrue(kwargs["cancelled"](), "download видит «Отмену» этой попытки")

    def test_page_only_when_no_self_update(self):
        self.dialog.self_update = False
        self.dialog.update_now()
        self.T.webbrowser.open.assert_called_once_with("https://github.com/r/v9.9")
        self.dialog.destroy.assert_called_once()
        self.assertEqual(self.started, [])

    def test_cancel_restores_and_ignores_result(self):
        _, done = self.start()
        d = self.dialog
        d.cancel_download()
        self.assertTrue(d.cancel_event.is_set())
        self.assertFalse(d.downloading)
        self.assert_restored()
        self.assertEqual(self.last_status()["text"], "Скачивание отменено.")
        self.assertEqual(self.last_status()["fg"], self.T.MUTED)
        status_calls = d.status.configure.call_count
        done(Path("C:/x/setup.exe"), None)  # поток всё-таки докачал — ничего не запускаем
        self.run_installer.assert_not_called()
        self.T.tray.stop.assert_not_called()
        done(None, updater.DownloadError("сбой"))  # или упал — сообщение «отменено» не затираем
        self.assertEqual(d.status.configure.call_count, status_calls)
        d.explain_blocked.assert_not_called()

    def test_cancelled_exception_after_cancel_is_silent(self):
        _, done = self.start()
        self.dialog.cancel_download()
        calls = self.dialog.status.configure.call_count
        done(None, updater.Cancelled())
        self.assertEqual(self.dialog.status.configure.call_count, calls)

    def test_retry_after_cancel_uses_new_event(self):
        """Вторая попытка после «Отмены»: у неё своя отмена, ответ первой не мешает."""
        _, first_done = self.start()
        first_event = self.dialog.cancel_event
        self.dialog.cancel_download()
        work2, second_done = self.start()
        self.assertIsNot(self.dialog.cancel_event, first_event)
        self.assertFalse(self.dialog.cancel_event.is_set())
        self.assertTrue(self.dialog.downloading)
        first_done(None, updater.DownloadError("старая попытка"))  # опоздавший ответ первой
        self.assertTrue(self.dialog.downloading, "ответ отменённой попытки не трогает новую")
        self.assertNotIn("старая попытка", str(self.last_status().get("text")))
        second_done(Path("C:/x/setup.exe"), None)
        self.run_installer.assert_called_once_with(Path("C:/x/setup.exe"))
        self.dialog.after.assert_called_with(500, self.dialog.on_close_app)

    def test_close_during_download(self):
        _, done = self.start()
        d = self.dialog
        d.close_during_download()
        self.assertTrue(d.cancel_event.is_set())
        self.assertFalse(d.downloading)
        d.destroy.assert_called_once()
        done(Path("C:/x/setup.exe"), None)
        self.run_installer.assert_not_called()

    def test_finished_after_window_destroyed_otherwise(self):
        """Окно закрыто иначе (вместе с программой) — результат тоже не трогает его."""
        _, done = self.start()
        self.dialog.alive = False
        done(Path("C:/x/setup.exe"), None)
        self.run_installer.assert_not_called()

    def test_error_restores_buttons(self):
        _, done = self.start()
        done(None, updater.DownloadError("Не удалось скачать обновление.", "сбой"))
        self.assert_restored()
        self.assertFalse(self.dialog.downloading)
        self.assertEqual(self.last_status()["text"], "Не удалось скачать обновление.")
        self.assertEqual(self.last_status()["fg"], self.T.DANGER)

    def test_blocked_error_explained(self):
        _, done = self.start()
        error = updater.BlockedError(updater.blocked_message())
        done(None, error)
        self.assert_restored()
        self.dialog.explain_blocked.assert_called_once_with(error)

    def test_unexpected_error_text(self):
        _, done = self.start()
        done(None, ValueError("странное"))
        self.assertEqual(self.last_status()["text"], "Ошибка: странное")

    def test_success_disables_cancel_and_installs(self):
        _, done = self.start()
        d = self.dialog
        done(Path("C:/x/setup.exe"), None)
        d.later_button.state.assert_called_with(["disabled"])
        self.assertEqual(d.protocol.call_args.args[0], "WM_DELETE_WINDOW")
        self.assertIsNot(d.protocol.call_args.args[1], d.close_during_download)
        self.T.tray.stop.assert_called_once()
        self.run_installer.assert_called_once()
        d.after.assert_called_with(500, d.on_close_app)

    def test_installer_failure_restores_buttons(self):
        """Установщик не запустился — окно снова можно закрыть, а не «замороженное»."""
        self.run_installer.side_effect = OSError("нет доступа")
        _, done = self.start()
        done(Path("C:/x/setup.exe"), None)
        self.assert_restored()
        self.assertIn("нет доступа", self.last_status()["text"])
        self.dialog.on_close_app.assert_not_called()

    def scheduled_tick(self):
        """Последний отложенный тик — он планируется через главное окно, не через это."""
        call = self.dialog.master.after.call_args
        self.assertEqual(call.args[0], 150)
        for args in self.dialog.after.call_args_list:
            self.assertNotEqual(args.args[0], 150, "тик не должен планироваться через само окно")
        return call.args[1]

    def kill_widgets(self):
        """Как у настоящего закрытого окна: любое обращение к его частям — TclError."""
        error = self.T.tk.TclError("invalid command name")
        d = self.dialog
        for widget in (d.status, d.ok_button, d.later_button):
            for name in ("configure", "state", "pack_forget"):
                getattr(widget, name).side_effect = error
        d.progress.__setitem__.side_effect = error
        d.progress.pack_forget.side_effect = error
        d.after.side_effect = error
        d.protocol.side_effect = error

    def test_tick_after_close_during_download_is_harmless(self):
        """Окно закрыли крестиком посреди скачивания — отложенный тик ничего не делает и не падает."""
        work, done = self.start()
        work()
        progress = self.download.call_args.args[1]
        tick = self.scheduled_tick()
        self.dialog.close_during_download()
        self.kill_widgets()
        progress(5 * 1048576, 10 * 1048576)
        planned = self.dialog.master.after.call_count
        for extra in (0, self.dialog.STALL_S + 5):  # и обычный тик, и «давно нет данных»
            self.clock.now += extra
            tick()  # не должно быть TclError
        self.assertEqual(self.dialog.master.after.call_count, planned, "тик больше не планируется")
        done(Path("C:/x/setup.exe"), None)
        self.run_installer.assert_not_called()

    def test_tick_after_window_destroyed_otherwise(self):
        """Окно уничтожено не через крестик (закрылась программа), отмена не ставилась —
        тик всё равно молча останавливается."""
        self.start()
        tick = self.scheduled_tick()
        self.dialog.alive = False
        self.kill_widgets()
        planned = self.dialog.master.after.call_count
        self.clock.now += self.dialog.STALL_S + 5
        tick()
        self.assertEqual(self.dialog.master.after.call_count, planned)

    def test_stall_cancels_with_error(self):
        """STALL_S секунд не пришло ни байта — скачивание останавливается с понятным сообщением."""
        work, done = self.start()
        work()
        progress = self.download.call_args.args[1]
        tick = self.scheduled_tick()
        self.clock.now += self.dialog.STALL_S // 2
        progress(1000, len(INSTALLER))  # что-то пришло — счётчик «тишины» заново
        tick()
        tick = self.scheduled_tick()
        self.clock.now += self.dialog.STALL_S - 5  # чуть меньше STALL_S после последней порции — ждём
        tick()
        self.assertTrue(self.dialog.downloading)
        self.assertFalse(self.dialog.cancel_event.is_set())
        tick = self.scheduled_tick()
        self.clock.now += self.dialog.STALL_S  # тишина дольше STALL_S
        after_calls = self.dialog.master.after.call_count
        tick()
        self.assertTrue(self.dialog.cancel_event.is_set())
        self.assertFalse(self.dialog.downloading)
        self.assert_restored()
        self.assertIn("не скачивается", self.last_status()["text"])
        self.assertEqual(self.last_status()["fg"], self.T.DANGER)
        self.assertEqual(self.dialog.master.after.call_count, after_calls, "тик больше не планируется")
        done(Path("C:/x/setup.exe"), None)
        self.run_installer.assert_not_called()

    def test_zero_progress_resets_stall(self):
        """on_progress(0, …) — начало новой попытки (.zip после .exe): отсчёт «тишины» заново."""
        work, _ = self.start()
        work()
        progress = self.download.call_args.args[1]
        self.clock.now += self.dialog.STALL_S - 5
        progress(0, len(ARCHIVE))
        tick = self.scheduled_tick()
        self.clock.now += self.dialog.STALL_S - 5
        tick()
        self.assertTrue(self.dialog.downloading)
        self.assertFalse(self.dialog.cancel_event.is_set())

    def test_stall_limit_is_90(self):
        self.assertEqual(self.T.UpdateDialog.STALL_S, 90)

    def test_stall_from_start_without_any_bytes(self):
        self.start()
        tick = self.scheduled_tick()
        self.clock.now += self.dialog.STALL_S + 1
        tick()
        self.assertTrue(self.dialog.cancel_event.is_set())

    def test_old_tick_does_not_touch_new_attempt(self):
        """Тик отменённой попытки после «Обновить» ещё раз не останавливает новую."""
        self.start()
        old_tick = self.scheduled_tick()
        self.dialog.cancel_download()
        self.start()
        self.clock.now += self.dialog.STALL_S + 5
        old_tick()
        self.assertTrue(self.dialog.downloading)
        self.assertFalse(self.dialog.cancel_event.is_set())

    def test_progress_shown(self):
        work, _ = self.start()
        work()
        progress = self.download.call_args.args[1]
        progress(3 * 1048576, 10 * 1048576)
        self.scheduled_tick()()
        self.dialog.progress.__setitem__.assert_called_with("value", 30.0)
        self.assertIn("3 из 10 МБ", self.last_status()["text"])


class CheckingDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def fake(self, alive=True):
        state = {"alive": alive}
        fake = SimpleNamespace(cancelled=False, bar=mock.Mock(),
                               winfo_exists=lambda: state["alive"],
                               destroy=mock.Mock(side_effect=lambda: state.update(alive=False)))
        fake.close = lambda: self.T.CheckingDialog.close(fake)
        return fake

    def test_cancel_marks_and_closes(self):
        fake = self.fake()
        self.T.CheckingDialog.cancel(fake)
        self.assertTrue(fake.cancelled)
        fake.bar.stop.assert_called_once()
        fake.destroy.assert_called_once()

    def test_close_twice_is_safe(self):
        fake = self.fake()
        self.T.CheckingDialog.close(fake)
        self.T.CheckingDialog.close(fake)
        fake.destroy.assert_called_once()
        self.assertFalse(fake.cancelled)

    def test_close_when_already_gone(self):
        fake = self.fake(alive=False)
        self.T.CheckingDialog.cancel(fake)
        self.assertTrue(fake.cancelled)
        fake.destroy.assert_not_called()


class CheckUpdateNowTests(unittest.TestCase):
    """TodoApp.check_update_now: окошко «Проверяю…» сразу, ответ после «Отмены» не показывается."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def setUp(self):
        self.order = []
        self.waiting = SimpleNamespace(cancelled=False, close=mock.Mock())
        self.started = []
        patches = {
            "CheckingDialog": mock.patch.object(
                self.T, "CheckingDialog",
                side_effect=lambda root: self.order.append("dialog") or self.waiting),
            "in_background": mock.patch.object(
                self.T, "in_background",
                side_effect=lambda root, work, done: self.order.append("bg")
                or self.started.append((root, work, done))),
            "UpdateDialog": mock.patch.object(self.T, "UpdateDialog"),
            "showinfo": mock.patch.object(self.T.ui, "showinfo"),
            "showwarning": mock.patch.object(self.T.ui, "showwarning"),
        }
        self.m = {name: p.start() for name, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)
        self.app = SimpleNamespace(root=mock.Mock(name="root"), close=mock.Mock())
        self.T.TodoApp.check_update_now(self.app)
        self.root, self.work, self.done = self.started[0]

    def assert_nothing_shown(self):
        self.m["UpdateDialog"].assert_not_called()
        self.m["showinfo"].assert_not_called()
        self.m["showwarning"].assert_not_called()

    def test_dialog_shown_before_request(self):
        self.assertEqual(self.order, ["dialog", "bg"])
        self.m["CheckingDialog"].assert_called_once_with(self.app.root)
        self.assertIs(self.root, self.app.root)
        self.assertIs(self.work, updater.fetch_latest)

    def test_newer_version(self):
        rel = {"version": "999.0"}
        self.done(rel, None)
        self.waiting.close.assert_called_once()
        self.m["UpdateDialog"].assert_called_once_with(self.app.root, rel, self.app.close)

    def test_same_version(self):
        self.done({"version": self.T.APP_VERSION}, None)
        self.waiting.close.assert_called_once()
        self.m["showinfo"].assert_called_once()
        self.m["UpdateDialog"].assert_not_called()

    def test_error(self):
        self.done(None, updater.UpdateError("Не удалось связаться с GitHub."))
        self.waiting.close.assert_called_once()
        self.m["showwarning"].assert_called_once()
        self.assertIn("GitHub", self.m["showwarning"].call_args.args[1])

    def test_cancelled_ignores_answer(self):
        for answer in (({"version": "999.0"}, None), (None, updater.UpdateError("x")),
                       ({"version": self.T.APP_VERSION}, None)):
            with self.subTest(answer=answer):
                self.waiting.cancelled = True
                self.done(*answer)
                self.assert_nothing_shown()
                self.waiting.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
