"""Связь с телефоном: маленький веб-сервер внутри значка ToDoro в трее.

Телефон не открывает файлы списков сам (по сети это медленно, и правки могут потеряться) —
он просит компьютер: «покажи задачи», «отметь выполненной», «добавь задачу». Компьютер
делает это тем же кодом, что и окно ToDoro (db.py, team.py), поэтому версии задач, авторы,
исполнители и общие списки работают как обычно.

Сервер включается, только когда в окне ToDoro выбрали «☰ → Подключить телефон»: тогда в
настройках появляется секретный ключ (phone_token). Ключ передаётся телефону в QR-коде и
нужен в каждом запросе (заголовок «Authorization: Bearer <ключ>»). «Отключить телефон»
стирает ключ — сервер перестаёт слушать сеть.

Запросы (ответы — JSON в UTF-8):
    GET    /                                     — страничка «ToDoro работает» (без ключа)
    GET    /api/v1/hello                         — версия, имя, компьютер
    GET    /api/v1/lists                         — все списки
    GET    /api/v1/sync                          — все списки сразу с задачами (копия для телефона)
    GET    /api/v1/lists/<список>                — колонки, задачи, участники
    POST   /api/v1/lists/<список>/tasks          — новая задача
    GET    /api/v1/lists/<список>/tasks/<номер>  — задача с файлами и комментариями
    PATCH  /api/v1/lists/<список>/tasks/<номер>  — изменить (version — защита от затирания)
    DELETE /api/v1/lists/<список>/tasks/<номер>
    POST   .../tasks/<номер>/comments            — {"text": ...}
    DELETE .../tasks/<номер>/comments/<id>
    POST   .../tasks/<номер>/attachments?name=<имя файла>   — тело запроса — сам файл
    GET    .../tasks/<номер>/attachments/<id>    — скачать файл
    DELETE .../tasks/<номер>/attachments/<id>
"""
import hmac
import json
import mimetypes
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, urlsplit

import db
import team

PORT = 47815
TOKEN_KEY = "phone_token"  # настройка в todoro.db; нет её — связь с телефоном выключена
API = "/api/v1"
APP_VERSION = ""            # версия ToDoro для /hello (задаёт start_in_background)
CHECK_EVERY = 3            # секунд: как часто сервер смотрит, не включили ли/выключили связь
RECONNECT_AFTER = 30       # секунд: не открылась общая папка — пробуем снова не раньше


# ---------- ключ и адреса (для окна «Подключить телефон») ----------

def get_token(prefs):
    return db.get_setting(prefs, TOKEN_KEY) or None


def new_token(prefs):
    """Новый ключ: телефоны со старым ключом больше не подключатся."""
    token = secrets.token_urlsafe(18)
    db.set_setting(prefs, TOKEN_KEY, token)
    return token


def disable(prefs):
    with prefs:
        prefs.execute("DELETE FROM settings WHERE key = ?", (TOKEN_KEY,))


def addresses():
    """IPv4-адреса компьютера в сети; первым — тот, через который компьютер выходит в сеть."""
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.168.1.1", 9))  # UDP «connect» ничего не отправляет — только выбирает адрес
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    result = []
    for ip in found:
        if ip not in result and not ip.startswith(("127.", "169.254.", "0.")):
            result.append(ip)
    return result


def pairing_text(token, hosts, port=PORT):
    """Что зашито в QR-код: адреса компьютера, порт и ключ."""
    return (f"todoro://connect?v=1&hosts={','.join(hosts)}&port={port}&key={quote(token)}"
            f"&name={quote(socket.gethostname())}")


def ping(port=PORT, timeout=1.0):
    """Отвечает ли сервер на этом компьютере (для окна «Подключить телефон»)."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as conn:
            conn.settimeout(timeout)
            conn.sendall(b"GET /ping HTTP/1.0\r\n\r\n")
            return b"ToDoro" in conn.recv(256)
    except OSError:
        return False


# ---------- данные: то же, что делает окно ----------

class ApiError(Exception):
    def __init__(self, status, message, extra=None):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra or {}


TASK_SQL = """
    SELECT id, title, body, done, status_id, urgent, important, due_at, remind_before,
           strftime('%Y-%m-%d %H:%M:%S', created_at, 'localtime'), created_by, assignee,
           updated_by, updated_at, version, done_at, mail_from
    FROM tasks
