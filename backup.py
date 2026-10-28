"""Резервные копии списков задач.

Копия — один zip-файл: внутри файлы списков (SQLite, со всеми задачами, колонками, бизнес-
единицами, комментариями и вложенными файлами) и опись MANIFEST — какие это списки.
    daily_personal()  — раз в день копирует личные списки в DATA_DIR/backups (BACKUP_DAYS дней)
    write_zip()       — копия выбранных списков в файл (его выбирает пользователь или daily_personal)
    open_backup()     — достаёт списки из копии (zip или отдельный файл списка .db) во временную папку
    restore_list()    — заменяет содержимое списка содержимым списка из копии (restore_file — то же
                        со своим соединением, для фонового потока)
    copy_as_new_list() — список из копии, которого сейчас нет, — в новый файл личного списка
"""
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import db

BACKUP_DAYS = 14
MANIFEST = "todoro-backup.json"
FORMAT = 1
# Что такое «содержимое списка» — эти таблицы заменяются при восстановлении. Таблица settings
# не трогается: в основном файле в ней настройки программы и перечень списков.
LIST_TABLES = ("statuses", "units", "tasks", "attachments", "comments")
# Ежедневные копии и копии «перед восстановлением» — их программа удаляет сама через BACKUP_DAYS дней
# (и недописанные .part, если программу закрыли посреди копирования)
AUTO_NAME = re.compile(r"^ToDoro .*?(\d{4}-\d{2}-\d{2}).*\.zip(\.part)?$")
TIMEOUT = 15
# Рабочие папки — во временной папке ToDoro: если программу закроют посреди работы, оставшееся
# там уберёт clean_temp_files при следующем запуске
TEMP_DIR = Path(tempfile.gettempdir()) / "ToDoro"


class BackupError(Exception):
    """Понятное пользователю описание того, что с копией не так."""


def backups_dir():
    return db.DATA_DIR / "backups"


