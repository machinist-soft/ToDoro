"""Примеры задач: показывают все варианты статусов, приоритетов, сроков и напоминаний.

Сроки считаются от текущего момента, поэтому примеры всегда «свежие»:
одна задача просрочена, одна — на сегодня, другие — на завтра, через неделю и т. д.
"""
from datetime import datetime, timedelta

HOUR = 60
DAY = 24 * 60


def _at(day, hour, minute=0):
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def make_examples(now=None):
    """Список примеров: словари с полями задачи."""
    now = now or datetime.now()
    today = now
    in_3_hours = (now + timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    this_evening = _at(today, 18) if now.hour < 17 else _at(today + timedelta(days=1), 18)

    examples = [
        # Просроченная, срочная и важная — красная строка
        dict(title="Оплатить интернет", due=_at(today - timedelta(days=1), 9),
             remind=HOUR, urgent=True, important=True,
             body="Тариф «Домашний 500», 650 ₽.\nОплатить в приложении банка "
                  "по номеру договора 12-345678, иначе завтра отключат."),
        # Срочно и важно, срок сегодня через 3 часа
        dict(title="Сдать квартальный отчёт", due=in_3_hours,
             remind=30, urgent=True, important=True,
             body="Отчёт за III квартал для руководителя отдела.\n\n"
                  "— свести продажи по регионам;\n— добавить графики;\n"
                  "— отправить файл до конца рабочего дня."),
        # Только срочно, срок сегодня вечером
        dict(title="Ответить на письмо от бухгалтерии", due=this_evening,
             remind=15, urgent=True,
             body="Бухгалтерия просит прислать скан командировочного удостоверения."),
        # Только важно, срок завтра, напомнить за день
        dict(title="Подготовить презентацию для клиента", due=_at(today + timedelta(days=1), 10),
             remind=DAY, important=True,
             body="10–12 слайдов: о компании, кейсы, цены, сроки. "
                  "Взять шаблон из прошлой презентации и обновить цифры."),
        # Важно, срок через неделю, напомнить за 2 дня
        dict(title="Продлить страховку автомобиля", due=_at(today + timedelta(days=7), 12),
             remind=2 * DAY, important=True,
             body="Полис ОСАГО заканчивается через неделю. Сравнить цены у двух-трёх страховых."),
        # Важно, без срока
        dict(title="Записаться к стоматологу", important=True,
             body="Плановый осмотр раз в полгода. Удобнее в субботу утром."),
        # Обычная, срок послезавтра, напомнить за 2 часа
        dict(title="Купить продукты на неделю", due=_at(today + timedelta(days=2), 19),
             remind=2 * HOUR,
             body="Молоко, хлеб, яйца, овощи для супа, крупа, кофе, фрукты."),
        # Обычная, без срока, без описания
        dict(title="Разобрать фотографии с отпуска"),
        # Длинное описание — видно, как оно выглядит в панели справа и в письме
        dict(title="Подарки на Новый год", due=_at(today + timedelta(days=30), 20),
             body="Составить список подарков для всей семьи, коллег и друзей и заранее "
                  "заказать их онлайн, чтобы успеть до праздников.\n\n"
                  "Маме — тёплый плед, папе — книгу, сестре — настольную игру, "
                  "коллегам — сладкие наборы. Бюджет — до 15 000 ₽."),
        # Выполненные
        dict(title="Позвонить маме", important=True, done=True,
             body="Спросить, как прошла поездка на дачу."),
        dict(title="Забрать посылку на почте", due=_at(today - timedelta(days=1), 15),
             urgent=True, done=True, body="Трек-номер RA123456789RU, отделение на Ленина, 5."),
    ]

    for ex in examples:
        due = ex.get("due")
        remind = ex.get("remind")
        ex["due_at"] = due.strftime("%Y-%m-%d %H:%M") if due else None
        ex["remind_before"] = remind
        # Если время напоминания уже прошло — считаем, что оно показано,
        # иначе сразу после добавления выскочит пачка напоминаний.
        ex["reminded"] = bool(due and remind and due - timedelta(minutes=remind) <= now)
    return examples
