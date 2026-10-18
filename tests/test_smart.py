"""Тесты умных подсказок (smart.py) и того, как их применяет окно (без окон Tk)."""

import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import smart  # noqa: E402
from tests.test_core import TempDir  # noqa: E402

# Воскресенье, полдень
NOW = datetime(2026, 10, 18, 12, 0)
TODAY = NOW.date()


def row(task_id, title, urgent=0, important=0, body=None, done=0):
    """Строка в виде db.list_tasks."""
    return (task_id, title, done, "2026-01-01 10:00", None, None, urgent, important, body, 1)


def when(text, now=NOW):
    return smart.parse_when(text, now)


class SuggestTitlesTests(unittest.TestCase):
    def test_starts_with_first_then_frequency_then_fresh(self):
        rows = [row(1, "Позвонить маме"), row(2, "Позвонить в бухгалтерию"),
                row(3, "позвонить в бухгалтерию"), row(4, "Срочно позвонить юристу"),
                row(5, "Позвонить врачу")]
        found = smart.suggest_titles("позв", rows)
        # «в бухгалтерию» — дважды (дубликаты схлопнуты, взят свежий вариант написания)
        self.assertEqual(found[0], "позвонить в бухгалтерию")
        self.assertEqual(found[1:3], ["Позвонить врачу", "Позвонить маме"])
        self.assertEqual(found[3], "Срочно позвонить юристу")  # «содержит» — после «начинается»
        self.assertEqual(len(found), 4)

    def test_duplicates_ignore_case_and_yo(self):
        rows = [row(1, "Сдать отчёт"), row(2, "сдать ОТЧЕТ"), row(3, "Сдать  отчет")]
        self.assertEqual(len(smart.suggest_titles("сда", rows)), 1)

    def test_all_words_last_is_prefix(self):
        rows = [row(1, "Отправить счёт клиенту Иванову"), row(2, "Отправить письмо")]
        self.assertEqual(smart.suggest_titles("счет клиен", rows), ["Отправить счёт клиенту Иванову"])
        self.assertEqual(smart.suggest_titles("счет письм", rows), [])

    def test_typed_text_itself_not_suggested(self):
        rows = [row(1, "Купить хлеб"), row(2, "Купить хлеб и молоко")]
        self.assertEqual(smart.suggest_titles("купить хлеб", rows), ["Купить хлеб и молоко"])

    def test_short_or_empty_query(self):
        rows = [row(1, "Позвонить")]
        self.assertEqual(smart.suggest_titles("П", rows), [])
        self.assertEqual(smart.suggest_titles("", rows), [])
        self.assertEqual(smart.suggest_titles("   ", rows), [])
        self.assertEqual(smart.suggest_titles("!!", rows), [])

    def test_limit_and_empty_titles(self):
        rows = [row(i, f"Задача номер {i}") for i in range(1, 20)] + [row(30, None), row(31, "")]
        self.assertEqual(len(smart.suggest_titles("зад", rows)), 5)
        self.assertEqual(len(smart.suggest_titles("зад", rows, limit=2)), 2)
        self.assertEqual(smart.suggest_titles("зад", []), [])


