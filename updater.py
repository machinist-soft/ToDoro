"""Проверка обновлений: спрашивает у GitHub последний выпуск и скачивает его установщик.

Никаких данных пользователя никуда не отправляется — только запрос «какая версия последняя».
Установщик проверяется по контрольной сумме SHA-256, которую GitHub указывает для файла выпуска.
Если установщик (.exe) скачать не дали — например, его не пропускает фильтр корпоративной сети, —
скачивается тот же установщик в архиве ToDoro-Setup-<версия>.zip, который тоже приложен к выпуску.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

REPO = "machinist-soft/ToDoro"
PROJECT_URL = f"https://github.com/{REPO}"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
RELEASES_LIST = f"https://github.com/{REPO}/releases"  # все выпуски со списками изменений
# Приложение для Android: к каждому выпуску прикладывается под этим именем (см. навык release)
APK_NAME = "ToDoro.apk"
APK_URL = f"https://github.com/{REPO}/releases/latest/download/{APK_NAME}"
ISSUES_PAGE = f"https://github.com/{REPO}/issues"  # сообщения об ошибках и идеи
# Адреса, которые администратор сети должен разрешить, чтобы обновление скачивалось
DOWNLOAD_HOSTS = ("github.com", "api.github.com", "release-assets.githubusercontent.com",
                  "objects.githubusercontent.com")


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


def _sha256(asset):
    digest = (asset or {}).get("digest") or ""
    return digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None


def fetch_latest(timeout=10):
    """Последний выпуск на GitHub: dict(version, notes, url, asset_url, asset_name, size, sha256,
    zip_url, zip_name, zip_size, zip_sha256). asset_* — None, если к выпуску не приложен
    установщик, zip_* — если не приложен его архив (в старых выпусках его нет)."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    try:
        with _urlopen(LATEST_URL, headers, timeout) as response:
            data = json.loads(response.read())
    except OSError as error:
        raise UpdateError("Не удалось связаться с GitHub. Проверьте подключение к интернету.\n"
                          f"Подробности: {_reason(error)}") from error
    except ValueError as error:
        raise UpdateError("GitHub ответил что-то непонятное. Попробуйте позже.") from error
    assets = data.get("assets", [])
    asset = next((a for a in assets if re.match(r"ToDoro-Setup-.*\.exe$", a.get("name", ""))), None)
    archive = next((a for a in assets if re.match(r"ToDoro-Setup-.*\.zip$", a.get("name", ""))), None)
    return dict(
        version=data.get("tag_name", "").lstrip("v"),
        notes=(data.get("body") or "").strip(),
        url=data.get("html_url") or RELEASES_PAGE,
        asset_url=asset and asset.get("browser_download_url"),
        asset_name=asset and asset.get("name"),
        size=asset and asset.get("size"),
        sha256=_sha256(asset),
        zip_url=archive and archive.get("browser_download_url"),
        zip_name=archive and archive.get("name"),
        zip_size=archive and archive.get("size"),
        zip_sha256=_sha256(archive),
    )


def check_release(release, prefix="asset"):
    """Установщик скачиваем только по https с github.com и только если GitHub сообщил его
    контрольную сумму: без неё скачанный файл нечем проверить, а он сразу запустится.
    prefix="zip" — то же для архива с установщиком (поля zip_url и zip_sha256)."""
    url = urllib.parse.urlsplit(release.get(f"{prefix}_url") or "")
    if url.scheme != "https" or url.hostname != "github.com":
        raise UpdateError("Адрес обновления — не на GitHub, поэтому обновление не скачано.\n"
                          f"Скачайте установщик со страницы выпуска: {RELEASES_PAGE}")
    if not release.get("sha256" if prefix == "asset" else "zip_sha256"):
        raise UpdateError("GitHub не сообщил контрольную сумму установщика — без проверки "
                          "ставить обновление нельзя.\n"
                          f"Скачайте установщик со страницы выпуска: {RELEASES_PAGE}")


class DownloadError(UpdateError):
    """Файл выпуска не скачался: сеть оборвала соединение, сервер ответил ошибкой и т. п.
    details — техническая причина для строки «Подробности»."""

    def __init__(self, message, details=""):
        super().__init__(message)
        self.details = details


class BlockedError(DownloadError):
    """Вместо файла пришло что-то другое — обычно страница фильтра сети «загрузка запрещена»."""


def blocked_message(details=""):
    """Что делать, если обновление не дали скачать (ни как .exe, ни как .zip)."""
    text = ("Не удалось скачать обновление. Если интернет работает — похоже, его не пропускает "
            "фильтр сети (например, корпоративный FortiGate).\n"
            f"Скачайте установщик в другой сети со страницы выпуска: {RELEASES_PAGE}\n"
            "или попросите администратора разрешить адреса: " + ", ".join(DOWNLOAD_HOSTS) + ".")
    return text + (f"\nПодробности: {details}" if details else "")


