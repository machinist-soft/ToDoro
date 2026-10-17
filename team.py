"""Общие списки задач в сетевой папке: видят и меняют все участники команды.

Устройство общей папки (подпапка ToDoro внутри папки из настроек):
    team.db           — перечень общих списков и участников
    lists/<id>.db     — сами списки (такие же файлы, как личные списки)
    backups/<дата>/   — ежедневные копии списков за последние BACKUP_DAYS дней
"""
import os
import shutil
import socket
import sqlite3
import threading
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

import db

BACKUP_DAYS = 14
TIMEOUT = 15  # секунд ждать, если файл сейчас пишет другой участник


class Probe:
    """Фоновая проверка, на связи ли общая папка.

    Когда пропадает Wi-Fi или VPN, любое обращение к сетевой папке может «повиснуть» на
    десятки секунд — и окно программы белеет. Поэтому окно само к папке не ходит, пока эта
    проверка (в отдельном потоке) не скажет, что связь есть. Если проверка сама повисла
    дольше HANG секунд — значит, связи нет."""
    EVERY = 3  # секунд между проверками
    HANG = 3   # секунд: дольше — считаем, что связи нет

    def __init__(self, folder):
        self.folder = folder
        self.file = Path(str(folder).strip()) / "ToDoro" / "team.db"
        self.ok = None        # None — ещё ни разу не проверяли
        self.started = None   # когда началась идущая сейчас проверка
        self.stopped = False
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while not self.stopped:
            self.started = time.monotonic()
            try:
                with open(self.file, "rb") as file:  # открыть и прочитать — нужен ответ сервера
                    ok = len(file.read(100)) == 100
            except OSError:
                ok = False
            self.ok, self.started = ok, None
            time.sleep(self.EVERY)

    def online(self):
        started = self.started
        if started is not None and time.monotonic() - started > self.HANG:
            return False
        return bool(self.ok)

    def stop(self):
        self.stopped = True


class TeamError(Exception):
    """Понятное пользователю описание того, что пошло не так с общей папкой."""


class Team:
    def __init__(self, folder):
        self.folder = str(folder).strip()
        self.root = Path(self.folder) / "ToDoro"
        try:
            (self.root / "lists").mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.root / "team.db", timeout=TIMEOUT)
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS lists (
                    id         TEXT PRIMARY KEY,
                    name       TEXT NOT NULL,
                    file       TEXT NOT NULL,
                    created_by TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    deleted    INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS members (
                    name      TEXT PRIMARY KEY,
                    computer  TEXT,
                    last_seen TEXT
                );
                """
            )
        except (OSError, sqlite3.Error) as error:
            raise TeamError(f"Не удалось открыть общую папку\n{self.folder}\n\n"
                            "Проверьте, что она доступна (сеть, VPN) и в неё можно записывать.") from error
        # Файлы удалённых списков, которые в момент удаления был кто-то открыт, — убираем сейчас
        for (file,) in self.conn.execute("SELECT file FROM lists WHERE deleted = 1"):
            try:
                (self.root / "lists" / file).unlink(missing_ok=True)
            except OSError:
                pass  # всё ещё открыт у кого-то — уберём в следующий раз

    def close(self):
        self.conn.close()

    # --- списки ---

    def lists(self):
        rows = self.conn.execute(
            "SELECT id, name, file FROM lists WHERE deleted = 0 ORDER BY created_at, name").fetchall()
        return [{"id": i, "name": n, "file": f, "shared": True} for i, n, f in rows]

    def path(self, item):
        return self.root / "lists" / item["file"]

    def add_list(self, name, user):
        list_id = "t" + uuid.uuid4().hex[:12]  # «t» — общий список (у личных такой буквы нет)
        item = {"id": list_id, "name": name, "file": f"{list_id}.db", "shared": True}
        db.connect(self.path(item), timeout=TIMEOUT).close()  # создать файл с колонками доски
        with self.conn:
            self.conn.execute("INSERT INTO lists (id, name, file, created_by) VALUES (?, ?, ?, ?)",
                              (list_id, name, item["file"], user))
        return item

    def rename_list(self, list_id, name):
        with self.conn:
            self.conn.execute("UPDATE lists SET name = ? WHERE id = ?", (name, list_id))

    def delete_list(self, item):
        """Убирает список у всех; файл удаляется (копии остаются в backups)."""
        with self.conn:
            self.conn.execute("UPDATE lists SET deleted = 1 WHERE id = ?", (item["id"],))
        try:
            self.path(item).unlink()
        except OSError:
            pass  # файл сейчас открыт у кого-то — список всё равно скрыт

    def version(self):
        """Меняется, когда кто-то добавил, переименовал или удалил общий список."""
        return self.conn.execute("PRAGMA data_version").fetchone()[0], \
            self.conn.execute("SELECT COUNT(*), MAX(created_at) FROM lists WHERE deleted = 0").fetchone()

    # --- участники ---

    def touch_member(self, name):
        with self.conn:
            self.conn.execute(
                "INSERT INTO members (name, computer, last_seen) VALUES (?, ?, datetime('now', 'localtime')) "
                "ON CONFLICT(name) DO UPDATE SET computer = excluded.computer, last_seen = excluded.last_seen",
                (name, socket.gethostname()))

    def members(self):
        return [r[0] for r in self.conn.execute("SELECT name FROM members ORDER BY name")]

    # --- резервные копии ---

    def backup_daily(self):
        """Раз в день (кто первый открыл программу) копирует все общие списки в backups/<дата>
        и удаляет копии старше BACKUP_DAYS дней. Вызывается в фоновом потоке."""
        backups = self.root / "backups"
        today = backups / date.today().isoformat()
        if today.exists():
            return
        conn = sqlite3.connect(self.root / "team.db", timeout=TIMEOUT)
        try:
            files = [r[0] for r in conn.execute("SELECT file FROM lists WHERE deleted = 0")]
        finally:
            conn.close()
        tmp = backups / (today.name + ".tmp")
        tmp.mkdir(parents=True, exist_ok=True)
        for name in files + ["../team.db"]:
            source = (self.root / "lists" / name).resolve() if name != "../team.db" else self.root / "team.db"
            if not source.exists():
                continue
            src = sqlite3.connect(source, timeout=TIMEOUT)
            dst = sqlite3.connect(tmp / source.name)
            try:
                src.backup(dst)  # целостная копия, даже если кто-то сейчас пишет
            finally:
                dst.close()
                src.close()
        try:
            os.replace(tmp, today)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)  # кто-то успел раньше
        oldest = (date.today() - timedelta(days=BACKUP_DAYS)).isoformat()
        for folder in backups.iterdir():
            if folder.is_dir() and folder.name < oldest:
                shutil.rmtree(folder, ignore_errors=True)
