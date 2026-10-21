"""Собирает установщик ToDoro: dist/ToDoro-Setup-<версия>.exe и тот же установщик в архиве
dist/ToDoro-Setup-<версия>.zip (в некоторых корпоративных сетях .exe скачать нельзя, а .zip — можно)

1. PyInstaller делает папку build/dist/ToDoro с ToDoro.exe — внутри уже есть Python,
   поэтому на другом компьютере ничего дополнительно ставить не нужно.
2. Inno Setup (ISCC.exe) упаковывает эту папку в один установщик.

Запуск из папки проекта:  python tools/build_installer.py
Нужны: pip install pyinstaller pywin32 segno "pillow>=13"  и  Inno Setup 6 (https://jrsoftware.org/isdl.php).
"""
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"


def app_version():
    text = (ROOT / "todoro.py").read_text(encoding="utf-8")
    return re.search(r'^APP_VERSION = "([^"]+)"', text, re.M).group(1)


def version_info(version):
    """Описание файла ToDoro.exe (Свойства → Подробно). FileDescription Windows показывает
    как название программы — например, в списке значков в трее, — иначе там «ToDoro.exe»."""
    numbers = tuple((list(map(int, version.split("."))) + [0, 0, 0, 0])[:4])
    fields = dict(CompanyName="Machinist", FileDescription="ToDoro", FileVersion=version,
                  InternalName="ToDoro", LegalCopyright="© 2026 Machinist",
                  OriginalFilename="ToDoro.exe", ProductName="ToDoro", ProductVersion=version)
    strings = ", ".join(f"StringStruct({key!r}, {value!r})" for key, value in fields.items())
    return (f"VSVersionInfo(ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f, "
            "flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), "
            f"kids=[StringFileInfo([StringTable('041904B0', [{strings}])]), "
            "VarFileInfo([VarStruct('Translation', [1049, 1200])])])\n")


def find_iscc():
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles(x86)", ""),
                 os.environ.get("ProgramFiles", "")):
        for folder in ("Programs/Inno Setup 6", "Inno Setup 6"):
            path = Path(base) / folder / "ISCC.exe"
            if base and path.exists():
                return path
    sys.exit("Не найден Inno Setup 6 (ISCC.exe). Установите его: https://jrsoftware.org/isdl.php")


def make_zip(installer):
    """Кладёт установщик в архив рядом с ним: ToDoro-Setup-<версия>.zip."""
    archive = installer.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(installer, installer.name)
    return archive


MIN_PILLOW = (13, 0)  # в старых версиях Pillow — известные уязвимости (pip-audit, 21.10.2026)


def check_pillow():
    """Pillow попадает в ToDoro.exe и разбирает картинки, приложенные к задачам (в общем списке —
    от любого участника), поэтому со старой версией не собираем."""
    try:
        import PIL
    except ImportError:
        sys.exit('Не установлен Pillow: python -m pip install --user "pillow>=13"')
    if tuple(int(n) for n in re.findall(r"\d+", PIL.__version__)[:2]) < MIN_PILLOW:
        sys.exit(f"Pillow {PIL.__version__} устарел (нужна {'.'.join(map(str, MIN_PILLOW))} или новее): "
                 'python -m pip install --user --upgrade "pillow>=13"')


def main():
    check_pillow()
    version = app_version()
    print(f"== ToDoro {version}: собираю ToDoro.exe ==")
    BUILD.mkdir(exist_ok=True)
    version_file = BUILD / "version_info.txt"
    version_file.write_text(version_info(version), encoding="utf-8")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "ToDoro", "--icon", str(ROOT / "icon.ico"),
        "--version-file", str(version_file),
        "--add-data", f"{ROOT / 'images'};images",
        "--add-data", f"{ROOT / 'icon.ico'};.",
        "--add-data", f"{ROOT / 'LICENSE'};.",
        "--add-data", f"{ROOT / 'RELEASE_NOTES.md'};.",  # окно «Что нового»
        "--distpath", str(BUILD / "dist"), "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
        str(ROOT / "todoro.py"),
    ], check=True)

    print("== собираю установщик ==")
    subprocess.run([str(find_iscc()), f"/DAppVersion={version}",
                    str(ROOT / "installer" / "ToDoro.iss")], check=True)
    installer = ROOT / "dist" / f"ToDoro-Setup-{version}.exe"
    archive = make_zip(installer)
    print(f"\nГотово: {installer}\n        {archive}")


if __name__ == "__main__":
    main()