def _fetch(url, path, size, sha256, magic, on_progress, timeout):
    """Скачивает один файл выпуска в path и сверяет размер и контрольную сумму.
    magic — первые байты настоящего файла («MZ» у .exe, «PK» у .zip): если начало другое,
    вместо файла пришла страница (обычно — фильтр сети), и дальше качать бессмысленно."""
    sha = hashlib.sha256()
    received = 0
    head = b""  # первые байты файла (первая порция может оказаться короче magic)
    try:
        with _urlopen(url, {"User-Agent": USER_AGENT}, timeout) as response, open(path, "wb") as f:
            total = int(response.headers.get("Content-Length") or size or 0)
            while chunk := response.read(256 * 1024):
                head = (head + chunk[:len(magic)])[:len(magic)]
                if not magic.startswith(head):
                    reason = "вместо файла пришла другая страница (обычно — от фильтра сети)"
                    raise BlockedError(blocked_message(reason), reason)
                f.write(chunk)
                sha.update(chunk)
                received += len(chunk)
                if on_progress:
                    on_progress(received, total)
    except BlockedError:
        path.unlink(missing_ok=True)
        raise
    except OSError as error:
        path.unlink(missing_ok=True)
        raise DownloadError("Не удалось скачать обновление. Проверьте подключение к интернету.\n"
                            f"Подробности: {_reason(error)}", _reason(error)) from error
    if size and received != size:
        path.unlink(missing_ok=True)
        raise UpdateError("Обновление скачалось не полностью. Попробуйте ещё раз.")
    if sha.hexdigest() != sha256:
        path.unlink(missing_ok=True)
        raise UpdateError("Скачанный файл повреждён (не совпала контрольная сумма). Попробуйте ещё раз.")


def _extract_installer(archive, folder, name, sha256):
    """Достаёт установщик name из скачанного архива и сверяет его собственную контрольную сумму
    (ту же, что у .exe в выпуске); сам архив после этого удаляется."""
    target = folder / name
    sha = hashlib.sha256()
    try:
        with zipfile.ZipFile(archive) as z, z.open(name) as source, open(target, "wb") as f:
            while chunk := source.read(256 * 1024):
                f.write(chunk)
                sha.update(chunk)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        target.unlink(missing_ok=True)
        raise UpdateError("Не удалось распаковать скачанный архив с обновлением. "
                          f"Попробуйте ещё раз.\nПодробности: {_reason(error)}") from error
    finally:
        archive.unlink(missing_ok=True)
    if sha.hexdigest() != sha256:
        target.unlink(missing_ok=True)
        raise UpdateError("Установщик в архиве не совпал с установщиком выпуска (контрольная сумма). "
                          f"Скачайте его со страницы выпуска: {RELEASES_PAGE}")
    return target


def download(release, on_progress=None, timeout=30):
    """Скачивает установщик во временную папку и проверяет его. Возвращает путь к файлу.
    Если .exe скачать не вышло, а к выпуску приложен архив .zip, — скачивает архив (тоже с
    проверкой контрольной суммы) и достаёт установщик из него.
    on_progress(получено_байт, всего_байт) вызывается по ходу скачивания (из этого же потока)."""
    if not release.get("asset_url"):
        raise UpdateError("К выпуску не приложен установщик.")
    check_release(release)
    folder = Path(tempfile.gettempdir()) / "ToDoro-update"
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(release["asset_name"]).name
    path = folder / name
    remove_old_downloads(folder, keep=path)
    try:
        _fetch(release["asset_url"], path, release.get("size"), release["sha256"], b"MZ",
               on_progress, timeout)
        return path
    except UpdateError as error:
        if not release.get("zip_url"):
            raise
        exe_error = error
    archive = folder / Path(release.get("zip_name") or "").name
    try:
        check_release(release, "zip")
    except UpdateError as error:
        if isinstance(exe_error, BlockedError):  # про фильтр сети важнее, чем про архив
            raise exe_error from error
        raise
    try:
        _fetch(release["zip_url"], archive, release.get("zip_size"), release["zip_sha256"], b"PK",
               on_progress, timeout)
    except DownloadError as error:
        if isinstance(exe_error, DownloadError):  # не скачалось ни так, ни так
            details = f".exe — {exe_error.details}; .zip — {error.details}"
            raise BlockedError(blocked_message(details), details) from error
        raise
    return _extract_installer(archive, folder, name, release["sha256"])


def remove_old_downloads(folder, keep=None):
    """Удаляет установщики (и их архивы), скачанные раньше: после установки они больше не нужны.
    Занятый файл (установщик ещё работает) пропускаем — уберём в следующий раз."""
    try:
        items = [*Path(folder).glob("*.exe"), *Path(folder).glob("*.zip")]
    except OSError:
        return
    for item in items:
        if item != keep:
            try:
                item.unlink()
            except OSError:
                pass


def can_self_update():
    """Ставить обновление сам может только установленный ToDoro.exe.
    При запуске из исходного кода (python todoro.py) — только ссылка на страницу выпуска."""
    return bool(getattr(sys, "frozen", False))


def run_installer(path):
    """Запускает установщик в режиме «без вопросов, с полоской прогресса».
    Программа после этого должна сразу закрыться; установщик откроет новую версию сам."""
    subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     close_fds=True)
