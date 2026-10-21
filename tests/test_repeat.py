"""Повторяющиеся задачи и вид «Календарь» (issue #5): расчёт следующего срока, создание следующей
задачи при выполнении (в окне, с телефона, через колонки), перенос между списками, форма, значок,
раскладка календаря. Временные файлы; окна Tk — за краем экрана; данные пользователя не трогаются."""

import gc
import json
import shutil
import sqlite3
import sys
import tempfile
import threading
import tkinter as tk
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import phone  # noqa: E402
from tests.test_core import TempDir  # noqa: E402

OFFSCREEN = "+-5000+-5000"
STATUSES = [(1, "Новая", "#3b82f6", 0), (2, "Выполнено", "#22c55e", 1)]


def stamp(when):
    return when.strftime("%Y-%m-%d %H:%M")


def tomorrow_at(hour=10):
    """Срок завтра — следующий срок от него всегда в будущем, тест не зависит от времени запуска."""
    return (datetime.now() + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)


# ---------- расчёт сроков ----------

class AddPeriodTests(unittest.TestCase):
    def test_day_and_week(self):
        start = datetime(2026, 12, 31, 9, 30)
        self.assertEqual(db.add_period(start, "day"), datetime(2027, 1, 1, 9, 30))
        self.assertEqual(db.add_period(start, "week"), datetime(2027, 1, 7, 9, 30))
        self.assertEqual(db.add_period(start, "day", 3), datetime(2027, 1, 3, 9, 30))

    def test_month_keeps_day_and_crosses_year(self):
        self.assertEqual(db.add_period(datetime(2026, 12, 15, 8, 0), "month"), datetime(2027, 1, 15, 8, 0))
        self.assertEqual(db.add_period(datetime(2026, 11, 30), "month"), datetime(2026, 12, 30))
        self.assertEqual(db.add_period(datetime(2026, 1, 15), "month", 23), datetime(2027, 12, 15))
        self.assertEqual(db.add_period(datetime(2026, 1, 15), "month", 24), datetime(2028, 1, 15))

    def test_31st_becomes_last_day(self):
        """31-е в коротком месяце — последний день, а через месяц снова 31-е (счёт от исходного)."""
        jan31 = datetime(2026, 1, 31, 10, 0)
        self.assertEqual(db.add_period(jan31, "month", 1), datetime(2026, 2, 28, 10, 0))
        self.assertEqual(db.add_period(jan31, "month", 2), datetime(2026, 3, 31, 10, 0))
        self.assertEqual(db.add_period(jan31, "month", 3), datetime(2026, 4, 30, 10, 0))
        self.assertEqual(db.add_period(datetime(2027, 12, 31), "month", 2), datetime(2028, 2, 29))
        self.assertEqual(db.add_period(datetime(2026, 12, 31), "month", 1), datetime(2027, 1, 31))

    def test_leap_year(self):
        feb29 = datetime(2024, 2, 29, 9, 0)
        self.assertEqual(db.add_period(feb29, "year", 1), datetime(2025, 2, 28, 9, 0))
        self.assertEqual(db.add_period(feb29, "year", 4), datetime(2028, 2, 29, 9, 0))
        self.assertEqual(db.add_period(feb29, "month", 12), datetime(2025, 2, 28, 9, 0))
        self.assertEqual(db.add_period(datetime(2026, 12, 31), "year"), datetime(2027, 12, 31))


class NextDueTests(unittest.TestCase):
    def test_simple(self):
        now = datetime(2026, 10, 20, 12, 0)
        self.assertEqual(db.next_due("2026-10-20 09:00", "day", now), "2026-10-21 09:00")
        self.assertEqual(db.next_due("2026-10-20 18:00", "day", now), "2026-10-21 18:00")
        self.assertEqual(db.next_due("2026-10-20 09:00", "week", now), "2026-10-27 09:00")
        self.assertEqual(db.next_due("2026-10-20 09:00", "month", now), "2026-11-20 09:00")
        self.assertEqual(db.next_due("2026-10-20 09:00", "year", now), "2027-10-20 09:00")

    def test_done_early_gives_next_period(self):
        """Выполнили заранее (срок ещё впереди) — следующий срок через период после срока."""
        now = datetime(2026, 10, 1)
        self.assertEqual(db.next_due("2026-10-20 09:00", "week", now), "2026-10-27 09:00")

    def test_late_by_several_periods_skips_missed(self):
        now = datetime(2026, 10, 21, 12, 0)
        self.assertEqual(db.next_due("2026-09-01 10:00", "week", now), "2026-10-27 10:00")
        self.assertEqual(db.next_due("2026-10-01 10:00", "day", now), "2026-10-22 10:00")
        self.assertEqual(db.next_due("2020-05-15 10:00", "year", now), "2027-05-15 10:00")

    def test_late_monthly_31st_not_lost(self):
        """Пропустили несколько месяцев — 31-е число не «съезжает» на 28-е."""
        now = datetime(2026, 3, 5)
        self.assertEqual(db.next_due("2026-01-31 10:00", "month", now), "2026-03-31 10:00")
        now = datetime(2026, 2, 28, 10, 0)  # ровно в срок февраля — он уже не «впереди»
        self.assertEqual(db.next_due("2026-01-31 10:00", "month", now), "2026-03-31 10:00")

    def test_leap_year_late(self):
        self.assertEqual(db.next_due("2024-02-29 09:00", "year", datetime(2025, 3, 1)), "2026-02-28 09:00")
        self.assertEqual(db.next_due("2024-02-29 09:00", "year", datetime(2027, 3, 1)), "2028-02-29 09:00")

    def test_date_without_time(self):
        self.assertEqual(db.next_due("2026-10-20", "day", datetime(2026, 10, 20, 12)), "2026-10-21 00:00")

    def test_broken_values(self):
        now = datetime(2026, 10, 20)
        for due, repeat in ((None, "day"), ("", "day"), ("завтра", "week"), ("2026-13-45 10:00", "month"),
                            ("2026-10-20 10:00", None), ("2026-10-20 10:00", "hour"),
                            ("2026-10-20 10:00", ""), (12345, "day")):
            self.assertIsNone(db.next_due(due, repeat, now), (due, repeat))

    def test_far_future_due_does_not_crash(self):
        """Срок у самой границы календаря (9999 год — телефон и CSV такое пропускают):
        следующего срока нет — None, а не исключение."""
        now = datetime(2026, 10, 20)
        for repeat in db.REPEATS:
            try:
                result = db.next_due("9999-12-31 10:00", repeat, now)
            except (OverflowError, ValueError) as error:
                self.fail(f"{repeat}: {error!r}")
            self.assertIsNone(result, repeat)


