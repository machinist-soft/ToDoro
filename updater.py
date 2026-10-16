"""Проверка обновлений: спрашивает у GitHub последний выпуск и скачивает его установщик.

Никаких данных пользователя никуда не отправляется — только запрос «какая версия последняя».
Установщик проверяется по контрольной сумме SHA-256, которую GitHub указывает для файла выпуска.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "machinist-soft/ToDoro"
PROJECT_URL = f"https://github.com/{REPO}"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
RELEASES_LIST = f"https://github.com/{REPO}/releases"  # все выпуски со списками изменений
ISSUES_PAGE = f"https://github.com/{REPO}/issues"  # сообщения об ошибках и идеи


def windows_name():
    """«Windows 11 (сборка 22631)» — для формы сообщения об ошибке."""
    try:
        build = sys.getwindowsversion().build
    except AttributeError:  # не Windows
        return ""
    return f"Windows {11 if build >= 22000 else 10} (сборка {build})"


def feedback_url(kind, app_version):
    """Страница GitHub с формой «Сообщить об ошибке» (kind="bug") или «Предложить улучшение»
    (kind="idea"); версия программы и Windows подставляются в форму заранее."""
    template = "bug_report.yml" if kind == "bug" else "feature_request.yml"
    fields = {"template": template, "version": app_version}
    if kind == "bug":
        fields["windows"] = windows_name()
    return f"https://github.com/{REPO}/issues/new?" + urllib.parse.urlencode(fields)
USER_AGENT = "ToDoro-updater"


class UpdateError(Exception):
    """Понятное пользователю описание того, что пошло не так."""


def parse_version(text):
    """'v1.10' -> (1, 10); то, что не похоже на версию, -> ()."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", (text or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def is_newer(latest, current):
    return parse_version(latest) > parse_version(current)


def fetch_latest(timeout=10):
    """Последний выпуск на GitHub: dict(version, notes, url, asset_url, asset_name, size, sha256).
    asset_* — None, если к выпуску не приложен установщик."""
    request = urllib.request.Request(LATEST_URL, headers={
        "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except OSError as error:
        raise UpdateError("Не удалось связаться с GitHub. Проверьте подключение к интернету.") from error
    except ValueError as error:
        raise UpdateError("GitHub ответил что-то непонятное. Попробуйте позже.") from error
    asset = next((a for a in data.get("assets", [])
                  if re.match(r"ToDoro-Setup-.*\.exe$", a.get("name", ""))), None)
    digest = (asset or {}).get("digest") or ""
    return dict(
        version=data.get("tag_name", "").lstrip("v"),
        notes=(data.get("body") or "").strip(),
        url=data.get("html_url") or RELEASES_PAGE,
        asset_url=asset and asset.get("browser_download_url"),
        asset_name=asset and asset.get("name"),
        size=asset and asset.get("size"),
        sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None,
    )


def download(release, on_progress=None, timeout=30):
    """Скачивает установщик во временную папку и проверяет его. Возвращает путь к файлу.
    on_progress(получено_байт, всего_байт) вызывается по ходу скачивания (из этого же потока)."""
    if not release.get("asset_url"):
        raise UpdateError("К выпуску не приложен установщик.")
    folder = Path(tempfile.gettempdir()) / "ToDoro-update"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(release["asset_name"]).name
    request = urllib.request.Request(release["asset_url"], headers={"User-Agent": USER_AGENT})
    sha = hashlib.sha256()
    received = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(path, "wb") as f:
            total = int(response.headers.get("Content-Length") or release.get("size") or 0)
            while chunk := response.read(256 * 1024):
                f.write(chunk)
                sha.update(chunk)
                received += len(chunk)
                if on_progress:
                    on_progress(received, total)
    except OSError as error:
        raise UpdateError("Не удалось скачать обновление. Проверьте подключение к интернету.") from error
    if release.get("size") and received != release["size"]:
        raise UpdateError("Обновление скачалось не полностью. Попробуйте ещё раз.")
    if release.get("sha256") and sha.hexdigest() != release["sha256"]:
        path.unlink(missing_ok=True)
        raise UpdateError("Скачанный файл повреждён (не совпала контрольная сумма). Попробуйте ещё раз.")
    return path


def can_self_update():
    """Ставить обновление сам может только установленный ToDoro.exe.
    При запуске из исходного кода (python todoro.py) — только ссылка на страницу выпуска."""
    return bool(getattr(sys, "frozen", False))


def run_installer(path):
    """Запускает установщик в режиме «без вопросов, с полоской прогресса».
    Программа после этого должна сразу закрыться; установщик откроет новую версию сам."""
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     close_fds=True)