class ParseWhenDayTests(unittest.TestCase):
    def test_relative_days(self):
        self.assertEqual(when("Сдать отчёт завтра"), ("Сдать отчёт", TODAY + timedelta(1), None))
        self.assertEqual(when("Сдать отчёт сегодня"), ("Сдать отчёт", TODAY, None))
        self.assertEqual(when("Сдать отчёт послезавтра"), ("Сдать отчёт", TODAY + timedelta(2), None))
        self.assertEqual(when("Сдать отчёт до завтра"), ("Сдать отчёт", TODAY + timedelta(1), None))
        self.assertEqual(when("Сдать отчёт на завтра"), ("Сдать отчёт", TODAY + timedelta(1), None))
        # исходный текст с большой буквы — очищенное название тоже
        self.assertEqual(when("К завтра сдать отчёт"), ("Сдать отчёт", TODAY + timedelta(1), None))
        self.assertEqual(when("Завтра позвонить маме"), ("Позвонить маме", TODAY + timedelta(1), None))
        self.assertEqual(when("завтра позвонить маме")[0], "позвонить маме")
        # с маленькой буквы в середине — срок, с большой без предлога — имя
        self.assertEqual(when("Фильм сегодня")[1], TODAY)
        self.assertEqual(when("Фильм до Сегодня")[1], TODAY)

    def test_in_days_and_weeks(self):
        self.assertEqual(when("Ответ через 3 дня")[1], TODAY + timedelta(3))
        self.assertEqual(when("Ответ через три дня")[1], TODAY + timedelta(3))
        self.assertEqual(when("Ответ через день")[1], TODAY + timedelta(1))
        self.assertEqual(when("Ответ через 10 дней")[1], TODAY + timedelta(10))
        self.assertEqual(when("Ответ через неделю"), ("Ответ", TODAY + timedelta(7), None))
        self.assertEqual(when("Ответ через две недели")[1], TODAY + timedelta(14))
        self.assertEqual(when("Ответ через 2 недели")[1], TODAY + timedelta(14))

    def test_weekdays_next_not_today(self):
        self.assertEqual(when("Встреча в пятницу"), ("Встреча", date(2026, 10, 23), None))
        self.assertEqual(when("Встреча во вторник")[1], date(2026, 10, 20))
        self.assertEqual(when("Встреча в понедельник")[1], date(2026, 10, 19))
        self.assertEqual(when("Встреча в среду")[1], date(2026, 10, 21))
        self.assertEqual(when("Встреча в субботу")[1], date(2026, 10, 24))
        # сегодня воскресенье — «в воскресенье» значит следующее
        self.assertEqual(when("Встреча в воскресенье")[1], date(2026, 10, 25))
        self.assertEqual(when("Встреча на пятницу")[1], date(2026, 10, 23))
        self.assertEqual(when("Встреча до пятницы")[1], date(2026, 10, 23))
        # без предлога день недели — не срок
        self.assertIsNone(when("Встреча пятница"))

    def test_weekday_dative_only_after_k(self):
        self.assertEqual(when("Отчёт к пятнице"), ("Отчёт", date(2026, 10, 23), None))
        self.assertEqual(when("Отчёт ко вторнику")[1], date(2026, 10, 20))
        self.assertEqual(when("Отчёт к среде")[1], date(2026, 10, 21))
        self.assertIsNone(when("Работа в среде разработки"))

    def test_numeric_dates(self):
        self.assertEqual(when("Оплатить 25.10"), ("Оплатить", date(2026, 10, 25), None))
        self.assertEqual(when("Оплатить до 25.10.2027")[1], date(2027, 10, 25))
        self.assertEqual(when("Оплатить 25.10.27")[1], date(2027, 10, 25))
        self.assertEqual(when("Оплатить 01.10")[1], date(2027, 10, 1))  # прошла — следующий год
        self.assertIsNone(when("Оплатить 01.10.2026"))  # год сказан и уже прошёл — не срок
        self.assertEqual(when("Оплатить 18.10.2026")[1], TODAY)
        self.assertEqual(when("Оплатить 18.10")[1], TODAY)
        self.assertEqual(when("Оплатить 5.11")[1], date(2026, 11, 5))

    def test_numeric_date_position(self):
        """Без предлога дата — только в конце; с предлогом — где угодно."""
        self.assertIsNone(when("Оплатить 25.10 счёт"))
        self.assertEqual(when("Оплатить до 25.10 счёт"), ("Оплатить счёт", date(2026, 10, 25), None))
        self.assertEqual(when("Оплатить на 25.10 счёт")[1], date(2026, 10, 25))
        self.assertEqual(when("Оплатить счёт 25.10.")[1], date(2026, 10, 25))
        self.assertIsNone(when("Обновить Python до 3.12"))
        self.assertIsNone(when("Обновить до 3.12.1"))

    def test_not_due_after_words(self):
        for text in ("Протокол от 1 мая", "Отчёт с 25.10", "Отчёт за 25.10", "Поговорить про завтра",
                     "Отчёт после 25.10", "Отчёт со вторника"):
            with self.subTest(text=text):
                self.assertIsNone(when(text))

    def test_quoted_text_skipped(self):
        self.assertIsNone(when("Найти книгу «Завтра была война»"))
        self.assertIsNone(when('Посмотреть "в пятницу" фильм'))
        self.assertEqual(when("Найти книгу «Завтра была война» завтра")[1], TODAY + timedelta(1))

    def test_invalid_date_skipped(self):
        self.assertIsNone(when("Оплатить 31.02"))
        self.assertIsNone(when("Оплатить 40.13"))
        # неверная дата пропущена, следующий способ всё равно срабатывает
        self.assertEqual(when("Оплатить 31.02 завтра")[1], TODAY + timedelta(1))

    def test_month_names(self):
        self.assertEqual(when("Отпуск 15 марта"), ("Отпуск", date(2027, 3, 15), None))
        self.assertEqual(when("Отпуск 20 октября")[1], date(2026, 10, 20))
        self.assertEqual(when("Отпуск к 15 марта"), ("Отпуск", date(2027, 3, 15), None))
        self.assertIsNone(when("Отпуск 30 февраля"))

    def test_first_day_wins(self):
        self.assertEqual(when("Сдать завтра, а не в пятницу")[1], TODAY + timedelta(1))