class FirstStepAfterTests(unittest.TestCase):
    """db.first_step_after: число периодов считается сразу (без шага за шагом) и всегда минимальное."""

    def slow(self, start, repeat, moment):
        steps = 1
        while db.add_period(start, repeat, steps) <= moment:
            steps += 1
        return steps

    def test_same_as_step_by_step(self):
        """Сравниваем с перебором по одному шагу: оценка не перескакивает лишний период
        (особенно месяц и год — 31-е, 29 февраля, время суток в тот же день)."""
        starts = [datetime(2024, 2, 29, 9, 0), datetime(2026, 1, 31, 10, 0), datetime(2025, 12, 31, 23, 59),
                  datetime(2026, 6, 15, 0, 0), datetime(2020, 6, 1, 10, 0), datetime(2026, 10, 20, 18, 0)]
        moments = [datetime(2026, 10, 20, 9, 59), datetime(2026, 10, 20, 10, 0), datetime(2026, 10, 20, 10, 1),
                   datetime(2026, 2, 28, 10, 0), datetime(2026, 3, 1), datetime(2028, 2, 29, 9, 0),
                   datetime(2027, 1, 31, 9, 59), datetime(2026, 1, 1), datetime(2026, 6, 15, 0, 0),
                   datetime(2030, 12, 31, 23, 59), datetime(2019, 1, 1)]
        for start in starts:
            for moment in moments:
                for repeat in db.REPEATS:
                    with self.subTest(start=start, moment=moment, repeat=repeat):
                        steps = db.first_step_after(start, repeat, moment)
                        self.assertEqual(steps, self.slow(start, repeat, moment))
                        self.assertGreater(db.add_period(start, repeat, steps), moment)
                        if steps > 1:
                            self.assertLessEqual(db.add_period(start, repeat, steps - 1), moment)

    def test_moment_before_start(self):
        self.assertEqual(db.first_step_after(datetime(2026, 10, 20), "day", datetime(2020, 1, 1)), 1)

    def test_years_overdue_fast_and_right(self):
        """Ежедневная задача, просроченная на 120 лет, — ответ сразу (раньше был цикл на десятки тысяч
        шагов с потолком 100000)."""
        import time as time_module
        start = datetime(1906, 3, 1, 9, 0)
        moment = datetime(2026, 10, 21, 12, 0)
        began = time_module.perf_counter()
        for _ in range(1000):
            steps = db.first_step_after(start, "day", moment)
        self.assertLess(time_module.perf_counter() - began, 1.0)
        self.assertEqual(db.add_period(start, "day", steps), datetime(2026, 10, 22, 9, 0))
        self.assertEqual(db.next_due("1906-03-01 09:00", "day", moment), "2026-10-22 09:00")
        self.assertEqual(db.next_due("1906-03-31 09:00", "month", moment), "2026-10-31 09:00")
        self.assertEqual(db.next_due("1904-02-29 09:00", "year", moment), "2027-02-28 09:00")
        self.assertEqual(db.next_due("1906-03-01 09:00", "week", moment),
                         db.add_period(start, "week", self.slow(start, "week", moment)).strftime("%Y-%m-%d %H:%M"))


class RepeatTextTests(unittest.TestCase):
    def test_text(self):
        self.assertEqual(db.repeat_text("week", "2026-12-31"), "каждую неделю до 31.12.2026")
        self.assertEqual(db.repeat_text("day"), "каждый день")
        self.assertEqual(db.repeat_text("month", None), "каждый месяц")
        self.assertEqual(db.repeat_text("year", ""), "каждый год")

    def test_broken(self):
        self.assertEqual(db.repeat_text(None), "")
        self.assertEqual(db.repeat_text("hour", "2026-12-31"), "")
        self.assertEqual(db.repeat_text("day", "31.12.2026"), "каждый день")  # дата испорчена — без «до»


# ---------- база ----------

