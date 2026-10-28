"""Собирает приложение ToDoro для Android: dist/ToDoro-<версия>.apk и dist/ToDoro-android.json

ToDoro-android.json — номер версии приложения; прикладывается к выпуску рядом с ToDoro.apk,
по нему телефон узнаёт, что вышла новая версия (☰ Меню → О приложении).

Нужны JDK 17+ и Android SDK — путь к SDK берётся из android/local.properties (sdk.dir),
JDK — из переменной JAVA_HOME, а если её нет — из папки TOOLS (там они стоят на компьютере
автора). Запуск из папки проекта:  python tools/build_apk.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANDROID = ROOT / "android"
VERSION_FILE = "ToDoro-android.json"  # то же имя — в Updates.kt (VERSION_FILE)
TOOLS = Path(r"D:\Claude\android-tools")


def property_value(text, key):
    """Значение ключа из файла .properties («ключ=значение» или «ключ: значение»), «» — нет.
    Только в пределах своей строки: пустое значение не «захватывает» следующую строку (а с ней,
    например, пароль). «\\» в .properties экранирует: D\\:\\\\keys\\\\x.properties."""
    found = re.search(rf"^[ \t]*{re.escape(key)}[ \t]*[=:][ \t]*(.*?)[ \t]*$", text, re.MULTILINE)
    return re.sub(r"\\(.)", r"\1", found.group(1)) if found else ""


def signing_problem(local_properties=ANDROID / "local.properties"):
    """Почему выпуск подписать нечем (или None, если всё на месте). Без ключа Gradle молча
    подпишет APK отладочным ключом — а такой APK не встанет поверх установленного приложения."""
    path = Path(local_properties)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    signing = property_value(text, "signing.file")
    if not signing:
        return f"В {path} не указан signing.file — путь к signing.properties (см. android/README.md)"
    signing = Path(signing)
    if not signing.exists():
        return f"Нет файла с ключом подписи: {signing}"
    props = signing.read_text(encoding="utf-8")
    missing = [key for key in ("storeFile", "storePassword", "keyAlias", "keyPassword")
               if not property_value(props, key)]
    if missing:
        return f"В {signing} не заполнено: {', '.join(missing)}"
    store = Path(property_value(props, "storeFile"))
    if not store.exists():
        return f"Нет файла ключа (storeFile): {store}"
    return None


def main():
    problem = signing_problem()
    if problem:
        sys.exit(f"Выпуск не собран: нечем подписать APK.\n{problem}")
    env = dict(os.environ)
    if not env.get("JAVA_HOME"):
        jdks = sorted(TOOLS.glob("jdk-*"))
        if not jdks:
            sys.exit("Не найден JDK: укажите JAVA_HOME")
        env["JAVA_HOME"] = str(jdks[-1])
    env.setdefault("GRADLE_USER_HOME", str(TOOLS / "gradle-home"))
    subprocess.run([str(ANDROID / "gradlew.bat"), "assembleRelease", "--console=plain", "-q"],
                   cwd=ANDROID, env=env, check=True)
    code, version = read_version()
    out = ROOT / "dist" / f"ToDoro-{version}.apk"
    out.parent.mkdir(exist_ok=True)
    shutil.copy2(ANDROID / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk", out)
    print(out)
    print(write_version_file(ROOT / "dist", code, version))


def read_version(gradle_file=ANDROID / "app" / "build.gradle.kts"):
    """(versionCode, versionName) из build.gradle.kts."""
    gradle = Path(gradle_file).read_text(encoding="utf-8")
    code = int(re.search(r"versionCode = (\d+)", gradle).group(1))
    version = re.search(r'versionName = "([^"]+)"', gradle).group(1)
    return code, version


def write_version_file(folder, code, version):
    path = Path(folder) / VERSION_FILE
    path.write_text(json.dumps({"versionCode": code, "versionName": version}), encoding="utf-8")
    return path


if __name__ == "__main__":
    main()
