"""Снимки экранов приложения для Android — без телефона и эмулятора.

Поднимает сервер ToDoro для телефона (phone.py) на временных данных с примерами задач
(общий список «Команда», как на скриншотах окна) и запускает в android/ тест ScreenshotTest:
Robolectric выполняет приложение прямо в Java и снимает экраны.
Снимки — в android/app/build/screens/; для README уменьшенные копии главного экрана,
карточки задачи и тёмной темы кладутся в docs/screenshots/android-*.png.
Данные пользователя не трогаются.

Запуск из папки проекта:  python tools/android_screenshots.py
"""
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import db  # noqa: E402
import phone  # noqa: E402
import team  # noqa: E402
from examples import make_examples  # noqa: E402

ANDROID = ROOT / "android"
TOOLS = Path(r"D:\Claude\android-tools")
PORT = 47899
ME = "Андрей"
TEAM = ["Мария", "Олег", "Светлана"]
PEOPLE = {  # кто создал и кому поручено — как в make_screenshots.py
    "Оплатить интернет": ("Мария", ME),
    "Сдать квартальный отчёт": (ME, ME),
    "Подготовить презентацию для клиента": ("Олег", "Мария"),
    "Продлить страховку автомобиля": (ME, "Олег"),
    "Записаться к стоматологу": ("Светлана", None),
    "Ответить на письмо от бухгалтерии": ("Мария", "Светлана"),
    "Купить продукты на неделю": (ME, ME),
    "Позвонить маме": (ME, ME),
    "Забрать посылку на почте": ("Мария", "Олег"),
}


def prepare(work):
    """Временные данные: личный список с примерами и общий «Команда» — его телефон и откроет."""
    prefs_path = work / "todoro.db"
    db.LISTS_DIR = work / "lists"
    prefs = db.connect(prefs_path)
    db.add_examples(prefs, make_examples())
    share = team.Team(work / "share")
    for name in [ME] + TEAM:
        share.touch_member(name)
    item = share.add_list("Команда", ME)
    shared = db.connect(share.path(item))
    db.add_examples(shared, make_examples())
    with shared:
        for title, (author, assignee) in PEOPLE.items():
            shared.execute("UPDATE tasks SET created_by = ?, assignee = ?, updated_by = ? WHERE title = ?",
                           (author, assignee, author, title))
    shared.close()
    share.close()
    for key, value in (("shared_folder", str(work / "share")), ("user_name", ME)):
        db.set_setting(prefs, key, value)
    token = phone.new_token(prefs)
    prefs.close()
    return prefs_path, token, item["id"]


# снимок экрана телефона -> картинка для README
README_SHOTS = {"1-main": "android-list.png", "2-card": "android-card.png", "4-dark": "android-dark.png",
               "6-menu": "android-theme.png"}


def copy_for_readme(screens):
    from PIL import Image
    out = ROOT / "docs" / "screenshots"
    for source, name in README_SHOTS.items():
        image = Image.open(screens / f"{source}.png").convert("RGB")
        width = 420
        image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
        image.save(out / name, optimize=True)
        print("saved", out / name)


def main():
    work = Path(tempfile.mkdtemp(prefix="todoro-android-shots-"))
    try:
        prefs_path, token, list_id = prepare(work)
        server = phone.Server(PORT, token, prefs_path)
        threading.Thread(target=server.serve, daemon=True).start()
        env = dict(os.environ)
        env.setdefault("JAVA_HOME", str(sorted(TOOLS.glob("jdk-*"))[-1]))
        env.setdefault("GRADLE_USER_HOME", str(TOOLS / "gradle-home"))
        screens = ANDROID / "app" / "build" / "screens"
        shutil.rmtree(screens, ignore_errors=True)
        result = subprocess.run(
            [str(ANDROID / "gradlew.bat"), "testDebugUnitTest", "--tests", "*ScreenshotTest*",
             "--console=plain", "--rerun", f"-Dtodoro.server=http://127.0.0.1:{PORT},{token}",
             f"-Dtodoro.list={list_id}"],
            cwd=ANDROID, env=env)
        server.shutdown()
        for shot in sorted(screens.glob("*.png")):
            print(shot)
        if result.returncode == 0:
            copy_for_readme(screens)
        sys.exit(result.returncode)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