"""
TASK_FIELDS = ("id", "title", "body", "done", "status_id", "urgent", "important", "due_at",
               "remind_before", "created_at", "author", "assignee", "updated_by", "updated_at",
               "version", "done_at", "mail_from")
BOOL_FIELDS = ("done", "urgent", "important")


def task_dict(row, counts=None):
    task = dict(zip(TASK_FIELDS, row))
    for key in BOOL_FIELDS:
        task[key] = bool(task[key])
    files, comments = (counts or {}).get(task["id"], (0, 0))
    task["files"], task["comments"] = files, comments
    return task


def check_due(value):
    """Срок: «ГГГГ-ММ-ДД ЧЧ:ММ» или null."""
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        raise ApiError(400, "Срок должен быть в виде ГГГГ-ММ-ДД ЧЧ:ММ") from None


def check_minutes(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ApiError(400, "remind_before — число минут (0 или больше) или null")
    return value


def check_title(value):
    if not isinstance(value, str) or not value.strip():
        raise ApiError(400, "Нужен заголовок задачи")
    return value.strip()


class Store:
    """Списки и задачи для телефона. Работает только в потоке сервера."""

    def __init__(self, prefs_path=None):
        self.prefs_path = prefs_path
        self.prefs = db.connect(prefs_path)  # это и есть личный список
        self.conns = {}          # id списка -> соединение
        self.team = None
        self.probe = None
        self.team_retry = 0

    def close(self):
        for conn in self.conns.values():
            if conn is not self.prefs:
                conn.close()
        self.conns.clear()
        if self.team:
            self.team.close()
            self.team = None
        if self.probe:
            self.probe.stop()
            self.probe = None
        self.prefs.close()

    def user(self):
        return db.get_setting(self.prefs, "user_name", "") or os.environ.get("USERNAME", "Я")

    # --- общая папка ---

    def shared_team(self):
        """Общая папка или None (не настроена или нет связи). Без связи к папке не ходим —
        запрос «повис» бы на десятки секунд."""
        folder = db.get_setting(self.prefs, "shared_folder", "").strip()
        if not folder:
            self.drop_team()
            return None
        if self.probe is None or self.probe.folder != folder:
            self.drop_team()
            self.probe = team.Probe(folder)
            deadline = time.monotonic() + team.Probe.HANG + 0.5
            while self.probe.ok is None and time.monotonic() < deadline:
                time.sleep(0.05)
        if not self.probe.online():
            self.drop_team(keep_probe=True)
            return None
        if self.team is None and time.monotonic() >= self.team_retry:
            try:
                self.team = team.Team(folder)
            except (team.TeamError, sqlite3.Error, OSError):
                self.team_retry = time.monotonic() + RECONNECT_AFTER
        return self.team

    def drop_team(self, keep_probe=False):
        for list_id in [i for i in self.conns if i.startswith("t")]:
            conn = self.conns.pop(list_id)
            threading.Thread(target=conn.close, daemon=True).start()  # без связи может «повиснуть»
        if self.team:
            conn, self.team = self.team.conn, None
            threading.Thread(target=conn.close, daemon=True).start()
        if self.probe and not keep_probe:
            self.probe.stop()
            self.probe = None

    def on_error(self, list_item):
        """Ошибка при работе со списком: соединение с общим файлом могло умереть вместе со связью."""
        if list_item and list_item["shared"]:
            self.drop_team(keep_probe=True)

    # --- списки ---

    def lists(self):
        """(списки, общая папка настроена, но недоступна)."""
        items = [dict(item, shared=False) for item in db.list_registry(self.prefs)]
        offline = False
        if db.get_setting(self.prefs, "shared_folder", "").strip():
            group = self.shared_team()
            if group is None:
                offline = True
            else:
                try:
                    items += group.lists()
                except sqlite3.Error:
                    self.drop_team(keep_probe=True)
                    offline = True
        return items, offline

    def find_list(self, list_id):
        items, offline = self.lists()
        item = next((i for i in items if i["id"] == list_id), None)
        if item is None:
            if offline and list_id.startswith("t"):
                raise ApiError(503, "Нет связи с общей папкой (сеть, VPN)")
            raise ApiError(404, "Такого списка нет")
        return item

    def conn(self, item):
        if item["id"] not in self.conns:
            if item["shared"]:
                # shared=True — только чтобы при обрыве связи закрыть соединение в другом потоке
                self.conns[item["id"]] = db.connect(self.team.path(item), timeout=team.TIMEOUT,
                                                    shared=True)
            elif item["file"] is None:
                self.conns[item["id"]] = self.prefs
            else:
                self.conns[item["id"]] = db.connect(db.list_path(item))
        return self.conns[item["id"]]

    def author(self, item):
        """Как в окне: в общем списке — имя участника, в личном — никто."""
        return self.user() if item["shared"] else None

    def members(self, item, conn):
        if not item["shared"]:
            return []
        names = {self.user()}
        names |= {r[0] for r in conn.execute(
            "SELECT DISTINCT assignee FROM tasks WHERE assignee IS NOT NULL AND assignee <> ''")}
        try:
            names |= set(self.team.members())
        except sqlite3.Error:
            pass
        return sorted(names, key=str.lower)

    # --- задачи ---

    def task(self, conn, task_id):
        row = conn.execute(TASK_SQL + " WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise ApiError(404, "Такой задачи нет (возможно, её удалили)")
        counts = db.extras_counts(conn)
        return task_dict(row, counts)

    def full_task(self, conn, task_id):
        task = self.task(conn, task_id)
        task["attachments"] = [dict(zip(("id", "name", "size", "added_by", "added_at"), r))
                               for r in db.list_attachments(conn, task_id)]
        task["comments_list"] = [dict(zip(("id", "author", "text", "created_at"), r))
                                 for r in db.list_comments(conn, task_id)]
        return task

    def list_view(self, item):
        conn = self.conn(item)
        counts = db.extras_counts(conn)
        return {
            "list": {"id": item["id"], "name": item["name"], "shared": item["shared"]},
            "statuses": [{"id": sid, "name": name, "color": color, "done": bool(done)}
                         for sid, name, color, done in db.list_statuses(conn)],
            "tasks": [task_dict(r, counts) for r in conn.execute(TASK_SQL + " ORDER BY id")],
            "members": self.members(item, conn),
            "user": self.user(),
        }

    def sync(self):
        """Всё сразу: телефон хранит копию, чтобы работать без связи и напоминать о сроках.
        Общий список, который не прочитался (пропала связь с папкой), не попадает в ответ —
        shared_offline подскажет телефону оставить его прежнюю копию."""
        items, offline = self.lists()
        lists, views = [], {}
        for item in items:
            try:
                views[item["id"]] = self.list_view(item)
            except (sqlite3.Error, OSError):
                if not item["shared"]:
                    raise
                self.on_error(item)
                offline = True
                continue
            lists.append({"id": item["id"], "name": item["name"], "shared": item["shared"]})
        return {"lists": lists, "views": views, "shared_offline": offline, "user": self.user()}

    def check_status(self, conn, status_id):
        if not any(s[0] == status_id for s in db.list_statuses(conn)):
            raise ApiError(400, "Такой колонки нет")
        return status_id

    def add_task(self, item, data):
        conn = self.conn(item)
        title = check_title(data.get("title"))
        due_at = check_due(data.get("due_at"))
        remind = check_minutes(data.get("remind_before"))
        status_id = data.get("status_id")
        if status_id is not None:
            self.check_status(conn, status_id)
        by = self.author(item)
        task_id = db.add_task(conn, title, status_id, created_by=by)
        db.update_task(conn, task_id, title, due_at, remind, bool(data.get("urgent")),
                       bool(data.get("important")), str(data.get("body") or ""), by=by)
        if item["shared"] and data.get("assignee"):
            db.set_assignee(conn, task_id, str(data["assignee"]), by=by)
        if data.get("done"):
            db.set_done(conn, task_id, True, by=by)
        return self.task(conn, task_id)

    def change_task(self, item, task_id, data):
        """Меняет только присланные поля. version — номер версии, который видел телефон:
        если задачу с тех пор изменили (на компьютере, у другого участника) — ответ 409
        с текущим вариантом задачи, ничего не меняется."""
        conn = self.conn(item)
        current = self.task(conn, task_id)
        version = data.get("version")
        if version is not None and version != current["version"]:
            raise ApiError(409, "Задачу уже изменили", {"task": self.full_task(conn, task_id)})
        by = self.author(item)
        fields = ("title", "body", "due_at", "remind_before", "urgent", "important")
        if any(key in data for key in fields):
            title = check_title(data["title"]) if "title" in data else current["title"]
            due_at = check_due(data["due_at"]) if "due_at" in data else current["due_at"]
            remind = (check_minutes(data["remind_before"]) if "remind_before" in data
                      else current["remind_before"])
            body = str(data.get("body") or "") if "body" in data else None
            saved = db.update_task(conn, task_id, title, due_at, remind,
                                   bool(data.get("urgent", current["urgent"])),
                                   bool(data.get("important", current["important"])),
                                   body, by=by, version=current["version"])
            if not saved:  # успели изменить за эти миллисекунды
                raise ApiError(409, "Задачу уже изменили", {"task": self.full_task(conn, task_id)})
        if "status_id" in data:
            db.set_task_status(conn, task_id, self.check_status(conn, data["status_id"]), by=by)
        elif "done" in data and bool(data["done"]) != current["done"]:
            if not db.set_done(conn, task_id, bool(data["done"]), by=by):
                raise ApiError(400, "На доске нет подходящей колонки")
        if "assignee" in data and item["shared"]:
            db.set_assignee(conn, task_id, data["assignee"] or None, by=by)
        return self.task(conn, task_id)

    def delete_task(self, item, task_id):
        conn = self.conn(item)
        self.task(conn, task_id)
        db.delete_task(conn, task_id)

    def owned(self, conn, table, row_id, task_id):
        row = conn.execute(f"SELECT 1 FROM {table} WHERE id = ? AND task_id = ?",
                           (row_id, task_id)).fetchone()
        if row is None:
            raise ApiError(404, "Не найдено")

    def add_comment(self, item, task_id, data):
        conn = self.conn(item)
        self.task(conn, task_id)
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ApiError(400, "Пустой комментарий")
        db.add_comment(conn, task_id, text.strip(), by=self.author(item))
        return self.full_task(conn, task_id)

    def delete_comment(self, item, task_id, comment_id):
        conn = self.conn(item)
        self.owned(conn, "comments", comment_id, task_id)
        db.delete_comment(conn, comment_id)

    def add_attachment(self, item, task_id, name, data):
        conn = self.conn(item)
        self.task(conn, task_id)
        name = os.path.basename((name or "").replace("\\", "/")).strip()
        if not name:
            raise ApiError(400, "Нужно имя файла (?name=...)")
        db.add_attachment(conn, task_id, name, data, by=self.author(item))
        return self.full_task(conn, task_id)

    def attachment(self, item, task_id, attachment_id):
        conn = self.conn(item)
        self.owned(conn, "attachments", attachment_id, task_id)
        name = conn.execute("SELECT name FROM attachments WHERE id = ?", (attachment_id,)).fetchone()[0]
        return name, db.attachment_data(conn, attachment_id)

    def delete_attachment(self, item, task_id, attachment_id):
        conn = self.conn(item)
        self.owned(conn, "attachments", attachment_id, task_id)
        db.delete_attachment(conn, attachment_id)


# ---------- HTTP ----------

HOME_PAGE = """<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ToDoro</title>
<body style="font-family: sans-serif; margin: 2em; line-height: 1.5">
<h2>ToDoro работает ✓</h2>
<p>Телефон видит этот компьютер — приложение ToDoro на телефоне сможет к нему подключиться.</p>
</body></html>"""

ROUTE = re.compile(r"^/api/v1/lists/(?P<list>[A-Za-z0-9_-]+)"
                   r"(?:/tasks(?:/(?P<task>\d+)(?:/(?P<kind>comments|attachments)(?:/(?P<sub>\d+))?)?)?)?$")


class Handler(BaseHTTPRequestHandler):
    server_version = "ToDoro"
    sys_version = ""
    protocol_version = "HTTP/1.0"  # одно соединение — один запрос: сервер однопоточный

    def log_message(self, format, *args):
        pass  # у значка в трее нет окна для журнала

    # --- ответы ---

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message, extra=None):
        self.send_json(status, {"error": message, **(extra or {})})

    def send_bytes(self, data, content_type, filename=None):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.end_headers()
        self.wfile.write(data)

    # --- запрос ---

    def body_bytes(self, limit):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "Неверная длина запроса") from None
        if length > limit:
            raise ApiError(413, f"Файл больше {limit // (1024 * 1024)} МБ")
        return self.rfile.read(length) if length else b""

    def body_json(self):
        raw = self.body_bytes(1024 * 1024)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "Тело запроса — не JSON") from None
        if not isinstance(data, dict):
            raise ApiError(400, "Ожидался JSON-объект")
        return data

    def authorized(self):
        token = self.server.token
        given = self.headers.get("Authorization", "")
        return bool(token) and hmac.compare_digest(given.encode(), f"Bearer {token}".encode())

    def do_GET(self):
        self.handle_any("GET")

    def do_POST(self):
        # стандартный HttpURLConnection в Java не умеет PATCH — телефон шлёт POST с этим заголовком
        override = self.headers.get("X-HTTP-Method-Override", "").upper()
        self.handle_any("PATCH" if override == "PATCH" else "POST")

    def do_PATCH(self):
        self.handle_any("PATCH")

    def do_DELETE(self):
        self.handle_any("DELETE")

    def handle_any(self, method):
        url = urlsplit(self.path)
        path = url.path.rstrip("/") or "/"
        if method == "GET" and path in ("/", "/ping"):
            self.send_bytes(HOME_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if not path.startswith(API):
            self.send_error_json(404, "Нет такого адреса")
            return
        if not self.authorized():
            time.sleep(0.5)  # чтобы ключ нельзя было быстро подбирать
            self.send_error_json(401, "Неверный ключ — подключите телефон заново (QR-код в ToDoro)")
            return
        store, item = self.server.store, None
        try:
            with self.server.lock:
                item = self.route(store, method, path, parse_qs(url.query))
        except ApiError as error:
            self.send_error_json(error.status, error.message, error.extra)
        except (sqlite3.Error, OSError) as error:
            store.on_error(item)
            self.send_error_json(503, f"Не удалось прочитать или записать список: {error}")

    def route(self, store, method, path, query):
        """Выполняет запрос и отвечает; возвращает список, с которым работали (или None)."""
        if path == API + "/hello" and method == "GET":
            self.send_json(200, {"app": "ToDoro", "version": APP_VERSION, "api": 1,
                                 "user": store.user(), "computer": socket.gethostname()})
            return None
        if path == API + "/lists" and method == "GET":
            items, offline = store.lists()
            self.send_json(200, {"lists": [{"id": i["id"], "name": i["name"], "shared": i["shared"]}
                                           for i in items],
                                 "shared_offline": offline, "user": store.user()})
            return None
        if path == API + "/sync" and method == "GET":
            self.send_json(200, store.sync())
            return None
        match = ROUTE.match(path)
        if not match:
            raise ApiError(404, "Нет такого адреса")
        item = store.find_list(match["list"])
        task_id = int(match["task"]) if match["task"] else None
        sub_id = int(match["sub"]) if match["sub"] else None
        kind = match["kind"]
        tasks_path = path.endswith("/tasks")
        if task_id is None and not tasks_path:
            if method != "GET":
                raise ApiError(405, "Так нельзя")
            self.send_json(200, store.list_view(item))
        elif task_id is None:
            if method != "POST":
                raise ApiError(405, "Так нельзя")
            self.send_json(201, {"task": store.add_task(item, self.body_json())})
        elif kind is None:
            if method == "GET":
                self.send_json(200, {"task": store.full_task(store.conn(item), task_id)})
            elif method == "PATCH":
                self.send_json(200, {"task": store.change_task(item, task_id, self.body_json())})
            elif method == "DELETE":
                store.delete_task(item, task_id)
                self.send_json(200, {"deleted": task_id})
            else:
                raise ApiError(405, "Так нельзя")
        elif kind == "comments":
            if method == "POST" and sub_id is None:
                self.send_json(201, {"task": store.add_comment(item, task_id, self.body_json())})
            elif method == "DELETE" and sub_id is not None:
                store.delete_comment(item, task_id, sub_id)
                self.send_json(200, {"deleted": sub_id})
            else:
                raise ApiError(405, "Так нельзя")
        else:  # attachments
            if method == "POST" and sub_id is None:
                data = self.body_bytes(db.MAX_ATTACHMENT)
                name = (query.get("name") or [""])[0]
                self.send_json(201, {"task": store.add_attachment(item, task_id, name, data)})
            elif method == "GET" and sub_id is not None:
                name, data = store.attachment(item, task_id, sub_id)
                kind_ = mimetypes.guess_type(name)[0] or "application/octet-stream"
                self.send_bytes(data, kind_, name)
            elif method == "DELETE" and sub_id is not None:
                store.delete_attachment(item, task_id, sub_id)
                self.send_json(200, {"deleted": sub_id})
            else:
                raise ApiError(405, "Так нельзя")
        return item


class Server(HTTPServer):
    """Однопоточный: запросы выполняются по очереди (телефон один, а SQLite так спокойнее)."""
    allow_reuse_address = False  # иначе на Windows две копии могут слушать один порт

    def __init__(self, port, token, prefs_path=None):
        super().__init__(("0.0.0.0", port), Handler)
        self.token = token
        self.lock = threading.Lock()
        self.store = None
        self.prefs_path = prefs_path

    def serve(self):
        self.store = Store(self.prefs_path)  # соединения — в потоке сервера
        try:
            self.serve_forever(poll_interval=0.5)
        finally:
            self.store.close()


def run_forever(port=PORT, prefs_path=None):
    """Для значка в трее (в отдельном потоке): включает сервер, когда в ToDoro подключили
    телефон, выключает, когда отключили, и подхватывает новый ключ. Никогда не возвращается."""
    server = thread = None
    while True:
        try:
            prefs = sqlite3.connect(prefs_path or db.default_path(), timeout=5)
            try:
                row = prefs.execute("SELECT value FROM settings WHERE key = ?", (TOKEN_KEY,)).fetchone()
            finally:
                prefs.close()
            token = row[0] if row else None
        except sqlite3.Error:
            token = server.token if server else None  # файл занят — оставляем как было
        if token and server is None:
            try:
                server = Server(port, token, prefs_path)
                thread = threading.Thread(target=server.serve, daemon=True)
                thread.start()
            except OSError:
                server = None  # порт занят — попробуем позже
        elif server is not None and not token:
            server.shutdown()
            server.server_close()
            thread.join(5)
            server = thread = None
        elif server is not None:
            server.token = token
        time.sleep(CHECK_EVERY)


def start_in_background(version, port=PORT, prefs_path=None):
    global APP_VERSION
    APP_VERSION = version
    threading.Thread(target=run_forever, args=(port, prefs_path), daemon=True).start()
