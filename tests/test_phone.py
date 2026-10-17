"""Проверки связи с телефоном (phone.py): настоящий сервер на свободном порту и временные файлы.

Запуск из папки проекта:  python -m unittest discover tests
"""
import json
import shutil
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

    def test_comments_and_files(self):
        task_id = self.call("POST", "/api/v1/lists/personal/tasks", {"title": "Отчёт"})[1]["task"]["id"]
        path = f"/api/v1/lists/personal/tasks/{task_id}"
        answer = self.call("POST", path + "/comments", {"text": "с телефона"})[1]
        self.assertEqual([c["text"] for c in answer["task"]["comments_list"]], ["с телефона"])
        answer = self.call("POST", path + "/attachments?name=%D1%84%D0%BE%D1%82%D0%BE.jpg",
                           raw=b"\xff\xd8 jpeg")[1]
        (attachment,) = answer["task"]["attachments"]
        self.assertEqual((attachment["name"], attachment["size"]), ("фото.jpg", 7))
        status, data = self.call("GET", f"{path}/attachments/{attachment['id']}")
        self.assertEqual((status, data), (200, b"\xff\xd8 jpeg"))
        # чужой номер файла (из другой задачи) не отдаётся
        other = self.call("POST", "/api/v1/lists/personal/tasks", {"title": "Другая"})[1]["task"]["id"]
        self.assertEqual(self.call("GET", f"/api/v1/lists/personal/tasks/{other}/attachments/"
                                          f"{attachment['id']}")[0], 404)

    def test_bad_input(self):
        self.assertEqual(self.call("POST", "/api/v1/lists/personal/tasks", {"title": "  "})[0], 400)
        self.assertEqual(self.call("POST", "/api/v1/lists/personal/tasks",
                                   {"title": "x", "due_at": "завтра"})[0], 400)
        self.assertEqual(self.call("GET", "/api/v1/lists/nope")[0], 404)
        self.assertEqual(self.call("POST", "/api/v1/lists/personal/tasks", raw=b"{")[0], 400)

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
        view = self.call("GET", f"/api/v1/lists/{item['id']}")[1]
        self.assertEqual(view["members"], ["Аня", "Боря"])
        # задача видна и программе на компьютере (тот же файл)
        conn = db.connect(group.path(item))
        self.assertEqual(db.task_meta(conn, task["id"])["updated_by"], "Аня")
        conn.close()


if __name__ == "__main__":
    unittest.main()