class ParseWhenTimeTests(unittest.TestCase):
    def test_in_hours_and_minutes(self):
        self.assertEqual(when("Перезвонить через 2 часа"), ("Перезвонить", TODAY, time(14, 0)))
        self.assertEqual(when("Перезвонить через час"), ("Перезвонить", TODAY, time(13, 0)))
        self.assertEqual(when("Перезвонить через два часа")[2], time(14, 0))
        now = datetime(2026, 10, 18, 12, 3, 40)
        self.assertEqual(when("Перезвонить через 30 минут", now)[1:], (TODAY, time(12, 35)))
        self.assertEqual(when("Перезвонить через 5 мин", NOW)[2], time(12, 5))

    def test_in_hours_crosses_midnight(self):
        now = datetime(2026, 10, 18, 23, 0)
        self.assertEqual(when("Перезвонить через 2 часа", now)[1:], (TODAY + timedelta(1), time(1, 0)))
        now = datetime(2026, 10, 18, 23, 58)
        self.assertEqual(when("Перезвонить через 1 минуту", now)[1:], (TODAY + timedelta(1), time(0, 0)))

    def test_clock(self):
        self.assertEqual(when("Созвон завтра в 10:30"), ("Созвон", TODAY + timedelta(1), time(10, 30)))
        self.assertEqual(when("Созвон к 9:15")[2], time(9, 15))
        self.assertEqual(when("Созвон в 10.30")[2], time(10, 30))
        self.assertEqual(when("Созвон в пятницу 18:00")[1:], (date(2026, 10, 23), time(18, 0)))

    def test_clock_without_day_today_or_tomorrow(self):
        self.assertEqual(when("Созвон в 15:00")[1:], (TODAY, time(15, 0)))
        self.assertEqual(when("Созвон в 10:30")[1:], (TODAY + timedelta(1), time(10, 30)))
        self.assertEqual(when("Созвон в 12:00")[1:], (TODAY + timedelta(1), time(12, 0)))

    def test_invalid_clock(self):
        self.assertIsNone(when("Созвон в 25:00"))
        self.assertIsNone(when("Созвон в 10:75"))

    def test_midnight(self):
        self.assertEqual(when("Позвонить в 12 ночи")[1:], (TODAY + timedelta(1), time(0, 0)))
        self.assertEqual(when("Позвонить завтра в 12 ночи")[1:], (TODAY + timedelta(1), time(0, 0)))
        self.assertEqual(when("Позвонить в 12 дня")[1:], (TODAY + timedelta(1), time(12, 0)))

    def test_hour_only(self):
        self.assertEqual(when("Сдать отчёт завтра в 10"), ("Сдать отчёт", TODAY + timedelta(1), time(10, 0)))
        self.assertEqual(when("Позвонить в 3 дня")[1:], (TODAY, time(15, 0)))
        self.assertEqual(when("Позвонить в 8 вечера")[2], time(20, 0))
        self.assertEqual(when("Позвонить в 8 утра")[1:], (TODAY + timedelta(1), time(8, 0)))
        self.assertEqual(when("Позвонить в 16 часов")[2], time(16, 0))
        self.assertEqual(when("Позвонить в 16")[1:], (TODAY, time(16, 0)))  # в конце
        self.assertIsNone(when("Позвонить в 25"))

    def test_small_hour_needs_day(self):
        """«в 3» без уточнения: с днём — 15:00, без дня — не время; «в 0» — не время."""
        self.assertEqual(when("Позвонить завтра в 3"), ("Позвонить", TODAY + timedelta(1), time(15, 0)))
        self.assertEqual(when("Позвонить завтра в 7")[2], time(19, 0))
        self.assertEqual(when("Позвонить завтра в 8")[2], time(8, 0))
        self.assertEqual(when("Позвонить завтра в 3 утра")[2], time(3, 0))
        self.assertEqual(when("Позвонить завтра в 3 часа")[2], time(3, 0))
        self.assertEqual(when("Позвонить в 2 ночи")[1:], (TODAY + timedelta(1), time(2, 0)))
        self.assertEqual(when("Позвонить завтра в 0"), ("Позвонить в 0", TODAY + timedelta(1), None))
        self.assertIsNone(when("Позвонить в 3"))
        self.assertIsNone(when("Позвонить в 0"))

    def test_parts_of_day(self):
        self.assertEqual(when("Пробежка утром"), ("Пробежка", TODAY + timedelta(1), time(9, 0)))
        self.assertEqual(when("Пробежка днём")[1:], (TODAY, time(14, 0)))
        self.assertEqual(when("Пробежка вечером")[1:], (TODAY, time(19, 0)))
        self.assertEqual(when("Пробежка завтра вечером")[1:], (TODAY + timedelta(1), time(19, 0)))
        self.assertIsNone(when("Проверить работу днем и ночью"))
        self.assertIsNone(when("Звонить утром или вечером"))
        self.assertEqual(when("Звонить завтра утром и вечером"),
                         ("Звонить утром и вечером", TODAY + timedelta(1), None))

    def test_used_piece_not_reused(self):
        """«к 15 марта» — это дата, а не ещё и 15:00."""
        self.assertEqual(when("Отпуск к 15 марта")[2], None)
        self.assertEqual(when("Оплатить до 25.10")[2], None)


