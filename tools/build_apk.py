"""Собирает приложение ToDoro для Android: dist/ToDoro-<версия>.apk

Нужны JDK 17+ и Android SDK — путь к SDK берётся из android/local.properties (sdk.dir),
JDK — из переменной JAVA_HOME, а если её нет — из папки TOOLS (там они стоят на компьютере
автора). Запуск из папки проекта:  python tools/build_apk.py
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANDROID = ROOT / "android"
TOOLS = Path(r"D:\Claude\android-tools")


def main():
    env = dict(os.environ)
    if not env.get("JAVA_HOME"):
        jdks = sorted(TOOLS.glob("jdk-*"))
        if not jdks:
            sys.exit("Не найден JDK: укажите JAVA_HOME")
        env["JAVA_HOME"] = str(jdks[-1])
    env.setdefault("GRADLE_USER_HOME", str(TOOLS / "gradle-home"))
    subprocess.run([str(ANDROID / "gradlew.bat"), "assembleRelease", "--console=plain", "-q"],
                   cwd=ANDROID, env=env, check=True)
    gradle = (ANDROID / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    version = re.search(r'versionName = "([^"]+)"', gradle).group(1)
    out = ROOT / "dist" / f"ToDoro-{version}.apk"
    out.parent.mkdir(exist_ok=True)
    shutil.copy2(ANDROID / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk", out)
    print(out)


if __name__ == "__main__":
    main()
