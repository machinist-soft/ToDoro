"""Задача из письма Outlook: читаем выделенное (или открытое) письмо классического Outlook.

Outlook разрешает другим программам управлять собой через COM — так ToDoro спрашивает
«какое письмо сейчас выделено?», забирает тему, текст, вложения и само письмо файлом .msg,
а после сохранения задачи ставит письму категорию «В ToDoro».
"""
import os
import re
import tempfile
from datetime import datetime
from email.utils import formataddr
from pathlib import Path

CATEGORY = "В ToDoro"     # категория письма в Outlook: «по нему уже есть задача»
CATEGORY_COLOR = 6         # olCategoryColorTeal — как значок ToDoro
MAX_BODY = 6000            # длиннее описание обрезаем — полный текст есть в приложенном письме
SMALL_INLINE = 30 * 1024   # картинки внутри текста меньше этого — обычно логотипы из подписей

# Классы элементов Outlook (OlObjectClass)
MAIL, TASK, MEETING = 43, 48, 53
TASK_REQUESTS = (49, 50, 51, 52)  # поручение задачи и ответы на него
EXPLORER, INSPECTOR = 34, 35      # окно папки и окно открытого письма

# Свойства MAPI, которых нет в обычном списке полей письма
PR_MESSAGE_ID = "http://schemas.microsoft.com/mapi/proptag/0x1035001F"   # Message-ID письма
PR_ATTACH_HIDDEN = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"
PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


class OutlookError(Exception):
    """Понятное пользователю сообщение: Outlook не запущен, не выделено письмо и т. п."""


# «RE:», «FW:», «Отв:», «Пересл:» (и немецкие, французские) в начале темы, сколько бы их ни было
SUBJECT_PREFIX = re.compile(
    r"^\s*((re|fw|fwd|aw|wg|tr|rv|отв|ответ|пересл|переслать|пер)\s*(\[\d+\]|\(\d+\))?\s*[:：]\s*)+",
    re.IGNORECASE)
# Начало цитаты прошлого письма в ответе: «-----Original Message-----» или блок «От: … Отправлено: …»
QUOTE_MARK = re.compile(r"^\s*-{2,}\s*(original message|исходное сообщение|forwarded message|"
                        r"пересылаемое сообщение)\s*-{2,}\s*$", re.IGNORECASE)
QUOTE_FROM = re.compile(r"^\s*(from|от|von|de)\s*:\s*\S", re.IGNORECASE)
QUOTE_SENT = re.compile(r"^\s*(sent|date|отправлено|дата|gesendet|envoyé)\s*:", re.IGNORECASE)
FILE_NAME_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def clean_subject(subject):
    return SUBJECT_PREFIX.sub("", subject or "").strip()