class RepeatDbTests(TempDir):
    def setUp(self):
        super().setUp()
        self.conn = db.connect(self.dir / "a.db")

    def tearDown(self):
        self.conn.close()
        super().tearDown()

    def task(self, title="Отчёт", due=None, repeat="week", until=None):
        tid = db.add_task(self.conn, title)
        db.update_task(self.conn, tid, title, due, None)
        db.set_repeat(self.conn, tid, repeat, until)
        return tid

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

    def row(self, tid, columns="*"):
        self.conn.row_factory = sqlite3.Row
        try:
            return self.conn.execute(f"SELECT {columns} FROM tasks WHERE id = ?", (tid,)).fetchone()
        finally:
            self.conn.row_factory = None

    def test_old_database_gets_columns(self):
        path = self.dir / "old.db"
        old = sqlite3.connect(path)
        old.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                    "done INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        old.execute("INSERT INTO tasks (title) VALUES ('старая')")
        old.commit()
        old.close()
        conn = db.connect(path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            self.assertTrue({"repeat", "repeat_until", "repeat_next"} <= columns)
            self.assertEqual(db.get_repeat(conn, 1), (None, None))
            self.assertEqual(db.repeat_infos(conn), {})
            db.set_done(conn, 1, True)  # без повтора — ничего не появляется
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
        finally:
            conn.close()

    def test_set_get_repeat(self):
        tid = self.task(due="2026-10-20 09:00", repeat="month", until="2026-12-31")
        self.assertEqual(db.get_repeat(self.conn, tid), ("month", "2026-12-31"))
        self.assertEqual(db.repeat_infos(self.conn), {tid: ("month", "2026-12-31", 0)})
        db.set_repeat(self.conn, tid, "day")
        self.assertEqual(db.get_repeat(self.conn, tid), ("day", None))
        db.set_repeat(self.conn, tid, None, "2026-12-31")  # без повтора «до» не хранится
        self.assertEqual(db.get_repeat(self.conn, tid), (None, None))
        self.assertEqual(db.repeat_infos(self.conn), {})
        db.set_repeat(self.conn, tid, "hour")  # неизвестное значение — как «не повторять»
        self.assertEqual(db.get_repeat(self.conn, tid), (None, None))
        self.assertEqual(db.get_repeat(self.conn, 9999), (None, None))

    def test_repeat_infos_has_next(self):
        """Третье значение repeat_infos — есть ли следующая задача (удалённая не считается)."""
        tid = self.task(due="2026-10-20 09:00", repeat="day")
        new_id = db.repeat_task(self.conn, tid, now=datetime(2026, 10, 21))
        infos = db.repeat_infos(self.conn)
        self.assertEqual(infos[tid], ("day", None, 1))
        self.assertEqual(infos[new_id], ("day", None, 0))
        db.delete_task(self.conn, new_id)
        self.assertEqual(db.repeat_infos(self.conn), {tid: ("day", None, 0)})

    def test_set_repeat_bumps_version(self):
        tid = self.task(due="2026-10-20 09:00", repeat=None)
        before = db.task_meta(self.conn, tid)["version"]
        db.set_repeat(self.conn, tid, "week", by="Анна")
        meta = db.task_meta(self.conn, tid)
        self.assertEqual((meta["version"], meta["updated_by"]), (before + 1, "Анна"))

    def test_broken_value_in_file_ignored(self):
        """В файле испорчено значение повтора (например, записала другая версия) — не повтор."""
        tid = self.task(due="2026-10-20 09:00")
        self.conn.execute("UPDATE tasks SET repeat = 'fortnight' WHERE id = ?", (tid,))
        self.conn.commit()
        self.assertEqual(db.get_repeat(self.conn, tid), (None, None))
        self.assertEqual(db.repeat_infos(self.conn), {})
        self.assertIsNone(db.repeat_task(self.conn, tid, now=datetime(2026, 10, 21)))
        self.assertEqual(self.count(), 1)

    def test_repeat_task_copies_fields(self):
        tid = db.add_task(self.conn, "Отчёт", created_by="Анна")
        db.update_task(self.conn, tid, "Отчёт", "2026-10-20 09:00", 60, True, True, "описание")
        db.set_repeat(self.conn, tid, "week", "2026-12-31")
        db.set_assignee(self.conn, tid, "Борис")
        db.set_initiator(self.conn, tid, "Мария")
        uid = db.add_unit(self.conn, "Розница")
        db.set_task_unit(self.conn, tid, uid)
        db.set_mail_id(self.conn, tid, "MAIL-1", "boss@example.com")
        db.add_comment(self.conn, tid, "комментарий", by="Анна")
        db.add_attachment(self.conn, tid, "a.txt", b"data", by="Анна")
        self.conn.execute("UPDATE tasks SET reminded = 1 WHERE id = ?", (tid,))
        self.conn.commit()
        new_id = db.repeat_task(self.conn, tid, by="Анна", now=datetime(2026, 10, 21, 12))
        self.assertIsNotNone(new_id)
        new = self.row(new_id)
        self.assertEqual((new["title"], new["body"], new["due_at"], new["remind_before"]),
                         ("Отчёт", "описание", "2026-10-27 09:00", 60))
        self.assertEqual((new["urgent"], new["important"], new["done"], new["reminded"]), (1, 1, 0, 0))
        self.assertEqual((new["created_by"], new["assignee"], new["initiator"], new["unit_id"]),
                         ("Анна", "Борис", "Мария", uid))
        self.assertEqual((new["repeat"], new["repeat_until"], new["repeat_next"]), ("week", "2026-12-31", None))
        self.assertEqual(new["mail_from"], "boss@example.com")
        self.assertIsNone(new["mail_id"])  # письмо одно — в Outlook оно связано со старой задачей
        self.assertIsNone(new["done_at"])
        self.assertEqual(new["status_id"], db.first_status(self.conn, False))
        self.assertEqual(new["updated_by"], "Анна")
        for table in ("comments", "attachments"):
            self.assertEqual(self.conn.execute(f"SELECT COUNT(*) FROM {table} WHERE task_id = ?",
                                               (new_id,)).fetchone()[0], 0, table)
        self.assertEqual(self.row(tid)["repeat_next"], new_id)
        # второй раз — ничего: следующая уже есть
        self.assertIsNone(db.repeat_task(self.conn, tid, now=datetime(2026, 10, 21, 12)))
        self.assertEqual(self.count(), 2)

    def test_no_repeat_or_no_due(self):
        plain = self.task(due="2026-10-20 09:00", repeat=None)
        no_due = self.task(due=None, repeat="day")
        now = datetime(2026, 10, 21)
        self.assertIsNone(db.repeat_task(self.conn, plain, now=now))
        self.assertIsNone(db.repeat_task(self.conn, no_due, now=now))
        self.assertIsNone(db.repeat_task(self.conn, 9999, now=now))  # задачи нет
        self.assertEqual(self.count(), 2)

    def test_until_inclusive(self):
        now = datetime(2026, 10, 20, 12, 0)
        on_day = self.task(due="2026-10-20 09:00", repeat="day", until="2026-10-21")
        self.assertIsNotNone(db.repeat_task(self.conn, on_day, now=now))  # 21-е — ещё можно
        last = self.task(due="2026-10-20 09:00", repeat="day", until="2026-10-20")
        self.assertIsNone(db.repeat_task(self.conn, last, now=now))
        weekly = self.task(due="2026-10-20 09:00", repeat="week", until="2026-10-26")
        self.assertIsNone(db.repeat_task(self.conn, weekly, now=now))  # 27-е уже после «до»

    def test_until_with_late_completion(self):
        """Выполнили с опозданием, и следующий срок после пропуска уже за «до» — новой задачи нет."""
        tid = self.task(due="2026-09-01 10:00", repeat="week", until="2026-10-01")
        self.assertIsNone(db.repeat_task(self.conn, tid, now=datetime(2026, 10, 21)))

    def test_set_done_creates_next_once(self):
        """Отметили выполненной — появилась следующая; сняли отметку и отметили снова — второй
        копии нет."""
        due = tomorrow_at()
        tid = self.task(due=stamp(due), repeat="day")
        self.assertTrue(db.set_done(self.conn, tid, True))
        self.assertEqual(self.count(), 2)
        next_id = self.row(tid)["repeat_next"]
        self.assertEqual(self.row(next_id)["due_at"], stamp(due + timedelta(days=1)))
        self.assertEqual(self.row(next_id)["done"], 0)
        db.set_done(self.conn, tid, False)
        db.set_done(self.conn, tid, True)
        self.assertEqual(self.count(), 2)
        # следующая, когда её выполнят, тоже даст следующую — цепочка продолжается
        db.set_done(self.conn, next_id, True)
        self.assertEqual(self.count(), 3)
        self.assertEqual(self.row(self.row(next_id)["repeat_next"])["due_at"], stamp(due + timedelta(days=2)))

    def test_deleted_next_is_created_again(self):
        """Следующую задачу удалили — при новой отметке «выполнено» она создаётся заново (одна)."""
        tid = self.task(due=stamp(tomorrow_at()), repeat="day")
        db.set_done(self.conn, tid, True)
        first_next = self.row(tid)["repeat_next"]
        db.delete_task(self.conn, first_next)
        db.set_done(self.conn, tid, False)
        self.assertEqual(self.count(), 1)  # снятие отметки ничего не создаёт
        db.set_done(self.conn, tid, True)
        self.assertEqual(self.count(), 2)
        again = self.row(tid)["repeat_next"]
        self.assertNotEqual(again, first_next)
        self.assertIsNotNone(self.row(again))
        db.set_done(self.conn, tid, False)
        db.set_done(self.conn, tid, True)  # следующая есть — третьей нет
        self.assertEqual(self.count(), 2)

    def test_deleted_next_direct_call(self):
        tid = self.task(due="2026-10-20 09:00", repeat="week")
        now = datetime(2026, 10, 21)
        first_next = db.repeat_task(self.conn, tid, now=now)
        db.delete_task(self.conn, first_next)
        self.assertIsNotNone(db.repeat_task(self.conn, tid, now=now))
        self.assertIsNone(db.repeat_task(self.conn, tid, now=now))
        self.assertEqual(self.count(), 2)

    def test_clearing_due_removes_repeat(self):
        """update_task без срока снимает повтор и «до»; со сроком — повтор остаётся."""
        tid = self.task(due="2026-10-20 09:00", repeat="month", until="2026-12-31")
        db.update_task(self.conn, tid, "Отчёт", "2026-11-01 09:00", None)
        self.assertEqual(db.get_repeat(self.conn, tid), ("month", "2026-12-31"))
        db.update_task(self.conn, tid, "Отчёт", None, None)
        self.assertEqual(db.get_repeat(self.conn, tid), (None, None))
        self.assertEqual(db.repeat_infos(self.conn), {})
        db.set_done(self.conn, tid, True)
        self.assertEqual(self.count(), 1)

    def test_clearing_due_with_stale_version_keeps_repeat(self):
        """Правка отклонена (чужая версия) — повтор не трогается."""
        tid = self.task(due="2026-10-20 09:00", repeat="week")
        version = db.task_meta(self.conn, tid)["version"]
        self.assertFalse(db.update_task(self.conn, tid, "Отчёт", None, None, version=version - 1))
        self.assertEqual(db.get_repeat(self.conn, tid), ("week", None))

    def test_two_members_one_copy(self):
        """Двое выполнили задачу общего списка почти одновременно: второй участник успевает
        создать копию, пока первый ещё считает срок, — первый вторую копию не создаёт."""
        tid = self.task(due="2026-10-20 09:00", repeat="week")
        other = db.connect(self.dir / "a.db")
        real_next_due = db.next_due
        inner = []
        calls = []

        def racing_next_due(due_at, repeat, now=None):
            calls.append(1)
            if len(calls) == 1:  # внутри первого вызова — второй участник
                inner.append(db.repeat_task(other, tid, by="Борис", now=datetime(2026, 10, 21)))
            return real_next_due(due_at, repeat, now)

        try:
            with mock.patch.object(db, "next_due", racing_next_due):
                first = db.repeat_task(self.conn, tid, by="Анна", now=datetime(2026, 10, 21))
        finally:
            other.close()
        self.assertIsNotNone(inner[0])
        self.assertIsNone(first)
        self.assertEqual(self.count(), 2)
        self.assertEqual(self.row(tid)["repeat_next"], inner[0])
        self.assertEqual(self.row(inner[0])["updated_by"], "Борис")

    def test_claim_marker_not_left_behind(self):
        """После создания копии в repeat_next — её id, а не временная метка -1."""
        tid = self.task(due="2026-10-20 09:00", repeat="week")
        new_id = db.repeat_task(self.conn, tid, now=datetime(2026, 10, 21))
        self.assertEqual(self.row(tid)["repeat_next"], new_id)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tasks WHERE repeat_next = -1").fetchone()[0], 0)

    def test_set_task_status_return_value(self):
        tid = self.task(due=stamp(tomorrow_at()), repeat="week")
        done = db.first_status(self.conn, True)
        undone = db.first_status(self.conn, False)
        self.assertTrue(db.set_task_status(self.conn, tid, done))
        self.assertFalse(db.set_task_status(self.conn, tid, done))  # уже выполнена
        self.assertEqual(self.count(), 2)
        self.assertFalse(db.set_task_status(self.conn, tid, undone))
        self.assertEqual(self.count(), 2)

    def test_moving_between_undone_columns_no_copy(self):
        tid = self.task(due=stamp(tomorrow_at()), repeat="day")
        statuses = db.list_statuses(self.conn)
        db.set_task_status(self.conn, tid, statuses[1][0])  # «В работе»
        self.assertEqual(self.count(), 1)

    def test_status_marked_done(self):
        """Колонку отметили «выполненной» — у невыполненных повторяющихся задач в ней
        появляются следующие (у выполненных и неповторяющихся — нет)."""
        column = db.add_status(self.conn, "Проверка", "#888888")
        due = stamp(tomorrow_at())
        rep, plain, already = (self.task("п", due, "day"), self.task("о", due, None),
                               self.task("в", due, "day"))
        db.set_done(self.conn, already, True)  # уже выполнена — следующая уже есть
        for tid in (rep, plain, already):
            db.set_task_status(self.conn, tid, column)
        self.assertEqual(self.count(), 4)  # три задачи + следующая для «в»
        db.set_status_done(self.conn, column, True, by="Анна")
        self.assertEqual(self.count(), 5)
        new_id = self.row(rep)["repeat_next"]
        self.assertIsNotNone(new_id)
        self.assertEqual(self.row(new_id)["status_id"], db.first_status(self.conn, False))
        self.assertEqual(self.row(new_id)["updated_by"], "Анна")
        self.assertIsNone(self.row(plain)["repeat_next"])
        # снять отметку с колонки и поставить снова — новых копий нет
        db.set_status_done(self.conn, column, False)
        db.set_status_done(self.conn, column, True)
        self.assertEqual(self.count(), 5)

    def test_delete_status_into_done_column(self):
        column = db.add_status(self.conn, "Временная", "#888888")
        tid = self.task(due=stamp(tomorrow_at()), repeat="month")
        db.set_task_status(self.conn, tid, column)
        db.delete_status(self.conn, column, db.first_status(self.conn, True), by="Анна")
        self.assertEqual(self.count(), 2)
        self.assertIsNotNone(self.row(tid)["repeat_next"])

    def test_delete_status_into_undone_column(self):
        column = db.add_status(self.conn, "Временная", "#888888")
        tid = self.task(due=stamp(tomorrow_at()), repeat="month")
        db.set_task_status(self.conn, tid, column)
        db.delete_status(self.conn, column, db.first_status(self.conn, False))
        self.assertEqual(self.count(), 1)

    def test_far_future_due_completion_does_not_crash(self):
        """Срок 31.12.9999 с повтором: отметить выполненной можно, ошибки нет, копии нет."""
        tid = self.task(due="9999-12-31 10:00", repeat="day")
        try:
            db.set_done(self.conn, tid, True)
        except (OverflowError, ValueError) as error:
            self.fail(f"выполнение задачи упало: {error!r}")
        self.assertEqual(self.row(tid)["done"], 1)
        self.assertEqual(self.count(), 1)

    def test_only_done_columns_board(self):
        """На доске не осталось невыполненной колонки — выполнение не падает, копия ставится
        в первую колонку (и она там тоже «выполнена»)."""
        tid = self.task(due=stamp(tomorrow_at()), repeat="day")  # в первой колонке «Новая»
        first, rest = db.list_statuses(self.conn)[0][0], db.list_statuses(self.conn)[1:]
        for sid, *_ in rest:
            db.set_status_done(self.conn, sid, True)
        self.assertEqual(self.count(), 1)  # в остальных колонках задач не было
        db.set_status_done(self.conn, first, True)
        self.assertEqual(self.count(), 2)
        new_id = self.row(tid)["repeat_next"]
        self.assertEqual(self.row(new_id)["status_id"], first)
        self.assertEqual(self.row(new_id)["done"], 1)

    def test_move_task_to_keeps_repeat(self):
        dst = db.connect(self.dir / "b.db")
        try:
            tid = self.task(due="2026-10-20 09:00", repeat="year", until="2030-01-01")
            new_id = db.move_task_to(self.conn, tid, dst)
            self.assertEqual(db.get_repeat(dst, new_id), ("year", "2030-01-01"))
            self.assertIsNone(dst.execute("SELECT repeat_next FROM tasks WHERE id = ?", (new_id,)).fetchone()[0])
            plain = self.task(due=None, repeat=None)
            self.assertEqual(db.get_repeat(dst, db.move_task_to(self.conn, plain, dst)), (None, None))
        finally:
            dst.close()


# ---------- телефон ----------

class RepeatPhoneTests(unittest.TestCase):
    """Отметка «выполнено» с телефона создаёт следующую задачу так же, как в окне."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="todoro-phone-"))
        self.addCleanup(self.remove_dir)
        self.prefs_path = self.dir / "todoro.db"
        prefs = db.connect(self.prefs_path)
        db.set_setting(prefs, "user_name", "Аня")
        self.token = phone.new_token(prefs)
        prefs.close()
        self.server = phone.Server(0, self.token, self.prefs_path)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def remove_dir(self):
        gc.collect()
        shutil.rmtree(self.dir, ignore_errors=True)

    def call(self, method, path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(self.base + path, data=body, method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def make_task(self, due, repeat):
        status, answer = self.call("POST", "/api/v1/lists/personal/tasks", {"title": "Полить цветы", "due_at": due})
        self.assertEqual(status, 201, answer)
        task = answer["task"]
        conn = db.connect(self.prefs_path)
        try:
            db.set_repeat(conn, task["id"], repeat)
            version = db.task_meta(conn, task["id"])["version"]
        finally:
            conn.close()
        return task["id"], version

    def titles_and_dues(self):
        conn = db.connect(self.prefs_path)
        try:
            return conn.execute("SELECT id, done, due_at, repeat FROM tasks ORDER BY id").fetchall()
        finally:
            conn.close()

    def test_done_from_phone(self):
        due = tomorrow_at()
        tid, version = self.make_task(stamp(due), "week")
        status, answer = self.call("PATCH", f"/api/v1/lists/personal/tasks/{tid}",
                                   {"version": version, "done": True})
        self.assertEqual(status, 200, answer)
        rows = self.titles_and_dues()
        self.assertEqual(len(rows), 2, rows)
        self.assertEqual(rows[0][:2], (tid, 1))
        self.assertEqual(rows[1][1:], (0, stamp(due + timedelta(weeks=1)), "week"))
        # телефон снимает отметку и ставит снова — вторая копия не появляется
        for done in (False, True):
            conn = db.connect(self.prefs_path)
            version = db.task_meta(conn, tid)["version"]
            conn.close()
            status, answer = self.call("PATCH", f"/api/v1/lists/personal/tasks/{tid}",
                                       {"version": version, "done": done})
            self.assertEqual(status, 200, answer)
        self.assertEqual(len(self.titles_and_dues()), 2)
        # новая задача видна телефону при следующей синхронизации
        status, answer = self.call("GET", "/api/v1/lists/personal")
        self.assertEqual(status, 200, answer)
        self.assertIn(rows[1][0], [t["id"] for t in answer["tasks"]])

    def test_done_by_status_from_phone(self):
        tid, version = self.make_task(stamp(tomorrow_at()), "day")
        conn = db.connect(self.prefs_path)
        done_status = db.first_status(conn, True)
        conn.close()
        status, answer = self.call("PATCH", f"/api/v1/lists/personal/tasks/{tid}",
                                   {"version": version, "status_id": done_status})
        self.assertEqual(status, 200, answer)
        self.assertEqual(len(self.titles_and_dues()), 2)

    def test_done_from_phone_far_future_due(self):
        """Срок 31.12.9999 (телефон такой принимает) и повтор — отметка «выполнено» проходит."""
        tid, version = self.make_task("9999-12-31 10:00", "day")
        status, answer = self.call("PATCH", f"/api/v1/lists/personal/tasks/{tid}",
                                   {"version": version, "done": True})
        self.assertEqual(status, 200, answer)

    def test_phone_clears_due_removes_repeat(self):
        """Телефон убрал срок (PATCH due_at=null) — повтор снят; правка без due_at повтор не трогает."""
        tid, version = self.make_task(stamp(tomorrow_at()), "week")
        status, answer = self.call("PATCH", f"/api/v1/lists/personal/tasks/{tid}",
                                   {"version": version, "title": "Полить кактус"})
        self.assertEqual(status, 200, answer)
        conn = db.connect(self.prefs_path)
        try:
            self.assertEqual(db.get_repeat(conn, tid), ("week", None))
        finally:
            conn.close()
        status, answer = self.call("PATCH", f"/api/v1/lists/personal/tasks/{tid}",
                                   {"version": answer["task"]["version"], "due_at": None})
        self.assertEqual(status, 200, answer)
        conn = db.connect(self.prefs_path)
        try:
            self.assertEqual(db.get_repeat(conn, tid), (None, None))
        finally:
            conn.close()

    def test_store_change_task(self):
        """То же напрямую через phone.Store.change_task (без HTTP)."""
        tid, version = self.make_task(stamp(tomorrow_at()), "month")
        store = phone.Store(self.prefs_path)
        self.addCleanup(store.close)
        item = store.find_list("personal")
        store.change_task(item, tid, {"version": version, "done": True})
        self.assertEqual(len(self.titles_and_dues()), 2)


# ---------- окно: форма, значки, письмо, правка ----------

class RepeatMarksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def fake(self, repeats=None, counts=None, mail=()):
        fake = SimpleNamespace(extra_counts=counts or {}, mail_ids=set(mail), repeats=repeats or {})
        for name in ("list_marks", "task_mark", "marks_order"):
            setattr(fake, name, getattr(self.T.TodoApp, name).__get__(fake))
        return fake

    def test_extras_mark(self):
        T = self.T
        self.assertEqual(T.extras_mark(None, repeat=True), "   " + T.REPEAT_MARK)
        self.assertEqual(T.extras_mark((1, 2), True, True), f"   {T.REPEAT_MARK}  {T.MAIL_MARK}  📎 1  💬 2")
        self.assertEqual(T.extras_mark(None), "")

    def test_list_marks_and_order(self):
        T = self.T
        app = self.fake(repeats={1: ("week", None, 0)}, counts={2: (1, 0)}, mail={1})
        self.assertEqual(app.list_marks(1), f"{T.REPEAT_MARK}  {T.MAIL_MARK}")
        self.assertEqual(app.list_marks(2), "📎 1")
        self.assertEqual(app.list_marks(3), "")
        self.assertIn(T.REPEAT_MARK, app.task_mark(1))
        self.assertEqual(app.marks_order(1), (0, 0, -1, -1))
        self.assertEqual(self.fake(repeats={5: ("day", None, 1)}).marks_order(5), (0, 0, 0, -1))
        self.assertIsNone(app.marks_order(3))

    def test_email_has_repeat_line(self):
        _, body = self.T.build_email(7, "Отчёт", "Новая", "", "20.10.2026 09:00", "", "01.10.2026", False,
                                     repeat="каждую неделю до 31.12.2026")
        self.assertIn("Повтор: каждую неделю до 31.12.2026", body)
        _, body = self.T.build_email(7, "Отчёт", "Новая", "", "", "", "01.10.2026", False)
        self.assertNotIn("Повтор", body)

    def test_changed_names(self):
        names = self.T.TodoApp.CHANGED_NAMES
        self.assertIn("repeat", names)
        self.assertIn("repeat_until", names)

    def test_options_match_db(self):
        keys = {key for key in self.T.REPEAT_OPTIONS.values() if key}
        self.assertEqual(keys, set(db.REPEATS))


class RepeatApplyEditTests(TempDir):
    """Сохранение повтора из формы (TodoApp.apply_edit / form_data на подставном приложении)."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def setUp(self):
        super().setUp()
        self.conn = db.connect(self.dir / "a.db")

    def tearDown(self):
        self.conn.close()
        super().tearDown()

    def fake_app(self):
        conn = self.conn
        app = SimpleNamespace(conn=conn, list_id=None, refreshed=[], celebrated=[])
        app.created_by = lambda: None
        app.members = lambda: None
        app.task_info = lambda task_id: {"status_id": db.get_task_row(conn, task_id)[-1]}
        app.celebrate = lambda task_id: app.celebrated.append(task_id)
        app.refresh = lambda select_id=None: app.refreshed.append(select_id)
        for name in ("apply_edit", "form_data"):
            setattr(app, name, getattr(self.T.TodoApp, name).__get__(app))
        return app

    def test_save_and_load_repeat(self):
        app = self.fake_app()
        tid = db.add_task(self.conn, "Отчёт")
        data = app.form_data(tid)
        self.assertEqual((data["repeat"], data["repeat_until"]), (None, None))
        data.update(due_at="2026-10-20 09:00", repeat="month", repeat_until="2026-12-31")
        self.assertTrue(app.apply_edit(tid, data, refresh=False))
        self.assertEqual(db.get_repeat(self.conn, tid), ("month", "2026-12-31"))
        data = app.form_data(tid)
        self.assertEqual((data["repeat"], data["repeat_until"]), ("month", "2026-12-31"))
        data.update(repeat=None, repeat_until=None)
        app.apply_edit(tid, data, refresh=False)
        self.assertEqual(db.get_repeat(self.conn, tid), (None, None))

    def test_unchanged_repeat_not_rewritten(self):
        app = self.fake_app()
        tid = db.add_task(self.conn, "Отчёт")
        db.update_task(self.conn, tid, "Отчёт", "2026-10-20 09:00", None)
        db.set_repeat(self.conn, tid, "week")
        data = app.form_data(tid)
        with mock.patch.object(db, "set_repeat") as set_repeat:
            app.apply_edit(tid, data, refresh=False)
        set_repeat.assert_not_called()

    def test_result_without_repeat_keeps_it(self):
        """Старые места вызова (без ключа repeat в результате) повтор не сбрасывают."""
        app = self.fake_app()
        tid = db.add_task(self.conn, "Отчёт")
        db.update_task(self.conn, tid, "Отчёт", "2026-10-20 09:00", None)
        db.set_repeat(self.conn, tid, "week")
        data = app.form_data(tid)
        del data["repeat"], data["repeat_until"]
        app.apply_edit(tid, data, refresh=False)
        self.assertEqual(db.get_repeat(self.conn, tid), ("week", None))

    def test_set_repeat_and_done_in_one_save(self):
        """В форме сразу выбрали повтор и колонку «Выполнено» — следующая задача появляется."""
        app = self.fake_app()
        tid = db.add_task(self.conn, "Отчёт")
        data = app.form_data(tid)
        data.update(due_at=stamp(tomorrow_at()), repeat="day", status_id=db.first_status(self.conn, True))
        app.apply_edit(tid, data, refresh=False)
        self.assertEqual(app.celebrated, [tid])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 2)


