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


class _WinInetResponse:
    """Ответ сервера, полученный через WinINet — сетевую часть самой Windows.
    Она берёт прокси и сертификаты из настроек Windows, как браузер, поэтому работает в
    корпоративных сетях, где прямой запрос Python не проходит (прокси со сценарием настройки,
    вход в прокси под учётной записью Windows, проверка HTTPS-трафика сертификатом компании)."""
    STATUS_CODE, CONTENT_LENGTH, AS_NUMBER = 19, 5, 0x20000000

    def __init__(self, url, headers, timeout):
        import ctypes
        from ctypes import wintypes
        self._ctypes = ctypes
        dll = self._dll = ctypes.WinDLL("wininet", use_last_error=True)
        dll.InternetOpenW.restype = dll.InternetOpenUrlW.restype = ctypes.c_void_p
        dll.InternetOpenW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPCWSTR,
                                      wintypes.LPCWSTR, wintypes.DWORD]
        dll.InternetOpenUrlW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                         wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        dll.InternetSetOptionW.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                           wintypes.DWORD]
        dll.InternetReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.POINTER(wintypes.DWORD)]
        dll.HttpQueryInfoW.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                       ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        dll.InternetCloseHandle.argtypes = [ctypes.c_void_p]
        self._session = self._request = None
        # 0 = «как настроено в Windows» (прокси, сценарий автонастройки)
        self._session = dll.InternetOpenW(headers.get("User-Agent", USER_AGENT), 0, None, None, 0)
        if not self._session:
            self._fail("InternetOpen")
        ms = wintypes.DWORD(int(timeout * 1000))
        for option in (2, 5, 6):  # тайм-ауты соединения, отправки и получения
            dll.InternetSetOptionW(self._session, option, ctypes.byref(ms), ctypes.sizeof(ms))
        extra = "".join(f"{k}: {v}\r\n" for k, v in headers.items() if k != "User-Agent")
        # без кэша, без окон, без cookie
        flags = 0x80000000 | 0x04000000 | 0x00000200 | 0x00080000
        self._request = dll.InternetOpenUrlW(self._session, url, extra or None,
                                             0xFFFFFFFF if extra else 0, flags, None)
        if not self._request:
            self._fail("InternetOpenUrl")
        status = self._number(self.STATUS_CODE)
        if status and status >= 400:
            self.close()
            raise OSError(f"сервер ответил HTTP {status}")
        length = self._number(self.CONTENT_LENGTH)
        self.headers = {"Content-Length": str(length)} if length else {}

    def _fail(self, what):
        code = self._ctypes.get_last_error()
        self.close()
        raise OSError(f"{what}: ошибка WinINet {code}")

    def _number(self, query):
        from ctypes import wintypes
        value, size = wintypes.DWORD(0), wintypes.DWORD(4)
        ok = self._dll.HttpQueryInfoW(self._request, query | self.AS_NUMBER,
                                      self._ctypes.byref(value), self._ctypes.byref(size), None)
        return value.value if ok else None

    def read(self, size=-1):
        from ctypes import wintypes
        if size is None or size < 0:
            chunks = []
            while chunk := self.read(256 * 1024):
                chunks.append(chunk)
            return b"".join(chunks)
        buffer = self._ctypes.create_string_buffer(size)
        got = wintypes.DWORD(0)
        if not self._dll.InternetReadFile(self._request, buffer, size, self._ctypes.byref(got)):
            self._fail("InternetReadFile")
        return buffer.raw[:got.value]

    def close(self):
        for handle in (self._request, self._session):
            if handle:
                self._dll.InternetCloseHandle(handle)
        self._session = self._request = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _urlopen(url, headers, timeout):
    """Открывает адрес напрямую, а если не вышло (на Windows) — через сетевую часть Windows."""
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)
    except OSError as direct_error:
        if sys.platform != "win32":
            raise
        try:
            return _WinInetResponse(url, headers, timeout)
        except OSError as windows_error:
            raise OSError(f"{_reason(direct_error)}; через Windows: {windows_error}") from direct_error


def _reason(error):
    """Короткое техническое описание сетевой ошибки — для строки «Подробности»."""
    reason = getattr(error, "reason", None) or error
    text = str(reason) or type(reason).__name__
    return text if len(text) <= 300 else text[:300] + "…"


def fetch_latest(timeout=10):
    """Последний выпуск на GitHub: dict(version, notes, url, asset_url, asset_name, size, sha256).
    asset_* — None, если к выпуску не приложен установщик."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    try:
        with _urlopen(LATEST_URL, headers, timeout) as response:
            data = json.loads(response.read())
    except OSError as error:
        raise UpdateError("Не удалось связаться с GitHub. Проверьте подключение к интернету.\n"
                          f"Подробности: {_reason(error)}") from error
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
    sha = hashlib.sha256()
    received = 0
    try:
        with _urlopen(release["asset_url"], {"User-Agent": USER_AGENT}, timeout) as response, \
                open(path, "wb") as f:
            total = int(response.headers.get("Content-Length") or release.get("size") or 0)
            while chunk := response.read(256 * 1024):
                f.write(chunk)
                sha.update(chunk)
                received += len(chunk)
                if on_progress:
                    on_progress(received, total)
    except OSError as error:
        raise UpdateError("Не удалось скачать обновление. Проверьте подключение к интернету.\n"
                          f"Подробности: {_reason(error)}") from error
    if release.get("size") and received != release["size"]:
        path.unlink(missing_ok=True)
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