class SameLengthTests(unittest.TestCase):
    """Буквы, которые casefold превращает в несколько («ß» → «ss», «İ» → «i̇»), не сдвигают
    позиции: вырезается именно срок, а не соседние буквы."""

    def test_same_length_norm(self):
        for text in ("Hauptstraße", "İstanbul", "ßßß Ёлка", "ﬁ ŉ ǰ", ""):
            with self.subTest(text=text):
                self.assertEqual(len(smart.same_length_norm(text)), len(text))
        self.assertEqual(smart.same_length_norm("ЁЛКА Ab"), "елка ab")

    def test_parse_keeps_positions(self):
        self.assertEqual(when("Письмо на Hauptstraße завтра в 10"),
                         ("Письмо на Hauptstraße", TODAY + timedelta(1), time(10, 0)))
        self.assertEqual(when("İstanbul тур завтра"), ("İstanbul тур", TODAY + timedelta(1), None))
        self.assertEqual(when("ßßßßßßßßßß сегодня"), ("ßßßßßßßßßß", TODAY, None))
        self.assertEqual(when("Straße İİİ до 25.10"), ("Straße İİİ", date(2026, 10, 25), None))


class ParseWhenFalsePositiveTests(unittest.TestCase):
    def test_no_false_positives(self):
        for text in ("Купить средство для мытья", "Купить 2 билета в 3 кассе", "Купить 5 машин",
                     "Обновить до 2.16", "Работа в среде разработки", "Прочитать главу 3",
                     "Версия 2.16.1", "Купить хлеб", "", "Позвонить в 25",
                     "Обновить Python до 3.12", "Обновить до 12.4", "Заказать 10.5 кг цемента",
                     "Найти книгу «Завтра была война»", "Протокол от 1 мая",
                     "Почитать про среду разработки", "Фильм Сегодня", "Проект Среда",
                     "Пятница — закрыть сделку", "Проверить работу днем и ночью",
                     "Выгрузка данных утром и вечером", "Позвонить в 3", "Разобрать почту до 5",
                     "Купить 2 в 1", "Отчёт 12.03.26"):
            with self.subTest(text=text):
                self.assertIsNone(when(text))

    def test_only_when_words(self):
        for text in ("завтра", "Завтра в 10", "в пятницу", "через 2 часа", "  до завтра  ", "утром"):
            with self.subTest(text=text):
                self.assertIsNone(when(text))

    def test_clean_title_keeps_original_case_and_punctuation(self):
        self.assertEqual(when("Сдать ОТЧЁТ Ивану, завтра")[0], "Сдать ОТЧЁТ Ивану")
        self.assertEqual(when("Встреча завтра, в 10:30 — обсудить план")[0], "Встреча, — обсудить план")
        self.assertEqual(when("Сдать отчёт в пятницу в")[0], "Сдать отчёт")

    def test_now_default(self):
        result = smart.parse_when("Сдать отчёт завтра")
        self.assertEqual(result[1], date.today() + timedelta(1))