def copy_db(source, target, timeout=TIMEOUT):
    """Целостная копия файла SQLite, даже если в него сейчас кто-то пишет."""
    src = sqlite3.connect(source, timeout=timeout)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def scrub(path):
    """Убирает из копии настройки: в основном файле среди них ключ телефона и путь к общей папке,
    а копию могут хранить на флешке или в облаке. При восстановлении настройки не нужны."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA secure_delete = ON")  # стёртое затирается, а не остаётся в файле
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'settings'").fetchone():
            with conn:
                conn.execute("DELETE FROM settings")
    finally:
        conn.close()


def work_dir(prefix):
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=TEMP_DIR))


def write_zip(target, sources, created=None):
    """Копирует списки в zip-файл target. sources — [(item, путь к файлу списка), ...], где item —
    {"id", "name", "shared"}. Пишет сначала во временный файл рядом: прежний файл с тем же именем
    не испортится, если что-то пойдёт не так. Возвращает число скопированных списков."""
    target = Path(target)
    work = work_dir("backup-")
    partial = target.with_name(target.name + ".part")
    try:
        entries = []
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
            for n, (item, source) in enumerate(sources, 1):
                if not Path(source).exists():
                    continue
                inner = f"{n:02d}.db"
                copy_db(source, work / inner)
                scrub(work / inner)
                archive.write(work / inner, inner)
                (work / inner).unlink()
                entries.append({"id": item["id"], "name": item["name"],
                                "shared": bool(item.get("shared")), "file": inner})
            archive.writestr(MANIFEST, json.dumps(
                {"format": FORMAT, "created": created or datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "lists": entries}, ensure_ascii=False, indent=1))
        os.replace(partial, target)
        return len(entries)
    finally:
        partial.unlink(missing_ok=True)
        shutil.rmtree(work, ignore_errors=True)


def personal_sources(prefs):
    """Все личные списки: [(item, путь к файлу), ...]."""
    return [(dict(item, shared=False), db.list_path(item)) for item in db.list_registry(prefs)]


def daily_personal(items, today=None):
    """Раз в день копирует личные списки в backups/«ToDoro ГГГГ-ММ-ДД.zip» и удаляет
    автоматические копии старше BACKUP_DAYS дней. items — результат personal_sources (его надо
    взять в окне: соединение с основным файлом из другого потока трогать нельзя).
    Вызывается в фоновом потоке. Возвращает путь к новой копии или None (сегодня уже была)."""
    today = today or date.today()
    folder = backups_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"ToDoro {today.isoformat()}.zip"
    made = None
    if not target.exists():
        write_zip(target, items)
        made = target
    remove_old(folder, today)
    return made


def remove_old(folder, today=None):
    oldest = ((today or date.today()) - timedelta(days=BACKUP_DAYS)).isoformat()
    for file in Path(folder).iterdir():
        found = AUTO_NAME.match(file.name)
        if found and file.is_file() and found.group(1) < oldest:
            try:
                file.unlink()
            except OSError:
                pass  # открыт в другой программе — уберём в следующий раз


def safety_copy(sources):
    """Копия списков перед восстановлением — чтобы восстановление можно было отменить."""
    folder = backups_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"ToDoro перед восстановлением {datetime.now():%Y-%m-%d %H-%M-%S}.zip"
    write_zip(target, sources)
    return target


def count_tasks(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()


def open_backup(path):
    """Достаёт списки из копии во временную папку. Возвращает (папка, когда сделана копия,
    [{"id", "name", "shared", "path", "tasks"}, ...]); папку потом удаляет тот, кто вызвал.
    Понимает zip-копию ToDoro и отдельный файл списка (.db) — например, из ежедневных копий
    общих списков в общей папке."""
    path = Path(path)
    work = work_dir("restore-")
    try:
        if zipfile.is_zipfile(path):
            lists, created = read_zip(path, work)
        else:
            lists, created = [single_file(path, work)], None
        for entry in lists:
            check_list(entry)
        if not lists:
            raise BackupError("В копии нет ни одного списка.")
        return work, created, lists
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise


def read_zip(path, work):
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                manifest = json.loads(archive.read(MANIFEST).decode("utf-8"))
            except KeyError:
                raise BackupError("Это не резервная копия ToDoro.") from None
            if not isinstance(manifest, dict) or not isinstance(manifest.get("lists", []), list):
                raise BackupError("Файл копии повреждён.")
            version = manifest.get("format", 0)
            if not isinstance(version, int) or version > FORMAT:
                raise BackupError("Копия сделана более новой версией ToDoro — обновите программу.")
            names = set(archive.namelist())
            lists = []
            for entry in manifest.get("lists", []):
                if not isinstance(entry, dict):
                    continue
                inner = entry.get("file", "")
                # имя файла внутри копии — только простое имя: никаких путей в чужие папки
                if inner not in names or not re.fullmatch(r"\d+\.db", inner):
                    continue
                target = work / inner
                with archive.open(inner) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                lists.append({"id": str(entry.get("id", "")), "name": str(entry.get("name") or "Список"),
                              "shared": bool(entry.get("shared")), "path": target})
            return lists, manifest.get("created")
    except (zipfile.BadZipFile, ValueError, UnicodeDecodeError) as error:
        raise BackupError(f"Файл копии повреждён.\n\n{error}") from None


def single_file(path, work):
    """Отдельный файл списка. Какой это список — понятно по имени файла: todoro.db — личный,
    <id>.db — другой личный или общий список с этим id."""
    target = work / "01.db"
    if not path.is_file():
        raise BackupError("Файл копии не найден.")
    try:
        copy_db(path, target)
    except sqlite3.Error as error:
        raise BackupError(f"Это не файл списка ToDoro.\n\n{error}") from None
    stem = path.stem
    list_id = db.PERSONAL if path.name.lower() == "todoro.db" else stem
    return {"id": list_id, "name": "Личный" if list_id == db.PERSONAL else stem,
            "shared": list_id != db.PERSONAL and stem.startswith("t"), "path": target}


def check_list(entry):
    """Файл из копии — действительно список задач; заодно добавляет в него столбцы новых версий."""
    try:
        conn = sqlite3.connect(entry["path"])
        try:
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("файл повреждён")
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'tasks'").fetchone():
                raise sqlite3.DatabaseError("в файле нет задач")
        finally:
            conn.close()
        db.connect(entry["path"]).close()  # копия из старой версии — получит новые столбцы
        scrub(entry["path"])  # чужие настройки (ключ телефона) не должны попасть в новый список
        entry["tasks"] = count_tasks(entry["path"])
    except sqlite3.Error as error:
        raise BackupError(f"Список «{entry['name']}» в копии не читается.\n\n{error}") from None


def columns(conn, schema, table):
    return [row[1] for row in conn.execute(f"PRAGMA {schema}.table_info({table})")]


def restore_list(conn, source):
    """Заменяет задачи, колонки доски, бизнес-единицы, комментарии и вложения списка (conn)
    содержимым файла source из копии. Настройки не трогает.
    Номера версий задач после восстановления больше всех прежних: у того, кто в это время
    правит задачу (другой участник, телефон), правка не запишется молча поверх."""
    top = conn.execute("SELECT COALESCE(MAX(version), 0) FROM tasks").fetchone()[0]
    if conn.in_transaction:
        conn.commit()  # ATTACH внутри транзакции нельзя
    conn.execute("ATTACH DATABASE ? AS backup", (str(source),))
    try:
        with conn:
            for table in LIST_TABLES:
                mine = columns(conn, "main", table)
                theirs = set(columns(conn, "backup", table))
                common = ", ".join(c for c in mine if c in theirs)
                conn.execute(f"DELETE FROM main.{table}")
                conn.execute(f"INSERT INTO main.{table} ({common}) SELECT {common} FROM backup.{table}")
            conn.execute("UPDATE main.tasks SET version = version + ?", (top + 1,))
            # напоминания, время которых уже прошло, второй раз не показываем
            conn.execute("UPDATE main.tasks SET reminded = 1 WHERE reminded = 0 AND due_at IS NOT NULL "
                         "AND remind_before IS NOT NULL AND datetime(due_at, '-' || remind_before || "
                         "' minutes') <= datetime('now', 'localtime')")
    finally:
        conn.execute("DETACH DATABASE backup")


def restore_file(path, source):
    """restore_list для файла списка — со своим соединением, чтобы работать в фоновом потоке."""
    conn = db.connect(path, timeout=TIMEOUT)
    try:
        restore_list(conn, source)
    finally:
        conn.close()


def copy_as_new_list(entry):
    """Копирует список из копии в новый файл в LISTS_DIR (можно в фоне). Возвращает имя файла."""
    file = db.new_list_file()
    copy_db(entry["path"], db.LISTS_DIR / file)
    return file


def new_list_item(file, name):
    return {"id": file.removesuffix(".db"), "name": name, "file": file}


def add_as_new_list(prefs, entry, name):
    """Список из копии, которого сейчас нет, — становится новым личным списком. Возвращает его item."""
    item = new_list_item(copy_as_new_list(entry), name)
    db.save_registry(prefs, db.list_registry(prefs) + [item])
    return item
