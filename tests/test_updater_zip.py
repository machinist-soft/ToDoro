"""Запасное скачивание обновления архивом ToDoro-Setup-<версия>.zip, когда фильтр сети
(например, корпоративный FortiGate) не даёт скачать .exe: fetch_latest, check_release, _fetch,
download, remove_old_downloads, окно «Обновление не скачалось» и make_zip из build_installer.

Сеть не используется: updater._urlopen подменяется; всё пишется во временную папку.
Запуск из папки проекта:  python -m unittest discover tests
"""
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import updater  # noqa: E402

EXE_URL = "https://github.com/machinist-soft/ToDoro/releases/download/v9.9/ToDoro-Setup-9.9.exe"
ZIP_URL = "https://github.com/machinist-soft/ToDoro/releases/download/v9.9/ToDoro-Setup-9.9.zip"
EXE_NAME = "ToDoro-Setup-9.9.exe"
ZIP_NAME = "ToDoro-Setup-9.9.zip"
INSTALLER = b"MZ" + b"installer body " * 5000
FILTER_PAGE = b"<html><body>FortiGate: Download blocked</body></html>"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def zip_bytes(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buffer.getvalue()


ARCHIVE = zip_bytes({EXE_NAME: INSTALLER})


def response(data):
    r = io.BytesIO(data)
    r.headers = {"Content-Length": str(len(data))}
    return r


class BrokenResponse(io.BytesIO):
    """Отдаёт первый кусок, а потом связь обрывается."""
    headers = {}

    def read(self, size=-1):
        if self.tell():
            raise ConnectionResetError("связь оборвалась")
        return super().read(1000)


def release(**changes):
    r = dict(asset_url=EXE_URL, asset_name=EXE_NAME, size=len(INSTALLER), sha256=sha(INSTALLER),
             zip_url=ZIP_URL, zip_name=ZIP_NAME, zip_size=len(ARCHIVE), zip_sha256=sha(ARCHIVE))
    r.update(changes)
    return r


class TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-test-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class FetchLatestZipTests(unittest.TestCase):
    def fetch(self, assets):
        data = json.dumps({"tag_name": "v9.9", "body": "что нового", "html_url": "https://x",
                           "assets": assets}).encode()
        with mock.patch.object(updater, "_urlopen", return_value=response(data)):
            return updater.fetch_latest()

    def test_finds_exe_and_zip(self):
        r = self.fetch([
            {"name": "ToDoro.apk", "browser_download_url": "https://github.com/a/ToDoro.apk",
             "size": 1, "digest": "sha256:" + "11" * 32},
            {"name": ZIP_NAME, "browser_download_url": ZIP_URL, "size": 200,
             "digest": "sha256:" + "AB" * 32},
            {"name": EXE_NAME, "browser_download_url": EXE_URL, "size": 100,
             "digest": "sha256:" + "cd" * 32},
        ])
        self.assertEqual(r["version"], "9.9")
        self.assertEqual((r["asset_url"], r["asset_name"], r["size"], r["sha256"]),
                         (EXE_URL, EXE_NAME, 100, "cd" * 32))
        self.assertEqual((r["zip_url"], r["zip_name"], r["zip_size"]), (ZIP_URL, ZIP_NAME, 200))
        self.assertEqual(r["zip_sha256"], "ab" * 32, "сумма приводится к строчным буквам")

    def test_old_release_without_zip(self):
        """В старых выпусках архива нет — zip_* равны None, установщик находится как раньше."""
        r = self.fetch([{"name": EXE_NAME, "browser_download_url": EXE_URL, "size": 100,
                         "digest": "sha256:" + "cd" * 32},
                        {"name": "Source code.zip", "browser_download_url": "https://github.com/s.zip"}])
        self.assertEqual(r["asset_url"], EXE_URL)
        for key in ("zip_url", "zip_name", "zip_size", "zip_sha256"):
            self.assertIsNone(r[key], key)

    def test_zip_without_or_with_other_digest(self):
        for digest in (None, "", "md5:abc", "sha256"):
            with self.subTest(digest=digest):
                r = self.fetch([{"name": ZIP_NAME, "browser_download_url": ZIP_URL,
                                 "digest": digest}])
                self.assertEqual(r["zip_url"], ZIP_URL)
                self.assertIsNone(r["zip_sha256"])
                self.assertIsNone(r["asset_url"])

    def test_no_assets_at_all(self):
        r = self.fetch([])
        self.assertIsNone(r["zip_url"])
        self.assertIsNone(r["asset_url"])


class CheckReleaseZipTests(unittest.TestCase):
    def test_zip_only_from_github_with_checksum(self):
        updater.check_release(release(), "zip")  # всё в порядке
        # проверяются именно поля архива, а не установщика
        updater.check_release(release(asset_url=None, sha256=None), "zip")
        for wrong in ({"zip_url": ZIP_URL.replace("https", "http")},
                      {"zip_url": "https://github.com.evil.example/ToDoro-Setup-9.9.zip"},
                      {"zip_url": "https://objects.githubusercontent.com/ToDoro-Setup-9.9.zip"},
                      {"zip_url": "file:///C:/ToDoro-Setup-9.9.zip"},
                      {"zip_url": None}, {"zip_url": ""},
                      {"zip_sha256": None}, {"zip_sha256": ""}):
            with self.subTest(wrong=wrong), self.assertRaises(updater.UpdateError):
                updater.check_release(release(**wrong), "zip")

    def test_default_prefix_ignores_zip_fields(self):
        updater.check_release(release(zip_url="http://evil.example/x.zip", zip_sha256=None))


class FetchTests(TempDir):
    def fetch(self, reply, size=None, sha256=None, magic=b"MZ", on_progress=None):
        path = self.dir / EXE_NAME
        opener = (dict(side_effect=reply) if isinstance(reply, BaseException)
                  else dict(return_value=reply))
        with mock.patch.object(updater, "_urlopen", **opener):
            updater._fetch(EXE_URL, path, size, sha256, magic, on_progress, 5)
        return path

    def test_good_file_with_progress(self):
        progress = []
        path = self.fetch(response(INSTALLER), len(INSTALLER), sha(INSTALLER),
                          on_progress=lambda got, total: progress.append((got, total)))
        self.assertEqual(path.read_bytes(), INSTALLER)
        self.assertEqual(progress[-1], (len(INSTALLER), len(INSTALLER)))

    def test_filter_page_instead_of_file(self):
        """Вместо .exe пришла страница фильтра — BlockedError, недописанный файл удалён."""
        with self.assertRaises(updater.BlockedError) as caught:
            self.fetch(response(FILTER_PAGE), None, sha(FILTER_PAGE))
        self.assertTrue(caught.exception.details)
        self.assertIn("фильтр", str(caught.exception))
        self.assertFalse((self.dir / EXE_NAME).exists())

    def test_wrong_magic_for_zip(self):
        """Для архива ждём «PK»: .exe на месте архива — тоже страница не та."""
        with self.assertRaises(updater.BlockedError):
            self.fetch(response(INSTALLER), None, sha(INSTALLER), magic=b"PK")
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_network_error_is_download_error_with_details(self):
        with self.assertRaises(updater.DownloadError) as caught:
            self.fetch(OSError("нет сети"), len(INSTALLER), sha(INSTALLER))
        self.assertNotIsInstance(caught.exception, updater.BlockedError)
        self.assertIn("нет сети", caught.exception.details)
        self.assertIn("нет сети", str(caught.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_connection_lost_midway_removes_partial_file(self):
        with self.assertRaises(updater.DownloadError):
            self.fetch(BrokenResponse(INSTALLER), len(INSTALLER), sha(INSTALLER))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_incomplete_file(self):
        part = INSTALLER[:1000]
        with self.assertRaises(updater.UpdateError) as caught:
            self.fetch(response(part), len(INSTALLER), sha(INSTALLER))
        self.assertNotIsInstance(caught.exception, updater.DownloadError)
        self.assertIn("не полностью", str(caught.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_wrong_checksum(self):
        with self.assertRaises(updater.UpdateError) as caught:
            self.fetch(response(INSTALLER), len(INSTALLER), "00" * 32)
        self.assertNotIsInstance(caught.exception, updater.DownloadError)
        self.assertIn("контрольная сумма", str(caught.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_empty_answer(self):
        """Пустой ответ без размера — не совпала сумма, а не «успех»."""
        with self.assertRaises(updater.UpdateError):
            self.fetch(response(b""), None, sha(INSTALLER))
        self.assertEqual(list(self.dir.iterdir()), [])


class DownloadZipFallbackTests(TempDir):
    """download(): сначала .exe, при неудаче — архив .zip."""

    def run_download(self, replies, rel=None, on_progress=None):
        """replies — {адрес: байты или исключение}; возвращает (результат или ошибка, адреса)."""
        asked = []

        def fake_urlopen(url, headers, timeout):
            asked.append(url)
            reply = replies[url]
            if isinstance(reply, BaseException):
                raise reply
            return response(reply)

        with mock.patch.object(updater.tempfile, "gettempdir", return_value=str(self.dir)), \
                mock.patch.object(updater, "_urlopen", side_effect=fake_urlopen):
            try:
                return updater.download(rel or release(), on_progress), asked
            except updater.UpdateError as error:
                return error, asked

    @property
    def folder(self):
        return self.dir / "ToDoro-update"

    def files(self):
        return sorted(p.name for p in self.folder.iterdir())

    def test_exe_downloads_zip_not_touched(self):
        result, asked = self.run_download({EXE_URL: INSTALLER})
        self.assertEqual(result, self.folder / EXE_NAME)
        self.assertEqual(asked, [EXE_URL])
        self.assertEqual(self.files(), [EXE_NAME])

    def test_blocked_exe_falls_back_to_zip(self):
        """Фильтр отдал страницу вместо .exe — установщик достаётся из .zip, архив удалён."""
        progress = []
        result, asked = self.run_download({EXE_URL: FILTER_PAGE, ZIP_URL: ARCHIVE},
                                          on_progress=lambda *a: progress.append(a))
        self.assertEqual(asked, [EXE_URL, ZIP_URL])
        self.assertEqual(result, self.folder / EXE_NAME)
        self.assertEqual(result.read_bytes(), INSTALLER)
        self.assertEqual(self.files(), [EXE_NAME], "архив после распаковки удалён")
        self.assertEqual(progress[-1], (len(ARCHIVE), len(ARCHIVE)))

    def test_network_error_on_exe_falls_back_to_zip(self):
        result, _ = self.run_download({EXE_URL: OSError("reset"), ZIP_URL: ARCHIVE})
        self.assertEqual(result.read_bytes(), INSTALLER)
        self.assertEqual(self.files(), [EXE_NAME])

    def test_bad_exe_checksum_falls_back_to_zip(self):
        result, _ = self.run_download({EXE_URL: b"MZ broken", ZIP_URL: ARCHIVE},
                                      release(size=None))
        self.assertEqual(result.read_bytes(), INSTALLER)

    def test_both_blocked(self):
        """Не скачались ни .exe, ни .zip — BlockedError с адресами и обеими причинами."""
        for exe, archive in ((FILTER_PAGE, FILTER_PAGE), (OSError("exe-сбой"), OSError("zip-сбой")),
                             (FILTER_PAGE, OSError("zip-сбой")), (OSError("exe-сбой"), FILTER_PAGE)):
            with self.subTest(exe=exe, archive=archive):
                error, asked = self.run_download({EXE_URL: exe, ZIP_URL: archive})
                self.assertIsInstance(error, updater.BlockedError)
                self.assertEqual(asked, [EXE_URL, ZIP_URL])
                text = str(error)
                for host in updater.DOWNLOAD_HOSTS:
                    self.assertIn(host, text)
                self.assertIn(updater.RELEASES_PAGE, text)
                self.assertIn(".exe —", error.details)
                self.assertIn(".zip —", error.details)
                if isinstance(exe, OSError):
                    self.assertIn("exe-сбой", error.details)
                if isinstance(archive, OSError):
                    self.assertIn("zip-сбой", error.details)
                self.assertEqual(self.files(), [])

    def test_no_zip_blocked_exe_is_blocked_error(self):
        for no_zip in (dict(zip_url=None, zip_name=None, zip_size=None, zip_sha256=None),):
            error, asked = self.run_download({EXE_URL: FILTER_PAGE}, release(**no_zip))
            self.assertIsInstance(error, updater.BlockedError)
            self.assertEqual(asked, [EXE_URL])
            self.assertEqual(self.files(), [])

    def test_no_zip_network_error_as_before(self):
        error, _ = self.run_download({EXE_URL: OSError("нет сети")}, release(zip_url=None))
        self.assertIsInstance(error, updater.DownloadError)
        self.assertNotIsInstance(error, updater.BlockedError)
        self.assertIn("подключение к интернету", str(error))

    def test_no_zip_bad_checksum_as_before(self):
        error, _ = self.run_download({EXE_URL: INSTALLER}, release(zip_url=None, sha256="00" * 32))
        self.assertIn("контрольная сумма", str(error))
        self.assertEqual(self.files(), [])

    def test_zip_not_on_github_not_downloaded(self):
        evil = "https://evil.example/ToDoro-Setup-9.9.zip"
        error, asked = self.run_download({EXE_URL: FILTER_PAGE, evil: ARCHIVE},
                                         release(zip_url=evil))
        self.assertIsInstance(error, updater.UpdateError)
        self.assertEqual(asked, [EXE_URL])
        self.assertEqual(self.files(), [])

    def test_zip_without_checksum_not_downloaded(self):
        error, asked = self.run_download({EXE_URL: OSError("reset"), ZIP_URL: ARCHIVE},
                                         release(zip_sha256=None))
        self.assertIn("контрольную сумму", str(error))
        self.assertEqual(asked, [EXE_URL])

    def test_zip_wrong_checksum(self):
        error, _ = self.run_download({EXE_URL: FILTER_PAGE, ZIP_URL: ARCHIVE},
                                     release(zip_sha256="00" * 32))
        self.assertIn("контрольная сумма", str(error))
        self.assertEqual(self.files(), [])

    def test_broken_archive(self):
        """Сумма совпала, но это не ZIP (только начинается с «PK») — понятная ошибка, всё убрано."""
        broken = b"PK" + b"\x00" * 500
        error, _ = self.run_download({EXE_URL: FILTER_PAGE, ZIP_URL: broken},
                                     release(zip_size=len(broken), zip_sha256=sha(broken)))
        self.assertIsInstance(error, updater.UpdateError)
        self.assertIn("распаковать", str(error))
        self.assertEqual(self.files(), [])

    def test_archive_without_installer(self):
        other = zip_bytes({"ToDoro-Setup-1.0.exe": INSTALLER, "readme.txt": b"x"})
        error, _ = self.run_download({EXE_URL: FILTER_PAGE, ZIP_URL: other},
                                     release(zip_size=len(other), zip_sha256=sha(other)))
        self.assertIn("распаковать", str(error))
        self.assertEqual(self.files(), [])

    def test_archive_with_path_inside_does_not_escape(self):
        """В архиве файл лежит в подпапке — его не находим (ищется только имя установщика)."""
        nested = zip_bytes({"../" + EXE_NAME: INSTALLER})
        error, _ = self.run_download({EXE_URL: FILTER_PAGE, ZIP_URL: nested},
                                     release(zip_size=len(nested), zip_sha256=sha(nested)))
        self.assertIsInstance(error, updater.UpdateError)
        self.assertFalse((self.dir / EXE_NAME).exists())
        self.assertEqual(self.files(), [])

    def test_exe_bad_checksum_and_zip_network_error(self):
        """.exe повреждён, архив не скачался — ошибка, файлов не осталось."""
        error, _ = self.run_download({EXE_URL: b"MZ broken", ZIP_URL: OSError("reset")},
                                     release(size=None))
        self.assertIsInstance(error, updater.UpdateError)
        self.assertEqual(self.files(), [])

    def test_old_zip_removed_before_download(self):
        self.folder.mkdir()
        (self.folder / "ToDoro-Setup-9.8.zip").write_bytes(b"old")
        (self.folder / "ToDoro-Setup-9.8.exe").write_bytes(b"old")
        self.run_download({EXE_URL: INSTALLER})
        self.assertEqual(self.files(), [EXE_NAME])

    def test_other_installer_inside_archive_rejected(self):
        """Сумма архива верна, но установщик внутри — не тот, что в выпуске: не запускаем."""
        other = zip_bytes({EXE_NAME: b"MZ other build"})
        error, _ = self.run_download({EXE_URL: FILTER_PAGE, ZIP_URL: other},
                                     release(zip_size=len(other), zip_sha256=sha(other)))
        self.assertIsInstance(error, updater.UpdateError)
        self.assertIn("не совпал", str(error))
        self.assertEqual(self.files(), [])

    def test_blocked_exe_and_zip_without_checksum_keeps_filter_message(self):
        """Фильтр не пустил .exe, а у архива нет суммы — объяснение про фильтр не теряется."""
        error, asked = self.run_download({EXE_URL: FILTER_PAGE}, release(zip_sha256=None))
        self.assertIsInstance(error, updater.BlockedError)
        self.assertIn(updater.DOWNLOAD_HOSTS[-1], str(error))
        self.assertEqual(asked, [EXE_URL])


class BlockedMessageTests(unittest.TestCase):
    def test_message_has_hosts_page_and_details(self):
        text = updater.blocked_message("причина")
        for host in updater.DOWNLOAD_HOSTS:
            self.assertIn(host, text)
        self.assertIn(updater.RELEASES_PAGE, text)
        self.assertIn("Подробности: причина", text)
        self.assertNotIn("Подробности", updater.blocked_message())

    def test_error_classes(self):
        self.assertTrue(issubclass(updater.BlockedError, updater.DownloadError))
        self.assertTrue(issubclass(updater.DownloadError, updater.UpdateError))
        self.assertEqual(updater.DownloadError("x").details, "")


class RemoveOldZipTests(TempDir):
    def test_removes_old_zip_keeps_new(self):
        old_zip, new = self.dir / "ToDoro-Setup-9.8.zip", self.dir / "ToDoro-Setup-9.9.exe"
        note = self.dir / "readme.txt"
        for f in (old_zip, new, note):
            f.write_text("x")
        updater.remove_old_downloads(self.dir, keep=new)
        self.assertFalse(old_zip.exists())
        self.assertTrue(new.exists())
        self.assertTrue(note.exists())


class ExplainBlockedTests(unittest.TestCase):
    """UpdateDialog.explain_blocked без настоящего окна: AlertDialog и браузер подменены."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def call(self, choice):
        fake = SimpleNamespace(clipboard_clear=mock.Mock(), clipboard_append=mock.Mock(),
                               status=mock.Mock(), release={"url": "https://github.com/r/v9.9"})
        dialog = mock.Mock()
        dialog.return_value.show.return_value = choice
        with mock.patch.object(self.T, "AlertDialog", dialog), \
                mock.patch.object(self.T.webbrowser, "open") as browser:
            self.T.UpdateDialog.explain_blocked(fake, updater.BlockedError(updater.blocked_message()))
        return fake, dialog, browser

    def test_copy_addresses(self):
        fake, dialog, browser = self.call("copy")
        fake.clipboard_clear.assert_called_once()
        fake.clipboard_append.assert_called_once_with("\n".join(updater.DOWNLOAD_HOSTS))
        fake.status.configure.assert_called_once()
        browser.assert_not_called()
        args = dialog.call_args.args
        self.assertIn("github.com", args[2], "в окне — текст ошибки с адресами")

    def test_open_release_page(self):
        fake, _, browser = self.call("page")
        browser.assert_called_once_with("https://github.com/r/v9.9")
        fake.clipboard_append.assert_not_called()

    def test_close(self):
        fake, _, browser = self.call(None)
        browser.assert_not_called()
        fake.clipboard_append.assert_not_called()
        fake.status.configure.assert_not_called()


class MakeZipTests(TempDir):
    def setUp(self):
        super().setUp()
        import build_installer
        self.B = build_installer

    def test_make_zip_next_to_installer(self):
        installer = self.dir / "ToDoro-Setup-9.9.exe"
        installer.write_bytes(INSTALLER)
        archive = self.B.make_zip(installer)
        self.assertEqual(archive, self.dir / "ToDoro-Setup-9.9.zip")
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(z.namelist(), [installer.name])
            self.assertEqual(z.read(installer.name), INSTALLER)
        self.assertTrue(archive.read_bytes().startswith(b"PK"))

    def test_make_zip_overwrites_old_archive(self):
        installer = self.dir / "ToDoro-Setup-9.9.exe"
        installer.write_bytes(INSTALLER)
        (self.dir / "ToDoro-Setup-9.9.zip").write_bytes(b"old garbage")
        with zipfile.ZipFile(self.B.make_zip(installer)) as z:
            self.assertEqual(z.read(installer.name), INSTALLER)

    def test_zip_from_make_zip_installs_via_download(self):
        """Архив, собранный make_zip, программа умеет распаковать при скачивании."""
        installer = self.dir / EXE_NAME
        installer.write_bytes(INSTALLER)
        data = self.B.make_zip(installer).read_bytes()
        target = self.dir / "dl"
        target.mkdir()
        replies = {EXE_URL: FILTER_PAGE, ZIP_URL: data}
        with mock.patch.object(updater.tempfile, "gettempdir", return_value=str(target)), \
                mock.patch.object(updater, "_urlopen", side_effect=lambda u, h, t: response(replies[u])):
            path = updater.download(release(zip_size=len(data), zip_sha256=sha(data)))
        self.assertEqual(path.read_bytes(), INSTALLER)

    def test_main_builds_zip(self):
        """Сборка (PyInstaller и Inno Setup подменены) кладёт рядом с установщиком .zip."""
        dist = self.dir / "dist"
        dist.mkdir()
        (dist / "ToDoro-Setup-9.9.exe").write_bytes(INSTALLER)
        with mock.patch.object(self.B, "ROOT", self.dir), \
                mock.patch.object(self.B, "BUILD", self.dir / "build"), \
                mock.patch.object(self.B, "app_version", return_value="9.9"), \
                mock.patch.object(self.B, "find_iscc", return_value=Path("ISCC.exe")), \
                mock.patch.object(self.B.subprocess, "run") as run, \
                mock.patch("builtins.print"):
            self.B.main()
        self.assertEqual(run.call_count, 2)
        self.assertTrue((dist / "ToDoro-Setup-9.9.zip").exists(),
                        "build_installer.main() не вызывает make_zip — архива в dist нет")


if __name__ == "__main__":
    unittest.main()