class RepeatFormTests(unittest.TestCase):
    """Поля «Повторять» и «до» в форме задачи (настоящий Tk, окна за краем экрана)."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro
        cls.root = tk.Tk()
        cls.root.geometry("300x200" + OFFSCREEN)
        todoro.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.top = tk.Toplevel(self.root)
        self.top.geometry(OFFSCREEN)
        self.saved = []

    def tearDown(self):
        self.top.destroy()
        self.root.update()

    def task(self, due="2026-10-20 09:00", **extra):
        task = dict(title="Отчёт", body="", due_at=due, remind_before=None, urgent=0, important=0,
                    status_id=1, assignee=None, initiator=None, version=3)
        task.update(extra)
        return task

    def form(self, task, compact=False):
        form = self.T.TaskForm(self.top, task, STATUSES, on_save=self.saved.append,
                               on_cancel=lambda: None, compact=compact)
        form.pack(fill="both")
        self.top.update()
        return form

    def until_shown(self, form):
        """Видны ли «До» и поле даты (оба вместе)."""
        shown = (bool(form.until.winfo_manager()), bool(form.until_label.winfo_manager()))
        self.assertEqual(shown[0], shown[1], "подпись «До» и поле даты должны появляться вместе")
        return shown[0]

    def test_repeat_and_until_in_one_row(self):
        """«Повторять» и «До» — в одной строке; у «До» нет кнопки 📅."""
        for compact in (False, True):
            form = self.form(self.task(repeat="month", repeat_until="2026-12-31"), compact=compact)
            self.assertIs(form.repeat.master, form.until.master)
            self.assertIs(form.until_label.master, form.repeat.master)
            self.assertEqual(form.until_label.cget("text"), "До")
            self.assertEqual(int(form.until.grid_info()["column"]), int(form.until_label.grid_info()["column"]))
            self.assertNotEqual(int(form.until.grid_info()["column"]), int(form.repeat.grid_info()["column"]))
            self.assertEqual(int(form.until.grid_info()["row"]), int(form.repeat.grid_info()["row"]))
            self.assertEqual([w for w in form.until.winfo_children() if isinstance(w, tk.ttk.Button)], [])
            self.assertEqual(int(form.until.entry.cget("width")), 10)
            form.destroy()

    def test_option_labels(self):
        self.assertEqual(list(self.T.REPEAT_OPTIONS),
                         ["Не повторять", "Ежедневно", "Еженедельно", "Ежемесячно", "Ежегодно"])

    def test_values_and_until_visibility(self):
        for compact in (False, True):
            form = self.form(self.task(repeat="week", repeat_until="2026-12-31"), compact=compact)
            self.assertEqual(form.repeat.get(), "Еженедельно")
            self.assertTrue(self.until_shown(form))
            values = form.values()
            self.assertEqual((values["repeat"], values["repeat_until"]), ("week", "2026-12-31"))
            self.assertFalse(form.dirty())
            form.repeat.set("Не повторять")
            form.repeat_changed()
            self.assertFalse(self.until_shown(form))  # «до» спрятано
            values = form.values()
            self.assertEqual((values["repeat"], values["repeat_until"]), (None, None))
            self.assertTrue(form.dirty())
            form.repeat.set("Ежегодно")
            form.repeat_changed()
            self.assertTrue(self.until_shown(form))
            self.assertEqual(form.values()["repeat"], "year")
            form.destroy()

    def test_no_repeat_by_default(self):
        task = self.task()
        form = self.form(task)  # словарь задачи без ключей repeat — как в старых местах вызова
        self.assertEqual(form.repeat.get(), "Не повторять")
        self.assertFalse(self.until_shown(form))
        self.assertEqual((form.values()["repeat"], form.values()["repeat_until"]), (None, None))
        self.assertEqual(form.until.text.get(), "без конца")

    def test_broken_until_ignored(self):
        form = self.form(self.task(repeat="day", repeat_until="31.12.2026"))
        self.assertIsNone(form.until.value)
        self.assertIsNone(form.values()["repeat_until"])
        form.destroy()
        form = self.form(self.task(repeat="sometimes"))
        self.assertEqual(form.repeat.get(), "Не повторять")

    def test_no_due_disables_repeat(self):
        form = self.form(self.task(due=None, repeat="week"))
        self.assertEqual(str(form.repeat.cget("state")), "disabled")
        self.assertIsNone(form.values()["repeat"])
        form.destroy()
        form = self.form(self.task(repeat="week", repeat_until="2026-12-31"))
        form.date.set(None)  # убрали срок — повтор сбрасывается и «до» прячется
        self.top.update()
        self.assertEqual(form.repeat.get(), "Не повторять")
        self.assertEqual(str(form.repeat.cget("state")), "disabled")
        self.assertFalse(self.until_shown(form))
        self.assertEqual((form.values()["repeat"], form.values()["repeat_until"]), (None, None))
        form.date.set(date(2026, 11, 1))
        self.assertEqual(str(form.repeat.cget("state")), "readonly")

    def test_until_before_due_not_saved(self):
        form = self.form(self.task(repeat="week"))
        form.until.set(date(2026, 10, 19))
        with mock.patch.object(self.T.ui, "showwarning") as warning:
            form.save()
        warning.assert_called_once()
        self.assertEqual(self.saved, [])
        form.until.set(date(2026, 10, 20))  # в день срока — можно (включительно)
        with mock.patch.object(self.T.ui, "showwarning") as warning:
            form.save()
        warning.assert_not_called()
        self.assertEqual(self.saved[-1]["repeat_until"], "2026-10-20")
        form.until.set(None)  # «Без конца»
        with mock.patch.object(self.T.ui, "showwarning"):
            form.save()
        self.assertIsNone(self.saved[-1]["repeat_until"])

    def test_date_picker_without_button(self):
        """DatePicker(button=False): кнопки 📅 нет, календарь открывается щелчком по полю."""
        with_button = self.T.DatePicker(self.top)
        self.assertEqual(len([w for w in with_button.winfo_children() if isinstance(w, tk.ttk.Button)]), 1)
        self.assertEqual(int(with_button.entry.cget("width")), 11)
        with_button.destroy()
        picker = self.T.DatePicker(self.top, date(2026, 10, 20), button=False, width=10)
        picker.pack()
        self.top.update()
        self.assertEqual([w for w in picker.winfo_children() if isinstance(w, tk.ttk.Button)], [])
        self.assertEqual(int(picker.entry.cget("width")), 10)
        picker.close_if_unfocused = lambda: None
        with mock.patch.object(self.T, "close_when_inactive", lambda *a, **k: None):
            picker.entry.event_generate("<Button-1>", x=5, y=5)
            self.top.update_idletasks()
            self.assertIsNotNone(picker.popup)  # щелчок по полю открыл календарь
            picker.entry.event_generate("<Button-1>", x=5, y=5)
            self.assertIsNone(picker.popup)  # второй щелчок — закрыл

    def test_date_picker_texts(self):
        picker = self.T.DatePicker(self.top)
        self.assertEqual(picker.text.get(), "Не задан")
        picker.destroy()
        picker = self.T.DatePicker(self.top, empty="без конца", clear="Без конца")
        self.assertEqual((picker.text.get(), picker.clear), ("без конца", "Без конца"))


# ---------- календарь ----------

def row(task_id, due, done=False, title=None, urgent=0, important=0):
    return (task_id, title or f"задача {task_id}", int(done), "2026-01-01 00:00", due, None,
            urgent, important, "", 1)


class CalendarEntriesTests(unittest.TestCase):
    """CalendarView.entries: раскладка задач по дням и будущие сроки повторов (без окна)."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def entries(self, rows, repeats, first, last, overdue=()):
        """repeats — {id: (повтор, до)} или {id: (повтор, до, есть_следующая)}, как в db.repeat_infos."""
        repeats = {tid: tuple(info) + (0,) * (3 - len(info)) for tid, info in repeats.items()}
        fake = SimpleNamespace(app=SimpleNamespace(repeats=repeats),
                               MAX_PROJECTED=self.T.CalendarView.MAX_PROJECTED)
        return self.T.CalendarView.entries(fake, rows, set(overdue), first, last)

    def month_after(self, months):
        today = date.today()
        index = today.year * 12 + today.month - 1 + months
        first = date(index // 12, index % 12 + 1, 1)
        nxt = index + 1
        last = date(nxt // 12, nxt % 12 + 1, 1) - timedelta(days=1)
        return first, last

    def test_plain_tasks_by_day(self):
        rows = [row(1, "2026-10-20 09:00"), row(2, "2026-10-20 08:00", done=True), row(3, None),
                row(4, "испорчено"), row(5, "2026-11-05 10:00")]
        got = self.entries(rows, {}, date(2026, 10, 1), date(2026, 10, 31), overdue={1})
        self.assertEqual(list(got), [date(2026, 10, 20)])
        day = got[date(2026, 10, 20)]
        self.assertEqual([item[2] for item in day], [2, 1])  # по времени
        self.assertEqual(day[1][4:], (False, True, False))  # не выполнена, просрочена, не повтор
        self.assertEqual(day[0][4], True)

    def test_projections_for_repeating_task(self):
        due = tomorrow_at()
        first, last = due.date(), due.date() + timedelta(days=6)
        got = self.entries([row(1, stamp(due))], {1: ("day", None)}, first, last)
        self.assertEqual(sorted(got), [first + timedelta(days=i) for i in range(7)])
        self.assertEqual(got[first][0][6], False)  # сама задача
        for i in range(1, 7):
            items = got[first + timedelta(days=i)]
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0][2], 1)
            self.assertEqual(items[0][6], True)  # будущий повтор
            self.assertEqual(items[0][0], due.strftime("%H:%M"))

    def test_until_inclusive(self):
        due = tomorrow_at()
        until = (due.date() + timedelta(days=2)).isoformat()
        got = self.entries([row(1, stamp(due))], {1: ("day", until)}, due.date(), due.date() + timedelta(days=10))
        self.assertEqual(max(got), due.date() + timedelta(days=2))

    def test_done_task_not_projected(self):
        due = tomorrow_at()
        got = self.entries([row(1, stamp(due), done=True)], {1: ("day", None)},
                           due.date(), due.date() + timedelta(days=10))
        self.assertEqual(list(got), [due.date()])

    def test_past_dates_not_projected(self):
        """Просроченная повторяющаяся задача: в прошлом повторы не рисуются (при выполнении их
        пропустят), будущие — рисуются."""
        due = datetime.now() - timedelta(days=10)
        first, last = due.date() - timedelta(days=1), date.today() + timedelta(days=5)
        got = self.entries([row(1, stamp(due))], {1: ("day", None)}, first, last, overdue={1})
        now = datetime.now()
        projected = [day for day, items in got.items() for item in items if item[6]]
        self.assertTrue(projected)
        for day in projected:
            item = next(i for i in got[day] if i[6])
            self.assertGreater(datetime.combine(day, datetime.strptime(item[0], "%H:%M").time()), now)
        self.assertIn(due.date(), got)  # сама просроченная задача — на своём дне
        self.assertTrue(got[due.date()][0][5])

    def test_next_exists_not_projected(self):
        """Отметку сняли после создания копии: у старой задачи будущие повторы не рисуются
        (их рисует копия), иначе в календаре было бы по два повтора на день."""
        due = tomorrow_at()
        nxt = due + timedelta(days=1)
        rows = [row(1, stamp(due)), row(2, stamp(nxt))]
        got = self.entries(rows, {1: ("day", None, 1), 2: ("day", None, 0)}, due.date(),
                           due.date() + timedelta(days=5))
        for day, items in got.items():
            self.assertNotIn(1, [i[2] for i in items if i[6]], day)
            self.assertLessEqual(len(items), 1, day)
        self.assertEqual([i[2] for i in got[due.date() + timedelta(days=3)]], [2])

    def test_no_repeat_info_no_projection(self):
        due = tomorrow_at()
        got = self.entries([row(1, stamp(due))], {}, due.date(), due.date() + timedelta(days=30))
        self.assertEqual(list(got), [due.date()])

    def test_real_task_before_projection_in_day(self):
        """В одном дне сначала настоящие задачи, потом будущие повторы."""
        due = tomorrow_at(hour=12)
        nxt = due + timedelta(days=1)
        rows = [row(1, stamp(due)), row(2, stamp(nxt.replace(hour=18)))]
        got = self.entries(rows, {1: ("day", None)}, due.date(), nxt.date())
        self.assertEqual([(i[2], i[6]) for i in got[nxt.date()]], [(2, False), (1, True)])

    def test_monthly_31st_projection(self):
        due = datetime(2027, 1, 31, 10, 0)
        got = self.entries([row(1, stamp(due))], {1: ("month", None)}, date(2027, 2, 1), date(2027, 3, 31))
        self.assertEqual(sorted(got), [date(2027, 2, 28), date(2027, 3, 31)])

    def test_far_month_daily_projection(self):
        """Ежедневная задача и месяц через полтора года: повторы этого месяца видны (каждый день)."""
        due = tomorrow_at()
        first, last = self.month_after(18)
        got = self.entries([row(1, stamp(due))], {1: ("day", None)}, first, last)
        self.assertEqual(len(got), (last - first).days + 1)

    def test_long_overdue_daily_projection(self):
        """Ежедневная задача просрочена больше чем на год: в текущем месяце будущие повторы видны."""
        due = datetime.now() - timedelta(days=500)
        first, last = self.month_after(0)
        got = self.entries([row(1, stamp(due))], {1: ("day", None)}, first, last, overdue={1})
        projected = [day for day, items in got.items() if any(i[6] for i in items)]
        self.assertTrue(projected, "будущие повторы не показаны")


