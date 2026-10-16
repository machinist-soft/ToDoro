"""Собирает установщик ToDoro: dist/ToDoro-Setup-<версия>.exe

1. PyInstaller делает папку build/dist/ToDoro с ToDoro.exe — внутри уже есть Python,
   поэтому на другом компьютере ничего дополнительно ставить не нужно.
2. Inno Setup (ISCC.exe) упаковывает эту папку в один установщик.

Запуск из папки проекта:  python tools/build_installer.py
Нужны: pip install pyinstaller  и  Inno Setup 6 (https://jrsoftware.org/isdl.php).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"


def app_version():
    text = (ROOT / "todoro.py").read_text(encoding="utf-8")
    return re.search(r'^APP_VERSION = "([^"]+)"', text, re.M).group(1)


def find_iscc():
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles(x86)", ""),
                 os.environ.get("ProgramFiles", "")):
        for folder in ("Programs/Inno Setup 6", "Inno Setup 6"):
            path = Path(base) / folder / "ISCC.exe"
            if base and path.exists():
                return path
    sys.exit("Не найден Inno Setup 6 (ISCC.exe). Установите его: https://jrsoftware.org/isdl.php")


def main():
    version = app_version()
    print(f"== ToDoro {version}: собираю ToDoro.exe ==")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "ToDoro", "--icon", str(ROOT / "icon.ico"),
        "--add-data", f"{ROOT / 'images'};images",
        "--add-data", f"{ROOT / 'icon.ico'};.",
        "--add-data", f"{ROOT / 'LICENSE'};.",
        "--distpath", str(BUILD / "dist"), "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
        str(ROOT / "todoro.py"),
    ], check=True)

    print("== собираю установщик ==")
    subprocess.run([str(find_iscc()), f"/DAppVersion={version}",
                    str(ROOT / "installer" / "ToDoro.iss")], check=True)
    print(f"\nГотово: {ROOT / 'dist' / f'ToDoro-Setup-{version}.exe'}")


if __name__ == "__main__":
    main()