class DescribeWhenTests(unittest.TestCase):
    def test_near_days(self):
        self.assertEqual(smart.describe_when(TODAY, None, TODAY), "сегодня")
        self.assertEqual(smart.describe_when(TODAY + timedelta(1), time(10, 0), TODAY), "завтра, 10:00")
        self.assertEqual(smart.describe_when(TODAY + timedelta(2), time(9, 5), TODAY), "послезавтра, 09:05")

    def test_far_days(self):
        self.assertEqual(smart.describe_when(date(2026, 10, 23), None, TODAY), "пт 23.10")
        self.assertEqual(smart.describe_when(date(2027, 1, 5), time(18, 30), TODAY), "вт 05.01.2027, 18:30")
        self.assertEqual(smart.describe_when(date(2026, 10, 17), None, TODAY), "сб 17.10")

    def test_default_today(self):
        self.assertEqual(smart.describe_when(date.today(), None), "сегодня")


class SimilarTests(unittest.TestCase):
    def test_similar_by_stems(self):
        rows = [row(1, "Отчет для бухгалтерии за май"), row(2, "Купить молоко"),
                row(3, "Отчёты бухгалтерии")]
        found = smart.similar("Отчёт для бухгалтерии", rows)
        self.assertEqual([r[0] for r in found], [3, 1])

    def test_same_title_excluded(self):
        rows = [row(1, "Отчёт бухгалтерии"), row(2, "отчет  бухгалтерии")]
        self.assertEqual(smart.similar("Отчет бухгалтерии", rows)[0][0], 2)
        self.assertEqual(len(smart.similar("Отчет бухгалтерии", [row(1, "Отчёт бухгалтерии")])), 0)

    def test_empty_and_stop_words(self):
        rows = [row(1, "в на и"), row(2, None), row(3, "")]
        self.assertEqual(smart.similar("в на", rows), [])
        self.assertEqual(smart.similar("Отчёт", rows), [])
        self.assertEqual(smart.similar("", [row(1, "Отчёт")]), [])
        self.assertEqual(smart.similar("2026", [row(1, "2026")]), [])


class SuggestPriorityTests(unittest.TestCase):
    def test_explicit_words(self):
        result = smart.suggest_priority("Срочно позвонить", [])
        self.assertEqual((result[0], result[1], result[3]), (True, False, True))
        result = smart.suggest_priority("Важно: встреча, ASAP", [])
        self.assertEqual((result[0], result[1], result[3]), (True, True, True))
        self.assertIn("«срочно» и «важно»", result[2])
        # точное «ASAP» — явно, «важная» рядом при этом не считается
        result = smart.suggest_priority("Важная встреча, ASAP", [])
        self.assertEqual((result[0], result[1], result[3]), (True, False, True))

    def test_word_forms_only_advice(self):
        for text, flags in (("Срочный вклад", (True, False)), ("Немедленно выйти", (True, False)),
                            ("Обязательные платежи", (False, True)), ("Важная встреча", (False, True)),
                            ("Критичный баг", (False, True))):
            with self.subTest(text=text):
                result = smart.suggest_priority(text, [])
                self.assertEqual(result, flags + ("так подсказывают слова в названии", False))

    def test_burning_not_a_sign(self):
        self.assertIsNone(smart.suggest_priority("Горит проект", []))

    def test_majority_of_similar(self):
        rows = [row(1, "Отчёт для налоговой", 1, 1), row(2, "Отчёт в налоговую", 1, 1),
                row(3, "Отчёты налоговой", 0, 0)]
        result = smart.suggest_priority("Отчёт налоговой", rows)
        self.assertEqual(result[:2], (True, True))
        self.assertFalse(result[3])
        self.assertIn("2 из 3", result[2])

    def test_need_two_similar(self):
        rows = [row(1, "Отчёт для налоговой", 1, 1), row(2, "Купить хлеб", 1, 1)]
        self.assertIsNone(smart.suggest_priority("Отчёт налоговой", rows))
        self.assertIsNone(smart.suggest_priority("Отчёт налоговой", []))

    def test_normal_majority_or_tie(self):
        normal = [row(1, "Отчёт для налоговой"), row(2, "Отчёт в налоговую"),
                  row(3, "Отчёты налоговой", 1, 1)]
        self.assertIsNone(smart.suggest_priority("Отчёт налоговой", normal))
        tie = [row(1, "Отчёт для налоговой", 1, 0), row(2, "Отчёт в налоговую", 0, 1)]
        self.assertIsNone(smart.suggest_priority("Отчёт налоговой", tie))
        half = [row(1, "Отчёт для налоговой", 1, 0), row(2, "Отчёт в налоговую", 1, 0),
                row(3, "Отчёты налоговой"), row(4, "Отчёта налоговой")]
        self.assertIsNone(smart.suggest_priority("Отчёт налоговой", half))


