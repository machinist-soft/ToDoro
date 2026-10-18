"""Проверки tools/build_apk.py без сборки: номер версии из gradle-файла и ToDoro-android.json.

Сборка Gradle здесь не запускается — только чтение версии и запись файла во временную папку.
Запуск из папки проекта:  python -m unittest discover tests
"""
import json
import shutil
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
