"""Проверки tools/build_apk.py без сборки: номер версии из gradle-файла и ToDoro-android.json.

Сборка Gradle здесь не запускается — только чтение версии и запись файла во временную папку.
Запуск из папки проекта:  python -m unittest discover tests
"""
import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_apk  # noqa: E402

GRADLE = """android {
    defaultConfig {
        applicationId = "com.machinist.todoro"
        minSdk = 26
        targetSdk = 35
        versionCode = 12
        versionName = "0.12.1"
    }
}
"""


class BuildApkVersionTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-apk-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_read_version_from_gradle_file(self):
        gradle = self.dir / "build.gradle.kts"
        gradle.write_text(GRADLE, encoding="utf-8")
        self.assertEqual(build_apk.read_version(gradle), (12, "0.12.1"))

    def test_read_version_accepts_str_path(self):
        gradle = self.dir / "build.gradle.kts"
        gradle.write_text(GRADLE, encoding="utf-8")
        code, version = build_apk.read_version(str(gradle))
        self.assertIsInstance(code, int)
        self.assertEqual((code, version), (12, "0.12.1"))

    def test_read_version_of_real_project(self):
        """Настоящий android/app/build.gradle.kts читается (только чтение)."""
        code, version = build_apk.read_version()
        self.assertGreater(code, 0)
        self.assertTrue(version)

    def test_read_version_without_code_fails_loudly(self):
        """Нет versionCode — сборка должна остановиться, а не записать мусор."""
        gradle = self.dir / "build.gradle.kts"
        gradle.write_text('versionName = "1.0"\n', encoding="utf-8")
        with self.assertRaises(AttributeError):
            build_apk.read_version(gradle)

    def test_write_version_file(self):
        path = build_apk.write_version_file(self.dir, 12, "0.12.1")
        self.assertEqual(path, self.dir / "ToDoro-android.json")
        self.assertEqual(path.name, build_apk.VERSION_FILE)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data, {"versionCode": 12, "versionName": "0.12.1"})
        self.assertIsInstance(data["versionCode"], int)  # телефон ждёт число, не строку

    def test_write_version_file_overwrites_old(self):
        build_apk.write_version_file(self.dir, 7, "0.7")
        path = build_apk.write_version_file(str(self.dir), 8, "0.8")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                         {"versionCode": 8, "versionName": "0.8"})
        self.assertEqual([p.name for p in self.dir.iterdir()], ["ToDoro-android.json"])

    def test_version_file_name_matches_phone(self):
        """Имя файла совпадает с Updates.VERSION_FILE в приложении для телефона."""
        kotlin = (ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "machinist" / "todoro"
                  / "Updates.kt").read_text(encoding="utf-8")
        self.assertIn(f'const val VERSION_FILE = "{build_apk.VERSION_FILE}"', kotlin)

    def test_round_trip(self):
        gradle = self.dir / "build.gradle.kts"
        gradle.write_text(GRADLE, encoding="utf-8")
        out = self.dir / "dist"
        out.mkdir()
        path = build_apk.write_version_file(out, *build_apk.read_version(gradle))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                         {"versionCode": 12, "versionName": "0.12.1"})