def clean_body(text):
    """Текст письма для описания задачи: без цитаты прошлых писем и лишних пустых строк."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i, line in enumerate(lines):
        if QUOTE_MARK.match(line) or (
                QUOTE_FROM.match(line) and any(QUOTE_SENT.match(l) for l in lines[i + 1:i + 4])):
            if any(l.strip() for l in lines[:i]):  # письмо, где всё — цитата (пересылка), не режем
                lines = lines[:i]
            break
    # В тексте HTML-писем Outlook пишет у каждой ссылки её адрес: «сайт <https://…>», а у картинок —
    # «[cid:…]». Для описания задачи это мусор (письмо целиком всё равно приложено к задаче).
    lines = [re.sub(r"\s*\[cid:[^\]]*\]", "", re.sub(r"\s*<(https?|mailto):[^>\s]*>", "", line)).rstrip()
             for line in lines]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY].rstrip() + "\n…\n(полный текст — в приложенном письме)"
    return body


def safe_file_name(name, default="письмо"):
    name = FILE_NAME_BAD.sub(" ", name or "").strip(" .")
    return (name or default)[:80]


def local_time(value):
    """Дату из Outlook (pywintypes.datetime) — в обычный datetime без пояса. Outlook отдаёт
    местное время, хотя и помечает его как UTC. «Пустая» дата Outlook — 4501 год."""
    try:
        moment = datetime(value.year, value.month, value.day, value.hour, value.minute)
    except (AttributeError, ValueError):
        return None
    return None if moment.year >= 4000 else moment


def outlook_app():
    try:
        import pythoncom
        import win32com.client
    except ImportError as error:
        raise OutlookError("Не найден модуль связи с Outlook (pywin32).") from error
    pythoncom.CoInitialize()
    try:
        return win32com.client.GetActiveObject("Outlook.Application")
    except Exception as error:  # noqa: BLE001 — Outlook не запущен или его нет
        raise OutlookError("Outlook не запущен.\n\nОткройте Outlook, выделите письмо "
                           "и попробуйте ещё раз.") from error


def selected_items():
    """Письма, выделенные в Outlook, или письмо, открытое в отдельном окне."""
    app = outlook_app()
    try:
        window = app.ActiveWindow()
        if window is not None and window.Class == INSPECTOR:
            return [window.CurrentItem]
        explorer = app.ActiveExplorer()
        selection = explorer.Selection if explorer is not None else None
        items = [selection.Item(i) for i in range(1, selection.Count + 1)] if selection else []
    except Exception as error:  # noqa: BLE001 — в папке нечего выделять (например, календарь)
        raise OutlookError(f"Не удалось узнать, какое письмо выделено в Outlook:\n{error}") from error
    if not items:
        raise OutlookError("В Outlook не выделено ни одного письма.\n\n"
                           "Выделите письмо в списке и попробуйте ещё раз.")
    return items


def get(item, name, default=None):
    try:
        return getattr(item, name)
    except Exception:  # noqa: BLE001 — у элемента такого поля нет (у задачи нет отправителя и т. п.)
        return default


def sender_parts(item):
    """(имя, адрес) отправителя письма."""
    name = get(item, "SenderName") or ""
    address = get(item, "SenderEmailAddress") or ""
    if get(item, "SenderEmailType") == "EX":  # внутренний адрес Exchange — ищем обычный
        try:
            address = item.Sender.GetExchangeUser().PrimarySmtpAddress or ""
        except Exception:  # noqa: BLE001
            address = ""
    return name, address if "@" in address else ""


def sender_address(item):
    """Отправитель для поля «Кому» письма по задаче: «Иван Иванов <ivan@firma.ru>»."""
    name, address = sender_parts(item)
    if not address:
        return ""
    if not name or name.casefold() == address.casefold():
        return address
    return formataddr((name, address))


def sender_text(item):
    name, address = sender_parts(item)
    if address and address.casefold() != name.casefold():
        return f"{name} <{address}>" if name else address
    return name or address


def item_attachments(item, folder):
    """[(имя, байты)] вложений письма, без мелких картинок из подписи и скрытых файлов."""
    files = []
    try:
        attachments = item.Attachments
        count = attachments.Count
    except Exception:  # noqa: BLE001
        return files
    for i in range(1, count + 1):
        try:
            attachment = attachments.Item(i)
            name = safe_file_name(attachment.FileName or attachment.DisplayName, f"Вложение {i}")
            props = attachment.PropertyAccessor
            try:
                if props.GetProperty(PR_ATTACH_HIDDEN):
                    continue
            except Exception:  # noqa: BLE001 — свойства нет: вложение обычное
                pass
            try:
                inline = bool(props.GetProperty(PR_ATTACH_CONTENT_ID))
            except Exception:  # noqa: BLE001
                inline = False
            if inline and Path(name).suffix.lower() in IMAGE_TYPES and attachment.Size < SMALL_INLINE:
                continue
            path = Path(folder) / f"{i}_{name}"
            attachment.SaveAsFile(str(path))
            files.append((name, path.read_bytes()))
        except Exception:  # noqa: BLE001 — одно вложение не сохранилось — остальные берём
            continue
    return files


def read_item(item, folder):
    """Всё, что нужно для задачи, из одного элемента Outlook."""
    kind = get(item, "Class")
    task = None
    if kind == TASK:
        task = item
    elif kind in TASK_REQUESTS:
        try:
            task = item.GetAssociatedTask(False)
        except Exception:  # noqa: BLE001
            task = None
    subject = get(item, "Subject") or ""
    title = clean_subject(subject)
    when = local_time(get(item, "ReceivedTime")) or local_time(get(item, "CreationTime"))
    sender = sender_text(item)
    if not title:
        title = f"Письмо от {sender}" if sender else "Письмо без темы"
    due = None
    if task is not None:
        due = local_time(get(task, "DueDate"))
    elif get(item, "IsMarkedAsTask"):
        due = local_time(get(item, "TaskDueDate"))
    if due is not None and due.hour == 0 and due.minute == 0:
        due = due.replace(hour=18)  # у Outlook срок — день без времени; берём конец рабочего дня

    header = []
    if sender:
        header.append(f"От: {sender}" + (when.strftime(", %d.%m.%Y %H:%M") if when else ""))
    elif when:
        header.append(when.strftime("Письмо от %d.%m.%Y %H:%M"))
    text = clean_body(get(item, "Body") or get(task, "Body") or "")
    body = "\n".join(header) + ("\n\n" + text if text else "")

    try:
        mail_id = item.PropertyAccessor.GetProperty(PR_MESSAGE_ID) or ""
    except Exception:  # noqa: BLE001 — у черновиков и задач Message-ID нет
        mail_id = ""
    entry_id = get(item, "EntryID") or ""
    files = item_attachments(item, folder)
    message = None
    try:
        path = Path(folder) / "mail.msg"
        item.SaveAs(str(path), 9)  # olMSGUnicode
        message = (safe_file_name(title, "Письмо") + ".msg", path.read_bytes())
    except Exception:  # noqa: BLE001
        pass
    return dict(
        title=title[:200], body=body, due_at=due.strftime("%Y-%m-%d %H:%M") if due else None,
        important=(get(item, "Importance") == 2 or get(task, "Importance") == 2),
        mail_id=mail_id or entry_id, entry_id=entry_id, mail_from=sender_address(item),
        store_id=get(get(item, "Parent"), "StoreID") or "",
        files=([message] if message else []) + files,
    )


def read_selected():
    """Выделенные в Outlook письма — список словарей для новых задач (см. read_item)."""
    items = selected_items()
    result = []
    for item in items:
        with tempfile.TemporaryDirectory(prefix="todoro-mail-") as folder:
            try:
                result.append(read_item(item, folder))
            except Exception as error:  # noqa: BLE001
                raise OutlookError(f"Не удалось прочитать письмо из Outlook:\n{error}") from error
    return result


def list_separator():
    """Разделитель категорий в Outlook — «разделитель элементов списка» Windows (у нас часто «;»)."""
    try:
        import ctypes
        buffer = ctypes.create_unicode_buffer(8)
        if ctypes.windll.kernel32.GetLocaleInfoW(0x0400, 0x0C, buffer, 8):  # LOCALE_SLIST
            return buffer.value or ","
    except (AttributeError, OSError):
        pass
    return ","


def mark_added(entry_id, store_id=""):
    """Ставит письму категорию «В ToDoro». Не получилось — не страшно: задача уже создана."""
    if not entry_id:
        return False
    try:
        app = outlook_app()
        session = app.Session
        try:
            if not any(session.Categories.Item(i).Name == CATEGORY
                       for i in range(1, session.Categories.Count + 1)):
                session.Categories.Add(CATEGORY, CATEGORY_COLOR)
        except Exception:  # noqa: BLE001 — без цвета категория всё равно поставится
            pass
        item = session.GetItemFromID(entry_id, store_id) if store_id else session.GetItemFromID(entry_id)
        names = [name.strip() for name in re.split(r"[;,]", item.Categories or "") if name.strip()]
        if CATEGORY not in names:
            item.Categories = (list_separator() + " ").join(names + [CATEGORY])
            item.Save()
        return True
    except Exception:  # noqa: BLE001
        return False


if os.name != "nt":  # pragma: no cover — Outlook с COM есть только в Windows
    def read_selected():  # noqa: F811
        raise OutlookError("Задачи из писем Outlook можно создавать только в Windows.")
