"""Проверки связи с телефоном (phone.py): настоящий сервер на свободном порту и временные файлы.

Запуск из папки проекта:  python -m unittest discover tests
"""
import json
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import phone  # noqa: E402
import team  # noqa: E402


class PhoneServerTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-phone-"))
        self.prefs_path = self.dir / "todoro.db"
        prefs = db.connect(self.prefs_path)
        db.set_setting(prefs, "user_name", "Аня")
        self.token = phone.new_token(prefs)
        prefs.close()
        self.server = phone.Server(0, self.token, self.prefs_path)  # 0 — любой свободный порт
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, method, path, data=None, raw=None, token=None):
        body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
        request = urllib.request.Request(self.base + path, data=body, method=method)
        request.add_header("Authorization", f"Bearer {token or self.token}")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                content = response.read()
                if response.headers.get_content_type() == "application/json":
                    return response.status, json.loads(content)
                return response.status, content
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_wrong_key_is_refused(self):
        status, answer = self.call("GET", "/api/v1/lists", token="wrong-key")
        self.assertEqual(status, 401)
        self.assertIn("error", answer)

    def test_home_page_needs_no_key(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as response:
            self.assertIn("ToDoro работает", response.read().decode("utf-8"))

    def test_task_round_trip_in_personal_list(self):
        status, answer = self.call("POST", "/api/v1/lists/personal/tasks",
                                   {"title": "Хлеб", "due_at": "2026-10-20 10:00", "remind_before": 15,
                                    "important": True})
        self.assertEqual(status, 201)
        task = answer["task"]
        self.assertEqual((task["title"], task["due_at"], task["important"], task["author"]),
                         ("Хлеб", "2026-10-20 10:00", True, None))  # в личном списке автора нет
        path = f"/api/v1/lists/personal/tasks/{task['id']}"
        status, answer = self.call("PATCH", path, {"version": task["version"], "title": "Хлеб и молоко"})
        self.assertEqual((status, answer["task"]["title"]), (200, "Хлеб и молоко"))
        # телефон видел старую версию — правка не проходит, приходит текущий вариант
        status, answer = self.call("PATCH", path, {"version": task["version"], "title": "старое"})
        self.assertEqual((status, answer["task"]["title"]), (409, "Хлеб и молоко"))
        status, answer = self.call("PATCH", path, {"done": True})
        self.assertTrue(answer["task"]["done"])
        status, answer = self.call("GET", "/api/v1/lists/personal")
        done_column = next(s["id"] for s in answer["statuses"] if s["done"])
        self.assertEqual(answer["tasks"][0]["status_id"], done_column)
        status, _ = self.call("DELETE", path)
        self.assertEqual(status, 200)
        self.assertEqual(self.call("GET", path)[0], 404)

    def test_patch_through_post_override(self):
        """Телефон шлёт PATCH как POST с заголовком X-HTTP-Method-Override."""
        task = self.call("POST", "/api/v1/lists/personal/tasks", {"title": "Старое"})[1]["task"]
        request = urllib.request.Request(f"{self.base}/api/v1/lists/personal/tasks/{task['id']}",
                                         data=json.dumps({"title": "Новое"}).encode(), method="POST")
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("X-HTTP-Method-Override", "PATCH")
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(json.loads(response.read())["task"]["title"], "Новое")

    def test_sync_returns_every_list(self):
        self.call("POST", "/api/v1/lists/personal/tasks", {"title": "Хлеб"})
        answer = self.call("GET", "/api/v1/sync")[1]
        self.assertEqual([i["id"] for i in answer["lists"]], ["personal"])
        self.assertEqual([t["title"] for t in answer["views"]["personal"]["tasks"]], ["Хлеб"])
        self.assertEqual(answer["user"], "Аня")

    def test_comments(self):
        task_id = self.call("POST", "/api/v1/lists/personal/tasks", {"title": "Отчёт"})[1]["task"]["id"]
        path = f"/api/v1/lists/personal/tasks/{task_id}"
        answer = self.call("POST", path + "/comments", {"text": "с телефона"})[1]
        (comment,) = answer["task"]["comments_list"]
        self.assertEqual(comment["text"], "с телефона")
        self.assertEqual(answer["task"]["comments"], 1)
        # чужой номер комментария (из другой задачи) не удаляется
        other = self.call("POST", "/api/v1/lists/personal/tasks", {"title": "Другая"})[1]["task"]["id"]
        self.assertEqual(self.call("DELETE", f"/api/v1/lists/personal/tasks/{other}/comments/"
                                             f"{comment['id']}")[0], 404)
        self.assertEqual(self.call("DELETE", f"{path}/comments/{comment['id']}")[0], 200)

    def test_files_are_not_served(self):
        """Файлы задач телефону не передаются: ни список, ни содержимое, ни загрузка."""
        prefs = db.connect(self.prefs_path)
        task_id = db.add_task(prefs, "С файлом")
        attachment_id = db.add_attachment(prefs, task_id, "секрет.txt", b"data")
        prefs.close()
        path = f"/api/v1/lists/personal/tasks/{task_id}"
        task = self.call("GET", path)[1]["task"]
        self.assertEqual(task["files"], 1)  # сколько файлов — видно
        self.assertNotIn("attachments", task)
        self.assertEqual(self.call("GET", f"{path}/attachments/{attachment_id}")[0], 404)
        self.assertEqual(self.call("POST", f"{path}/attachments?name=a.txt", raw=b"x")[0], 404)
        self.assertEqual(self.call("DELETE", f"{path}/attachments/{attachment_id}")[0], 404)

    def test_repeated_create_makes_one_task(self):
        """Ответ потерялся, телефон прислал ту же новую задачу ещё раз — задача одна."""
        data = {"title": "Хлеб", "client_id": "abc-123"}
        first = self.call("POST", "/api/v1/lists/personal/tasks", data)
        again = self.call("POST", "/api/v1/lists/personal/tasks", data)
        self.assertEqual(first[0], 201)
        self.assertEqual(again[1]["task"]["id"], first[1]["task"]["id"])
        other = self.call("POST", "/api/v1/lists/personal/tasks", {"title": "Хлеб", "client_id": "xyz"})
        self.assertNotEqual(other[1]["task"]["id"], first[1]["task"]["id"])
        self.assertEqual(len(self.call("GET", "/api/v1/lists/personal")[1]["tasks"]), 2)
        # задачу удалили на компьютере, а телефон шлёт её снова — не создаём заново
        self.call("DELETE", f"/api/v1/lists/personal/tasks/{first[1]['task']['id']}")
        self.assertEqual(self.call("POST", "/api/v1/lists/personal/tasks", data)[0], 404)

    def test_bad_input(self):
        self.assertEqual(self.call("POST", "/api/v1/lists/personal/tasks", {"title": "  "})[0], 400)
        self.assertEqual(self.call("POST", "/api/v1/lists/personal/tasks",
                                   {"title": "x", "due_at": "завтра"})[0], 400)
        self.assertEqual(self.call("GET", "/api/v1/lists/nope")[0], 404)
        self.assertEqual(self.call("POST", "/api/v1/lists/personal/tasks", raw=b"{")[0], 400)

    def test_silent_connection_does_not_block(self):
        """Кто-то подключился и молчит — сервер однопоточный, но телефону отвечает."""
        phone.Handler.timeout, saved = 0.5, phone.Handler.timeout
        self.addCleanup(setattr, phone.Handler, "timeout", saved)
        idle = socket.create_connection(("127.0.0.1", self.server.server_address[1]))
        self.addCleanup(idle.close)
        status, answer = self.call("GET", "/api/v1/hello")
        self.assertEqual((status, answer["app"]), (200, "ToDoro"))

    def test_sync_survives_lost_shared_folder(self):
        """Связь с общей папкой пропала на первом общем списке — остальные общие пропускаются,
        личный список всё равно приходит телефону."""
        folder = self.dir / "share"
        group = team.Team(folder)
        group.add_list("Команда", "Боря")
        group.add_list("Дом", "Боря")
        group.close()
        prefs = db.connect(self.prefs_path)
        db.set_setting(prefs, "shared_folder", str(folder))
        prefs.close()
        store = phone.Store(self.prefs_path)
        self.addCleanup(store.close)
        list_view, broken_ids = store.list_view, []

        def broken(item):
            if item["shared"] and not broken_ids:  # первый же общий список
                broken_ids.append(item["id"])
                store.conn(item)
                raise sqlite3.OperationalError("disk I/O error")  # как при обрыве сети
            return list_view(item)

        store.list_view = broken
        answer = store.sync()
        self.assertTrue(answer["shared_offline"])
        self.assertEqual(list(answer["views"]), ["personal"])

    def test_shared_list(self):
        folder = self.dir / "share"
        group = team.Team(folder)
        item = group.add_list("Команда", "Боря")
        group.touch_member("Боря")
        group.close()
        prefs = db.connect(self.prefs_path)
        db.set_setting(prefs, "shared_folder", str(folder))
        prefs.close()
        answer = self.call("GET", "/api/v1/lists")[1]
        self.assertFalse(answer["shared_offline"])
        self.assertIn({"id": item["id"], "name": "Команда", "shared": True}, answer["lists"])
        task = self.call("POST", f"/api/v1/lists/{item['id']}/tasks",
                         {"title": "Позвонить", "assignee": "Боря"})[1]["task"]
        self.assertEqual((task["author"], task["assignee"]), ("Аня", "Боря"))
        synced = self.call("GET", "/api/v1/sync")[1]
        self.assertEqual(synced["views"][item["id"]]["tasks"][0]["assignee"], "Боря")
        view = self.call("GET", f"/api/v1/lists/{item['id']}")[1]
        self.assertEqual(view["members"], ["Аня", "Боря"])
        # задача видна и программе на компьютере (тот же файл)
        conn = db.connect(group.path(item))
        self.assertEqual(db.task_meta(conn, task["id"])["updated_by"], "Аня")
        conn.close()


if __name__ == "__main__":
    unittest.main()