class SigningProblemTests(unittest.TestCase):
    """signing_problem и остановка main() до Gradle — только на временных файлах
    (настоящие android/local.properties и ключ не читаются, Gradle не запускается)."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-sign-"))
        self.store = self.dir / "release.jks"
        self.store.write_bytes(b"key")
        self.local = self.dir / "local.properties"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    @staticmethod
    def escape(path):
        r"""Путь, как его пишет Android Studio: D\:\\keys\\x.properties."""
        return str(path).replace("\\", "\\\\").replace(":", "\\:")

    def write(self, signing_text, signing_name="signing.properties"):
        """signing.properties с текстом signing_text (None — файла нет) и local.properties,
        где на него ссылается signing.file (с пробелами вокруг «=» и в конце строки)."""
        signing = self.dir / signing_name
        if signing_text is not None:
            signing.write_text(signing_text, encoding="utf-8")
        self.local.write_text("sdk.dir=C\\:\\\\sdk\n"
                              f"signing.file = {self.escape(signing)}  \n", encoding="utf-8")
        return signing

    def good(self, store=None):
        store = self.escape(store or self.store)
        return f"storeFile={store}\nstorePassword=secret\nkeyAlias=todoro\nkeyPassword=secret\n"

    def test_all_in_place(self):
        self.write(self.good())
        self.assertIsNone(build_apk.signing_problem(self.local))
        self.assertIsNone(build_apk.signing_problem(str(self.local)))

    def test_forward_slashes_and_colon_escape(self):
        r"""Как в настоящем local.properties: D\:/папка/файл."""
        signing = self.dir / "signing.properties"
        signing.write_text(self.good(), encoding="utf-8")
        line = str(signing).replace("\\", "/").replace(":", "\\:")
        self.local.write_text(f"signing.file={line}\n", encoding="utf-8")
        self.assertIsNone(build_apk.signing_problem(self.local))

    def test_path_with_spaces_and_cyrillic(self):
        folder = self.dir / "ключи и пароли"
        folder.mkdir()
        store = folder / "мой ключ.jks"
        store.write_bytes(b"k")
        self.write(self.good(store), signing_name="ключи и пароли/подпись.properties")
        self.assertIsNone(build_apk.signing_problem(self.local))

    def test_no_local_properties(self):
        problem = build_apk.signing_problem(self.dir / "нет.properties")
        self.assertIn("signing.file", problem)

    def test_empty_local_properties(self):
        self.local.write_text("", encoding="utf-8")
        self.assertIn("не указан signing.file", build_apk.signing_problem(self.local))

    def test_signing_file_commented_out(self):
        self.local.write_text(f"#signing.file={self.escape(self.dir / 'x')}\n", encoding="utf-8")
        self.assertIn("не указан signing.file", build_apk.signing_problem(self.local))

    def test_signing_file_missing(self):
        signing = self.write(None)
        problem = build_apk.signing_problem(self.local)
        self.assertIn("Нет файла с ключом подписи", problem)
        self.assertIn(str(signing), problem)  # путь — без экранирования, понятный человеку

    def test_missing_keys_listed(self):
        self.write(f"storeFile={self.escape(self.store)}\nkeyAlias=\nkeyPassword=   \n")
        problem = build_apk.signing_problem(self.local)
        self.assertIn("не заполнено", problem)
        for key in ("storePassword", "keyAlias", "keyPassword"):
            self.assertIn(key, problem)
        self.assertNotIn("storeFile", problem)

    def test_empty_value_in_middle(self):
        """Пустой keyAlias посреди файла — не заполнено (а не «значение» со следующей строки)."""
        self.write(f"storeFile={self.escape(self.store)}\nstorePassword=secret\nkeyAlias=\n"
                   "keyPassword=secret\n")
        problem = build_apk.signing_problem(self.local)
        self.assertIsNotNone(problem)
        self.assertIn("keyAlias", problem)

    def test_empty_store_file_first(self):
        """Пустой storeFile в первой строке: сообщение про storeFile, и пароль со следующей
        строки в нём не показывается."""
        self.write("storeFile=\nstorePassword=secret\nkeyAlias=todoro\nkeyPassword=secret\n")
        problem = build_apk.signing_problem(self.local)
        self.assertIsNotNone(problem)
        self.assertIn("storeFile", problem)
        self.assertNotIn("secret", problem)

    def test_empty_signing_file(self):
        self.write("")
        problem = build_apk.signing_problem(self.local)
        for key in ("storeFile", "storePassword", "keyAlias", "keyPassword"):
            self.assertIn(key, problem)

    def test_store_file_missing(self):
        self.write(self.good(self.dir / "нет.jks"))
        problem = build_apk.signing_problem(self.local)
        self.assertIn("storeFile", problem)
        self.assertIn(str(self.dir / "нет.jks"), problem)

    def test_password_not_in_message(self):
        """Пароль в текст ошибки не попадает."""
        self.write(self.good(self.dir / "нет.jks"))
        self.assertNotIn("secret", build_apk.signing_problem(self.local))

    def test_main_stops_before_gradle(self):
        with mock.patch.object(build_apk, "signing_problem", return_value="нет ключа"),                 mock.patch.object(build_apk.subprocess, "run") as run,                 mock.patch.object(build_apk.shutil, "copy2") as copy:
            with self.assertRaises(SystemExit) as stop:
                build_apk.main()
        run.assert_not_called()
        copy.assert_not_called()
        self.assertIn("нет ключа", str(stop.exception.code))
        self.assertIn("подписать", str(stop.exception.code))

    def test_main_goes_on_when_signing_ok(self):
        """Ключ на месте — дело доходит до Gradle (здесь подменён и «падает»)."""
        with mock.patch.object(build_apk, "signing_problem", return_value=None),                 mock.patch.dict(build_apk.os.environ, {"JAVA_HOME": str(self.dir)}),                 mock.patch.object(build_apk.subprocess, "run", side_effect=RuntimeError("стоп")) as run:
            with self.assertRaises(RuntimeError):
                build_apk.main()
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