class SuggestStepsTests(unittest.TestCase):
    def test_body_with_steps(self):
        rows = [row(1, "Подготовить командировку в Казань", body="1. Билеты\n\n2. Гостиница\n"),
                row(2, "Подготовить командировку в Сочи", body="одна строка")]
        self.assertEqual(smart.suggest_steps("Подготовить командировку в Москву", rows),
                         ("Подготовить командировку в Казань", "1. Билеты\n\n2. Гостиница"))

    def test_no_steps(self):
        rows = [row(1, "Подготовить командировку", body="одна строка\n   \n"),
                row(2, "Подготовить командировку в Сочи", body=None),
                row(3, "Купить хлеб", body="а\nб")]
        self.assertIsNone(smart.suggest_steps("Подготовить командировку в Москву", rows))
        self.assertIsNone(smart.suggest_steps("", rows))


class ApplyWhenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def test_with_clock(self):
        self.assertEqual(self.T.apply_when(("x", date(2026, 10, 19), time(10, 30))),
                         ("2026-10-19 10:30", 15))

    def test_day_only(self):
        self.assertEqual(self.T.apply_when(("x", date(2026, 10, 19), None)), ("2026-10-19 09:00", None))


class FakeBanner:
    def __init__(self, kind=None, has_action=False):
        self.kind, self.has_action, self.shown = kind, has_action, []

    def show(self, kind, text, button=None, action=None, hide_after=None):
        self.shown.append((kind, text, button, action))

    def hide(self):
        self.hidden = getattr(self, "hidden", 0) + 1


class FakeEntry:
    def delete(self, *args):
        pass