class CalendarViewTests(unittest.TestCase):
    """Отрисовка календаря без показа на экране (окно за краем экрана)."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro
        cls.root = tk.Tk()
        cls.root.geometry("900x700" + OFFSCREEN)
        todoro.setup_style(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.calls = []
        app = SimpleNamespace(repeats={}, root=self.root)
        app.select_task = lambda tid: self.calls.append(("select", tid))
        app.clear_selection = lambda: self.calls.append(("clear",))
        app.new_task_on = lambda day: self.calls.append(("new", day))
        app.edit = lambda: self.calls.append(("edit",))
        app.show_menu_for = lambda *a: self.calls.append(("menu",))
        self.app = app
        self.view = self.T.CalendarView(self.root, app)
        self.view.pack(fill="both", expand=True)
        self.root.update()

    def tearDown(self):
        self.view.destroy()
        self.root.update()

    def test_render_select_and_navigation(self):
        due = tomorrow_at()
        self.app.repeats = {1: ("day", None, 0)}
        self.view.month = due.date().replace(day=1)
        rows = [row(1, stamp(due), title="Полить цветы"), row(2, None)]
        self.view.render(STATUSES, rows, set())
        self.root.update()
        self.assertIn(str(due.year), self.view.title.cget("text"))
        self.assertIn("Без срока: 1", self.view.note.cget("text"))
        self.assertEqual(len(self.view.chips[1]), 1)  # сама задача; повторы в chips не попадают
        self.view.select(1)
        chip = self.view.chips[1][0]
        self.assertEqual(str(chip.cget("bg")), self.T.ACCENT_SOFT)
        self.view.select(None)
        self.assertNotEqual(str(chip.cget("bg")), self.T.ACCENT_SOFT)
        month = self.view.month
        self.view.shift_month(1)
        self.assertNotEqual(self.view.month, month)
        self.view.shift_month(-1)
        self.assertEqual(self.view.month, month)
        self.view.draw()
        self.view.month = date(2026, 12, 1)
        self.view.shift_month(1)
        self.assertEqual(self.view.month, date(2027, 1, 1))
        self.assertEqual(self.view.title.cget("text"), f"{self.T.MONTHS[0]} 2027")  # заголовок — сразу
        self.view.draw()
        self.view.shift_month(-1)
        self.assertEqual(self.view.month, date(2026, 12, 1))
        self.view.go_today()
        self.assertEqual(self.view.month, date.today().replace(day=1))
        self.view.set_mark(1, "x")  # значков нет — и ошибки тоже

    def test_wheel_over_day_cell_turns_month(self):
        """Колёсико над ячейкой дня листает месяц (вниз — следующий, вверх — предыдущий)."""
        self.view.month = date(2026, 12, 1)
        self.view.render(STATUSES, [], set())
        self.root.update()
        cells = [w for w in self.view.days.winfo_children() if isinstance(w, tk.Frame)]
        self.assertTrue(cells)
        cells[10].event_generate("<MouseWheel>", delta=-120)
        self.assertEqual(self.view.month, date(2027, 1, 1))
        self.view.draw()  # дни перерисованы — привязка есть и у новых ячеек
        self.root.update()
        cells = [w for w in self.view.days.winfo_children() if isinstance(w, tk.Frame)]
        cells[3].winfo_children()[0].event_generate("<MouseWheel>", delta=120)  # над числом дня
        self.assertEqual(self.view.month, date(2026, 12, 1))
        self.assertEqual(self.view.wheel(SimpleNamespace(delta=120)), "break")
        self.assertEqual(self.view.month, date(2026, 11, 1))

    def test_wheel_between_days_after_many_redraws(self):
        """После нескольких перерисовок один щелчок колёсика (над линией между днями, то есть над
        самой сеткой дней) листает ровно на один месяц, а не на столько, сколько было перерисовок."""
        self.view.month = date(2026, 12, 1)
        self.view.render(STATUSES, [], set())
        for _ in range(3):
            self.view.draw()
        self.root.update()
        self.view.days.event_generate("<MouseWheel>", delta=-120)
        self.assertEqual(self.view.month, date(2027, 1, 1))

    def test_fit_before_shown(self):
        view = self.T.CalendarView(self.root, self.app)  # не размещён — высоты нет
        try:
            self.assertEqual(view.fit(), 3)
        finally:
            view.destroy()

    def test_many_tasks_in_day_show_more_link(self):
        due = tomorrow_at()
        self.view.month = due.date().replace(day=1)
        rows = [row(i, stamp(due)) for i in range(1, 30)]
        self.view.render(STATUSES, rows, set())
        self.root.update()
        fit = self.view.fit()
        shown = sum(len(chips) for chips in self.view.chips.values())
        self.assertLess(shown, 29)
        self.assertEqual(shown, max(fit - 1, 0))
        labels = [w.cget("text") for w in self.view.days.winfo_children()
                  for w in w.winfo_children() if isinstance(w, tk.Label)]
        self.assertIn(f"ещё {29 - shown}…", labels)


if __name__ == "__main__":
    unittest.main()