class AddTests(TempDir):
    """TodoApp.add и smart_banner на временной базе — без окна: методы берём у TodoApp,
    всё, что рисует, — заглушки."""

    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def make_app(self, text, smart_on=True, banner_kind=None, has_action=False):
        T = self.T
        conn = db.connect(self.dir / "list.db")

        class App:
            add = T.TodoApp.add
            smart_banner = T.TodoApp.smart_banner
            smart_rows = T.TodoApp.smart_rows
            banner_busy = T.TodoApp.banner_busy
            entry_enter = T.TodoApp.entry_enter

            def entry_text(self):
                return text

            def created_by(self):
                return None

            def refresh(self, select_id=None):
                self.all_rows = db.list_tasks(self.conn)

            def show_placeholder(self):
                pass

            def finish_editing(self):
                pass

        app = App()
        app.conn, app.smart_on, app.entry = conn, smart_on, FakeEntry()
        app.title_suggest = mock.Mock(accept=mock.Mock(return_value=False))
        app.filter = mock.Mock(get=mock.Mock(return_value="Все"))
        app.banner = FakeBanner(banner_kind, has_action)
        app.quick_priority = mock.Mock()
        app.all_rows = []
        self.conns.append(conn)
        return app

    def setUp(self):
        super().setUp()
        self.conns = []

    def tearDown(self):
        for conn in self.conns:  # закрываем до удаления папки, иначе файл базы не удалится
            conn.close()
        super().tearDown()

    def last_task(self, app):
        return db.list_tasks(app.conn)[-1]

    def test_when_and_told_applied_then_undo(self):
        app = self.make_app("Срочно сдать отчёт завтра в 10:30")
        app.add()
        task = self.last_task(app)
        tomorrow = (date.today() + timedelta(1)).strftime("%Y-%m-%d")
        self.assertEqual(task[1], "Срочно сдать отчёт")
        self.assertEqual((task[4], task[5], task[6], task[7]), (tomorrow + " 10:30", 15, 1, 0))
        kind, text, button, undo = app.banner.shown[-1]
        self.assertEqual((kind, button), ("hint", "Отменить"))
        self.assertIn("напомню за 15 минут", text)
        undo()
        task = self.last_task(app)
        self.assertEqual(task[1], "Срочно сдать отчёт завтра в 10:30")
        self.assertEqual((task[4], task[5], task[6], task[7]), (None, None, 0, 0))

    def test_day_only_no_reminder(self):
        app = self.make_app("Оплатить счёт послезавтра")
        app.add()
        task = self.last_task(app)
        day = (date.today() + timedelta(2)).strftime("%Y-%m-%d")
        self.assertEqual((task[1], task[4], task[5]), ("Оплатить счёт", day + " 09:00", None))
        self.assertNotIn("напомню", app.banner.shown[-1][1])

    def test_undo_skipped_if_task_changed(self):
        """Задачу после добавления изменили — «Отменить» её не трогает (проверка version)."""
        app = self.make_app("Сдать отчёт завтра")
        app.add()
        task_id = self.last_task(app)[0]
        db.update_task(app.conn, task_id, "Новое название", None, None)
        app.banner.shown[-1][3]()
        self.assertEqual(self.last_task(app)[1], "Новое название")
        # полоса честно говорит, что отменять не стала, и кнопки у неё нет
        self.assertEqual(app.banner.shown[-1][:3], ("hint", "Задачу уже изменили — отменять не стал.", None))

    def other_list(self, app, title, body=None):
        """Список B с задачей того же id, что последняя в списке A; self.conn — уже на B."""
        conn_b = db.connect(self.dir / "b.db")
        self.conns.append(conn_b)
        task_id = self.last_task(app)[0]
        while True:
            new = db.add_task(conn_b, title)
            if new >= task_id:
                break
        self.assertEqual(new, task_id)
        db.update_task(conn_b, new, title, None, None, body=body)
        app.conn = conn_b
        return conn_b, task_id, db.list_tasks(conn_b), db.task_meta(conn_b, task_id)

    def assert_untouched(self, conn_b, task_id, rows, meta):
        self.assertEqual(db.list_tasks(conn_b), rows)
        self.assertEqual(db.task_meta(conn_b, task_id), meta)

    def test_undo_after_list_switch(self):
        """Переключили список — «Отменить» не трогает задачу с тем же номером в другом списке."""
        app = self.make_app("Сдать отчёт завтра")
        app.add()
        conn_b, task_id, rows, meta = self.other_list(app, "Чужая задача")
        db.update_task(conn_b, task_id, "Чужая задача", "2030-01-01 09:00", 15, True, True)
        rows, meta = db.list_tasks(conn_b), db.task_meta(conn_b, task_id)
        shown = len(app.banner.shown)
        app.banner.shown[-1][3]()
        self.assert_untouched(conn_b, task_id, rows, meta)
        self.assertEqual(len(app.banner.shown), shown)  # «отменять не стал» тоже не показываем
        self.assertGreaterEqual(app.banner.hidden, 1)

    def test_mark_after_list_switch(self):
        app = self.make_app("Отчёт налоговой")
        for title in ("Отчёт для налоговой", "Отчёт в налоговую"):
            task_id = db.add_task(app.conn, title)
            db.update_task(app.conn, task_id, title, None, None, True, True)
        app.refresh()
        app.add()
        conn_b, task_id, rows, meta = self.other_list(app, "Чужая задача")
        app.banner.shown[-1][3]()
        app.quick_priority.assert_not_called()
        self.assert_untouched(conn_b, task_id, rows, meta)
        self.assertGreaterEqual(app.banner.hidden, 1)

    def test_steps_after_list_switch(self):
        app = self.make_app("Командировка в Казань снова")
        old = db.add_task(app.conn, "Командировка в Казань")
        db.update_task(app.conn, old, "Командировка в Казань", None, None, body="Билеты\nГостиница")
        app.refresh()
        app.add()
        self.assertEqual(app.banner.shown[-1][2], "Вставить шаги")
        conn_b, task_id, rows, meta = self.other_list(app, "Чужая задача")
        app.banner.shown[-1][3]()
        self.assert_untouched(conn_b, task_id, rows, meta)
        self.assertFalse(db.get_task(conn_b, task_id)[5])  # описание чужой задачи осталось пустым
        self.assertGreaterEqual(app.banner.hidden, 1)

    def test_buttons_work_after_switch_back(self):
        """Вернулись в тот же список (тот же conn) — «Отменить» снова работает."""
        app = self.make_app("Сдать отчёт завтра")
        app.add()
        conn_a = app.conn
        self.other_list(app, "Чужая задача")
        app.conn = conn_a
        app.banner.shown[-1][3]()
        self.assertEqual(self.last_task(app)[1], "Сдать отчёт завтра")

    def test_undo_after_delete(self):
        app = self.make_app("Сдать отчёт завтра")
        app.add()
        db.delete_task(app.conn, self.last_task(app)[0])
        app.banner.shown[-1][3]()  # не падает
        self.assertEqual(db.list_tasks(app.conn), [])

    def test_smart_off(self):
        app = self.make_app("Срочно сдать отчёт завтра", smart_on=False)
        app.add()
        task = self.last_task(app)
        self.assertEqual((task[1], task[4], task[6]), ("Срочно сдать отчёт завтра", None, 0))
        self.assertEqual(app.banner.shown, [])

    def test_busy_banner_not_covered(self):
        """Полоса занята (связь, «Открыть список») — молча ничего не применяем: задача как написана."""
        for kind, action in (("alert", False), ("wait", False), ("good", True)):
            with self.subTest(kind=kind):
                app = self.make_app("Срочно сдать отчёт завтра", banner_kind=kind, has_action=action)
                self.assertTrue(app.banner_busy())
                app.add()
                task = self.last_task(app)
                self.assertEqual((task[1], task[4], task[6]), ("Срочно сдать отчёт завтра", None, 0))
                self.assertEqual(app.banner.shown, [])

    def test_free_banner_kinds(self):
        for kind, action in ((None, False), ("good", False), ("hint", True)):
            with self.subTest(kind=kind):
                app = self.make_app("Сдать отчёт завтра", banner_kind=kind, has_action=action)
                self.assertFalse(app.banner_busy())
                app.add()
                self.assertEqual(self.last_task(app)[1], "Сдать отчёт")
                self.assertEqual(app.banner.shown[-1][2], "Отменить")

    def test_plain_title_nothing_shown(self):
        app = self.make_app("Купить 2 билета в 3 кассе")
        app.add()
        self.assertEqual(self.last_task(app)[1], "Купить 2 билета в 3 кассе")
        self.assertEqual(app.banner.shown, [])

    def test_priority_advice(self):
        app = self.make_app("Отчёт налоговой")
        for title in ("Отчёт для налоговой", "Отчёт в налоговую"):
            task_id = db.add_task(app.conn, title)
            db.update_task(app.conn, task_id, title, None, None, True, True)
        app.refresh()
        app.add()
        task = self.last_task(app)
        self.assertEqual((task[6], task[7]), (0, 0))  # только советуем, не ставим
        kind, text, button, mark = app.banner.shown[-1]
        self.assertEqual(button, "Отметить")
        self.assertTrue(text.startswith("Отметить новую задачу как «Срочно и важно»?"), text)
        mark()
        app.quick_priority.assert_called_once_with(task[0], True, True)

    def test_steps_advice(self):
        app = self.make_app("Командировка в Казань снова")
        old = db.add_task(app.conn, "Командировка в Казань")
        db.update_task(app.conn, old, "Командировка в Казань", None, None, body="Билеты\nГостиница")
        app.refresh()
        app.add()
        kind, text, button, insert = app.banner.shown[-1]
        self.assertEqual(button, "Вставить шаги")
        insert()
        self.assertEqual(db.get_task(app.conn, self.last_task(app)[0])[5], "Билеты\nГостиница")

    def test_steps_do_not_overwrite_body(self):
        app = self.make_app("Командировка в Казань снова")
        old = db.add_task(app.conn, "Командировка в Казань")
        db.update_task(app.conn, old, "Командировка в Казань", None, None, body="Билеты\nГостиница")
        app.refresh()
        app.add()
        new = self.last_task(app)[0]
        db.update_task(app.conn, new, "Командировка в Казань снова", None, None, body="своё")
        app.banner.shown[-1][3]()
        self.assertEqual(db.get_task(app.conn, new)[5], "своё")

    def test_word_form_priority_only_advice(self):
        """«Срочный вклад» — приоритет не ставим сами, только предлагаем «Отметить»."""
        app = self.make_app("Срочный вклад открыть")
        app.add()
        task = self.last_task(app)
        self.assertEqual((task[6], task[7]), (0, 0))
        kind, text, button, mark = app.banner.shown[-1]
        self.assertEqual(button, "Отметить")
        mark()
        app.quick_priority.assert_called_once_with(task[0], True, False)

    def test_enter_with_suggestion_does_not_add(self):
        app = self.make_app("Позвонить")
        app.title_suggest.accept.return_value = True
        app.entry_enter()
        self.assertEqual(db.list_tasks(app.conn), [])
        app.title_suggest.accept.return_value = False
        app.entry_enter()
        self.assertEqual(len(db.list_tasks(app.conn)), 1)

    def test_add_button_ignores_suggestion(self):
        """Кнопка «Добавить» вызывает add напрямую — открытый список вариантов не мешает."""
        app = self.make_app("Позвонить")
        app.title_suggest.accept.return_value = True
        app.add()
        app.title_suggest.accept.assert_not_called()
        self.assertEqual(len(db.list_tasks(app.conn)), 1)

    def test_smart_rows(self):
        app = self.make_app("x")
        app.all_rows = None
        self.assertEqual(app.smart_rows(), [])
        app.smart_on = False
        self.assertIsNone(app.smart_rows())


if __name__ == "__main__":
    unittest.main()
