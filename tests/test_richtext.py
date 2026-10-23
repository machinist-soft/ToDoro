"""Оформление описания значками (richtext, GitHub #12): разбор строк и блоков, снятие значков,
таблицы из Excel, письмо Outlook из HTML (в том числе с разметкой Word), а также
outlook.mail_text / read_item / clean_body с «**От:**». Без окон и без Outlook: письмо — подделка."""

import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import outlook  # noqa: E402
import richtext  # noqa: E402


def joined(parts):
    return "".join(t for t, _ in parts)


class InlineTests(unittest.TestCase):
    def test_plain_text(self):
        self.assertEqual(richtext.inline("просто текст"), [("просто текст", frozenset())])

    def test_empty(self):
        self.assertEqual(richtext.inline(""), [])

    def test_bold_italic_strike(self):
        parts = richtext.inline("а **ж** б *к* в ~~з~~")
        self.assertEqual(parts, [("а ", frozenset()), ("ж", {"bold"}), (" б ", frozenset()),
                                 ("к", {"italic"}), (" в ", frozenset()), ("з", {"strike"})])

    def test_multiplication_is_not_italic(self):
        self.assertEqual(richtext.inline("2 * 3 * 4"), [("2 * 3 * 4", frozenset())])

    def test_star_inside_word_is_not_italic(self):
        self.assertEqual(joined(richtext.inline("a*b*c")), "a*b*c")

    def test_italic_inside_bold(self):
        parts = richtext.inline("**жирный и *курсив***")
        self.assertEqual(parts, [("жирный и ", {"bold"}), ("курсив", {"bold", "italic"})])

    def test_bold_inside_strike(self):
        parts = richtext.inline("~~старое **важное**~~")
        self.assertEqual(parts, [("старое ", {"strike"}), ("важное", {"strike", "bold"})])

    def test_marks_with_spaces_inside_stay_text(self):
        for text in ("** не жирный **", "~~ нет ~~", "* нет *"):
            self.assertEqual(richtext.inline(text), [(text, frozenset())], text)

    def test_unclosed_marks_stay_text(self):
        self.assertEqual(richtext.inline("**без конца"), [("**без конца", frozenset())])

    def test_styles_are_frozensets(self):
        for _, styles in richtext.inline("**a** *b*"):
            self.assertIsInstance(styles, frozenset)

    def test_huge_line(self):
        """Строка длиннее LONG_LINE — как есть, значки не ищутся (иначе на «*a *a …» поиск
        идёт очень долго); строка короче — разбирается."""
        text = "**ж** обычный " * 5000
        self.assertEqual(richtext.inline(text), [(text, frozenset())])
        self.assertEqual(richtext.marks(text), [])
        start = time.perf_counter()
        richtext.inline("*a " * 2000)
        self.assertLess(time.perf_counter() - start, 0.2)
        short = "**ж** обычный " * 100
        self.assertEqual(joined(richtext.inline(short)), "ж обычный " * 100)


class MarksTests(unittest.TestCase):
    def test_bold(self):
        self.assertEqual(sorted(richtext.marks("a **b** c")),
                         [(2, 4, "mark"), (4, 5, "bold"), (5, 7, "mark")])

    def test_italic_and_strike(self):
        self.assertEqual(sorted(richtext.marks("*к* ~~з~~")),
                         [(0, 1, "mark"), (1, 2, "italic"), (2, 3, "mark"),
                          (4, 6, "mark"), (6, 7, "strike"), (7, 9, "mark")])

    def test_nested(self):
        line = "**a *b***"
        found = richtext.marks(line)
        self.assertIn((0, 2, "mark"), found)
        self.assertIn((7, 9, "mark"), found)
        self.assertIn((2, 7, "bold"), found)
        self.assertIn((4, 5, "mark"), found)
        self.assertIn((5, 6, "italic"), found)
        self.assertIn((6, 7, "mark"), found)

    def test_no_marks(self):
        self.assertEqual(richtext.marks("2 * 3 * 4"), [])
        self.assertEqual(richtext.marks(""), [])


class BlocksTests(unittest.TestCase):
    def test_text_lines(self):
        self.assertEqual(richtext.blocks("a\n\nb"), [("text", "a"), ("text", ""), ("text", "b")])

    def test_none_and_empty(self):
        self.assertEqual(richtext.blocks(None), [("text", "")])
        self.assertEqual(richtext.blocks(""), [("text", "")])

    def test_crlf(self):
        self.assertEqual(richtext.blocks("a\r\nb"), [("text", "a"), ("text", "b")])

    def test_bullets_and_levels(self):
        self.assertEqual(richtext.blocks("- a\n• b\n  - c\n\t- d"),
                         [("bullet", "a", 0), ("bullet", "b", 0), ("bullet", "c", 1),
                          ("bullet", "d", 2)])

    def test_numbers(self):
        self.assertEqual(richtext.blocks("1. a\n2) b\n   10. c"),
                         [("number", "1", "a", 0), ("number", "2", "b", 0),
                          ("number", "10", "c", 1)])

    def test_not_a_list(self):
        """«-5 градусов», «2024. год» без пробела, «- » без текста — обычные строки."""
        for line in ("-5 градусов", "2024.год", "- ", "1. "):
            self.assertEqual(richtext.blocks(line), [("text", line)], line)

    def test_table_with_header(self):
        self.assertEqual(richtext.blocks("| a | b |\n|---|---|\n| 1 | 2 |"),
                         [("table", [["a", "b"], ["1", "2"]], True)])

    def test_table_without_header(self):
        self.assertEqual(richtext.blocks("| a | b |\n| 1 | 2 |"),
                         [("table", [["a", "b"], ["1", "2"]], False)])

    def test_table_rows_padded(self):
        self.assertEqual(richtext.blocks("| a |\n| 1 | 2 | 3 |"),
                         [("table", [["a", "", ""], ["1", "2", "3"]], False)])

    def test_rule_only_is_not_table(self):
        self.assertEqual(richtext.blocks("|---|---|"), [])

    def test_rule_not_after_first_row_is_not_header(self):
        blocks = richtext.blocks("| a |\n| b |\n|---|\n| c |")
        self.assertEqual(blocks, [("table", [["a"], ["b"], ["c"]], False)])

    def test_text_around_table(self):
        self.assertEqual(richtext.blocks("до\n| a |\nпосле"),
                         [("text", "до"), ("table", [["a"]], False), ("text", "после")])


class PlainTests(unittest.TestCase):
    def test_removes_marks(self):
        self.assertEqual(richtext.plain("**ж** *к* ~~з~~"), "ж к з")

    def test_lists(self):
        self.assertEqual(richtext.plain("- пункт\n2. второй"), "• пункт\n2. второй")

    def test_table(self):
        self.assertEqual(richtext.plain("| **a** | b |\n|---|---|\n| 1 | 2 |"), "a  b\n1  2")

    def test_empty_and_none(self):
        self.assertEqual(richtext.plain(""), "")
        self.assertEqual(richtext.plain(None), "")

    def test_plain_text_unchanged(self):
        text = "Обычное описание\n\n2 * 3 * 4 = 24"
        self.assertEqual(richtext.plain(text), text)


class TableTests(unittest.TestCase):
    def test_header_rule(self):
        self.assertEqual(richtext.table([["a", "b"], ["1", "2"]]),
                         "| a | b |\n|---|---|\n| 1 | 2 |")

    def test_single_row_no_rule(self):
        self.assertEqual(richtext.table([["a", "b"]]), "| a | b |")

    def test_pipes_and_spaces_cleaned(self):
        self.assertEqual(richtext.table([["a|b", "  x \n y "], [1, None]]),
                         "| a/b | x y |\n|---|---|\n| 1 | None |")

    def test_ragged_rows(self):
        self.assertEqual(richtext.table([["a"], ["1", "2"]]), "| a |  |\n|---|---|\n| 1 | 2 |")

    def test_round_trip(self):
        rows = [["Имя", "Сумма"], ["Иван", "1 000"]]
        self.assertEqual(richtext.blocks(richtext.table(rows)), [("table", rows, True)])


class TsvTests(unittest.TestCase):
    def test_excel_cells(self):
        self.assertEqual(richtext.tsv_to_table("a\tb\r\n1\t2\r\n"), "| a | b |\n|---|---|\n| 1 | 2 |")

    def test_one_row(self):
        self.assertEqual(richtext.tsv_to_table("a\tb"), "| a | b |")

    def test_not_a_table(self):
        for text in ("", None, "одна ячейка", "a\nb\nc", "\n\n"):
            self.assertIsNone(richtext.tsv_to_table(text), repr(text))

    def test_empty_cells_kept(self):
        self.assertEqual(richtext.tsv_to_table("a\t\n\tb"), "| a |  |\n|---|---|\n|  | b |")


OUTLOOK_HTML = """<html xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head><meta http-equiv=Content-Type content="text/html; charset=utf-8">
<style><!--
p.MsoNormal, li.MsoNormal {margin:0cm; font-size:11.0pt; font-family:"Calibri",sans-serif;}
--></style><!--[if gte mso 9]><xml>
<o:shapedefaults v:ext="edit" spidmax="1026" />
</xml><![endif]--><!--[if gte mso 9]><xml>
<o:shapelayout v:ext="edit"><o:idmap v:ext="edit" data="1" /></o:shapelayout></xml><![endif]-->
</head>
<body lang=RU link="#0563C1" vlink="#954F72" style='word-wrap:break-word'>
<div class=WordSection1>
<p class=MsoNormal>Добрый&nbsp;день,<o:p></o:p></p>
<p class=MsoNormal><o:p>&nbsp;</o:p></p>
<p class=MsoNormal><b>Важно:</b> отчёт до <i>пятницы</i>, <s>не четверга</s><o:p></o:p></p>
<p class=MsoListParagraph style='text-indent:-18.0pt;mso-list:l0 level1 lfo1'><![if !supportLists]><span style='font-family:Symbol'><span style='mso-list:Ignore'>·<span style='font:7.0pt "Times New Roman"'>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; </span></span></span><![endif]>Первый пункт<o:p></o:p></p>
<p class=MsoListParagraph style='text-indent:-18.0pt;mso-list:l0 level1 lfo1'><![if !supportLists]><span style='font-family:Symbol'><span style='mso-list:Ignore'>·<span style='font:7.0pt "Times New Roman"'>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; </span></span></span><![endif]>Второй пункт<o:p></o:p></p>
<p class=MsoNormal><o:p>&nbsp;</o:p></p>
<table class=MsoTableGrid border=1 cellspacing=0 cellpadding=0 style='border-collapse:collapse'>
<tr><td width=200 valign=top><p class=MsoNormal><b>Имя<o:p></o:p></b></p></td>
<td width=200 valign=top><p class=MsoNormal><b>Сумма<o:p></o:p></b></p></td></tr>
<tr><td width=200 valign=top><p class=MsoNormal>Иван<o:p></o:p></p></td>
<td width=200 valign=top><p class=MsoNormal>1&nbsp;000<o:p></o:p></p></td></tr>
</table>
<p class=MsoNormal><o:p>&nbsp;</o:p></p>
<p class=MsoNormal>С уважением,<br>Пётр<o:p></o:p></p>
<p class=MsoNormal><o:p>&nbsp;</o:p></p>
<div style='border:none;border-top:solid #E1E1E1 1.0pt;padding:3.0pt 0cm 0cm 0cm'>
<p class=MsoNormal><b>От:</b> Иванов Иван &lt;ivan@example.com&gt; <br><b>Отправлено:</b> 1 октября 2026 г. 10:00<br><b>Кому:</b> Пётр<br><b>Тема:</b> отчёт<o:p></o:p></p>
</div>
<p class=MsoNormal><o:p>&nbsp;</o:p></p>
<p class=MsoNormal>Старое письмо<o:p></o:p></p>
</div></body></html>"""


class HtmlToMarkupTests(unittest.TestCase):
    def md(self, html):
        return richtext.html_to_markup(html)

    def test_outlook_word_mail(self):
        text = self.md(OUTLOOK_HTML)
        lines = text.split("\n")
        self.assertEqual(lines[0], "Добрый день,")
        self.assertEqual(lines[1], "")  # пустой абзац с &nbsp; — пустая строка
        self.assertIn("**Важно:** отчёт до *пятницы*, ~~не четверга~~", lines)
        self.assertIn("- Первый пункт", lines)
        self.assertIn("- Второй пункт", lines)
        self.assertIn("| **Имя** | **Сумма** |", lines)
        self.assertIn("|---|---|", lines)
        self.assertIn("| Иван | 1 000 |", lines)
        self.assertIn("**От:** Иванов Иван <ivan@example.com>", lines)
        # стили, условные комментарии и xml из head — не в тексте
        for junk in ("MsoNormal", "shapedefaults", "mso", "<o:p>", "&nbsp;", "\xa0", "Symbol"):
            self.assertNotIn(junk, text)
        self.assertNotIn("\n\n\n", text)

    def test_outlook_mail_table_is_separate_block(self):
        blocks = richtext.blocks(self.md(OUTLOOK_HTML))
        tables = [b for b in blocks if b[0] == "table"]
        self.assertEqual(tables, [("table", [["**Имя**", "**Сумма**"], ["Иван", "1 000"]], True)])

    def test_styles(self):
        self.assertEqual(self.md("<p><b>b</b> <strong>s</strong> <i>i</i> <em>e</em> "
                                 "<s>x</s> <strike>y</strike> <del>d</del></p>"),
                         "**b** **s** *i* *e* ~~x~~ ~~y~~ ~~d~~")

    def test_empty_bold_gives_no_marks(self):
        self.assertEqual(self.md("<p>x<b></b>y<i></i>z</p>"), "xyz")

    def test_paragraphs_and_breaks(self):
        self.assertEqual(self.md("<p>a</p><p></p><p>b</p>c<br>d<br><br>e"), "a\n\nb\nc\nd\n\ne")

    def test_div_lines(self):
        self.assertEqual(self.md("<div>a</div><div>b</div>"), "a\nb")

    def test_lists(self):
        self.assertEqual(self.md("<ul><li>a</li><li>b</li></ul><ol><li>x</li><li>y</li></ol>"),
                         "- a\n- b\n1. x\n2. y")

    def test_nested_bullet_list_indented(self):
        """Вложенный список — с отступом: в описании он уровнем ниже."""
        text = self.md("<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>")
        self.assertEqual(richtext.blocks(text),
                         [("bullet", "a", 0), ("bullet", "b", 1), ("bullet", "c", 0)])

    def test_nested_numbered_list_indented(self):
        text = self.md("<ol><li>a<ol><li>b</li></ol></li><li>c</li></ol>")
        self.assertEqual(richtext.blocks(text),
                         [("number", "1", "a", 0), ("number", "1", "b", 1), ("number", "2", "c", 0)])

    def test_word_bullet_paragraph(self):
        self.assertEqual(self.md("<p>·\xa0\xa0\xa0 пункт</p><p>•  второй</p>"), "- пункт\n- второй")

    def test_data_table_separated_from_text(self):
        text = self.md("<p>до</p><table><tr><td>a</td><td>b</td></tr>"
                       "<tr><td>1</td><td>2|3</td></tr></table><p>после</p>")
        self.assertEqual(text, "до\n\n| a | b |\n|---|---|\n| 1 | 2/3 |\n\nпосле")

    def test_th_cells(self):
        text = self.md("<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>")
        self.assertEqual(text, "| a | b |\n|---|---|\n| 1 | 2 |")

    def test_layout_table_one_row_is_text(self):
        self.assertEqual(self.md("<table><tr><td>a</td><td>b</td></tr></table>"), "a b")

    def test_layout_table_one_column_is_text(self):
        self.assertEqual(self.md("<table><tr><td>a</td></tr><tr><td>b</td></tr></table>"), "a\nb")

    def test_empty_rows_dropped(self):
        text = self.md("<table><tr><td>a</td><td>b</td></tr><tr><td>&nbsp;</td><td></td></tr>"
                       "<tr><td>1</td><td>2</td></tr></table>")
        self.assertEqual(text, "| a | b |\n|---|---|\n| 1 | 2 |")

    def test_layout_table_with_nested_data_table(self):
        """Таблица для вёрстки — текстом, а таблица данных внутри неё — настоящей таблицей
        на своих строках (а не значками, склеенными в одну строку)."""
        text = self.md("<table><tr><td>логотип<table><tr><td>a</td><td>b</td></tr>"
                       "<tr><td>c</td><td>d</td></tr></table></td></tr></table>")
        self.assertEqual(text, "логотип\n| a | b |\n|---|---|\n| c | d |")
        kinds = [b[0] for b in richtext.blocks(text)]
        self.assertEqual(kinds, ["text", "table"])

    def test_layout_table_keeps_paragraphs(self):
        """Всё письмо внутри таблицы для вёрстки (рассылки, подписи) — абзацы не склеиваются
        в одну строку."""
        text = self.md("<table><tr><td><p>Привет</p><p>Вторая строка</p></td></tr></table>")
        self.assertEqual(text.split("\n"), ["Привет", "Вторая строка"])

    def test_head_style_script_skipped(self):
        self.assertEqual(self.md("<head><title>T</title><style>p{color:red}</style></head>"
                                 "<script>alert(1)</script><p>ok</p>"), "ok")

    def test_entities(self):
        self.assertEqual(self.md("<p>a &lt;b&gt; &amp; &quot;c&quot;</p>"), 'a <b> & "c"')

    def test_broken_html_does_not_fail(self):
        for html in ("<b>не закрыт <table><tr><td>a<div", "</p></table></li></ul>", "<<<>>>",
                     "<table><tr><td>a</td>", "<ul><li>a", "<!--[if", "</style>текст"):
            self.assertIsInstance(self.md(html), str, html)

    def test_empty(self):
        self.assertEqual(self.md(""), "")
        self.assertEqual(self.md(None), "")

    def test_no_triple_newlines(self):
        self.assertEqual(self.md("<p>a</p><br><br><br><br><p>b</p>"), "a\n\nb")


class MailTextTests(unittest.TestCase):
    """outlook.mail_text и read_item — на подделке письма (настоящий Outlook не нужен)."""

    def item(self, **values):
        base = dict(Class=43, Subject="Отчёт", ReceivedTime=None, CreationTime=None,
                    Body="", HTMLBody="", BodyFormat=1, Importance=1)
        base.update(values)
        return SimpleNamespace(**base)

    def test_html_mail(self):
        item = self.item(BodyFormat=2, HTMLBody="<p><b>Жирный</b> текст</p>")
        self.assertEqual(outlook.mail_text(item), "**Жирный** текст")

    def test_plain_and_rtf_mail_give_empty(self):
        for fmt in (1, 3, None):
            item = self.item(BodyFormat=fmt, HTMLBody="<p><b>x</b></p>")
            self.assertEqual(outlook.mail_text(item), "", fmt)

    def test_huge_html_gives_empty(self):
        """Огромное письмо (больше MAX_HTML) — без оформления: возьмут обычный текст."""
        html = "<p><b>x</b></p>" * (outlook.MAX_HTML // 14 + 1)
        self.assertGreater(len(html), outlook.MAX_HTML)
        self.assertEqual(outlook.mail_text(self.item(BodyFormat=2, HTMLBody=html)), "")

    def test_missing_fields(self):
        self.assertEqual(outlook.mail_text(SimpleNamespace()), "")
        self.assertEqual(outlook.mail_text(SimpleNamespace(BodyFormat=2)), "")
        self.assertEqual(outlook.mail_text(SimpleNamespace(BodyFormat=2, HTMLBody=None)), "")

    def read(self, item):
        folder = tempfile.mkdtemp()
        try:
            with mock.patch.object(outlook, "sender_text", return_value=""), \
                    mock.patch.object(outlook, "sender_address", return_value=""), \
                    mock.patch.object(outlook, "item_attachments", return_value=[]), \
                    mock.patch.object(outlook, "mark_added"):
                task = outlook.read_item(item, folder)
                task["body"] = task["body"].strip()  # без отправителя и даты шапки нет
                return task
        finally:
            import shutil
            shutil.rmtree(folder, ignore_errors=True)

    def test_read_item_uses_html(self):
        item = self.item(BodyFormat=2, Body="Жирный текст",
                         HTMLBody="<p><b>Жирный</b> текст</p><p><b>От:</b> Иван<br>"
                                  "<b>Отправлено:</b> вчера</p><p>старое</p>")
        task = self.read(item)
        self.assertEqual(task["body"], "**Жирный** текст")

    def test_read_item_plain_mail_uses_body(self):
        item = self.item(BodyFormat=1, Body="Обычный *текст*", HTMLBody="")
        self.assertEqual(self.read(item)["body"], "Обычный *текст*")

    def test_read_item_empty_html_falls_back_to_body(self):
        item = self.item(BodyFormat=2, Body="Текст из Body", HTMLBody="<html><head></head></html>")
        self.assertEqual(self.read(item)["body"], "Текст из Body")


class CleanBodyMarksTests(unittest.TestCase):
    def test_bold_from_header_cuts_quote(self):
        body = "Сделайте до пятницы.\n\n**От:** Иванов\n**Отправлено:** вчера\n\nстарое"
        self.assertEqual(outlook.clean_body(body), "Сделайте до пятницы.")

    def test_bold_from_with_space_cuts_quote(self):
        body = "Текст\n**From:** Ivan\n**Sent:** Monday\nold"
        self.assertEqual(outlook.clean_body(body), "Текст")

    def test_marks_kept_in_result(self):
        body = "**Важно:** *сегодня*\n**От:** Иванов\n**Отправлено:** вчера"
        self.assertEqual(outlook.clean_body(body), "**Важно:** *сегодня*")

    def test_forward_only_not_cut(self):
        body = "**От:** Иванов\n**Отправлено:** вчера\n\nстарое"
        self.assertIn("старое", outlook.clean_body(body))

    def test_from_without_sent_not_cut(self):
        body = "Текст\n**От:** кого угодно\nещё текст"
        self.assertEqual(outlook.clean_body(body), body)

    def test_html_mail_through_clean_body(self):
        text = outlook.clean_body(richtext.html_to_markup(OUTLOOK_HTML))
        self.assertIn("**Важно:**", text)
        self.assertIn("| Иван | 1 000 |", text)
        self.assertIn("Пётр", text)
        self.assertNotIn("Старое письмо", text)
        self.assertNotIn("От:", text)


class OutlookSpacesTests(unittest.TestCase):
    """Outlook (Word) оставляет пробелы внутри <b> и дробит жирный на соседние <b> —
    звёздочек в тексте задачи оставаться не должно."""

    def check(self, html, markup, plain):
        text = richtext.html_to_markup(html)
        self.assertEqual(text, markup)
        self.assertEqual(richtext.plain(text), plain)
        self.assertNotIn("*", richtext.plain(text))

    def test_space_inside_bold(self):
        self.check("<b>Срок: </b>пятница", "**Срок:** пятница", "Срок: пятница")

    def test_nbsp_inside_bold(self):
        self.check("<b><span>Срок:<o:p>&nbsp;</o:p></span></b>", "**Срок:**", "Срок:")

    def test_bold_only_space(self):
        self.check("Привет,<b> </b>коллеги", "Привет, коллеги", "Привет, коллеги")

    def test_bold_pieces_glued(self):
        self.check("<b>Жирный</b><b>подряд</b>", "**Жирныйподряд**", "Жирныйподряд")

    def test_bold_across_br(self):
        self.check("<p><b>строка1<br>строка2</b></p>", "**строка1**\n**строка2**", "строка1\nстрока2")

    def test_leading_space_moves_out(self):
        self.check("a<i> курсив</i> b", "a *курсив* b", "a курсив b")

    def test_big_layout_cell_is_fast(self):
        """Рассылка целиком в одной ячейке таблицы, в каждом абзаце жирный: разбор не растёт
        квадратично (раньше ~30 с на 400 КБ — окно ToDoro висело)."""
        para = "<p><strong>Заголовок</strong> текст <b>жирный</b> и ещё немного слов в абзаце.</p>"
        html = "<table><tr><td>" + para * 3000 + "</td></tr></table>"
        start = time.perf_counter()
        text = richtext.html_to_markup(html)
        self.assertLess(time.perf_counter() - start, 3)
        self.assertEqual(text.count("**Заголовок**"), 3000)
        self.assertNotIn("\x01", text)

    def test_many_bold_in_one_paragraph_is_fast(self):
        html = "<p>" + "<b>x</b> " * 20000 + "</p>"
        start = time.perf_counter()
        text = richtext.html_to_markup(html)
        self.assertLess(time.perf_counter() - start, 3)
        self.assertEqual(text.count("**x**"), 20000)

    def test_card_mask_kept(self):
        """«****1234» — текст письма (маска номера карты), а не значки: остаётся как есть."""
        self.assertEqual(richtext.html_to_markup("<p>Номер карты ****1234</p>"), "Номер карты ****1234")
        self.assertEqual(richtext.html_to_markup("<p>Карта **** 1234, код ~~~~</p>"),
                         "Карта **** 1234, код ~~~~")

    def test_bold_across_br_in_layout_cell(self):
        """Подпись в таблице-вёрстке: жирный через <br> — у каждой строки свои значки."""
        self.check("<table><tr><td><b>Иван Иванов<br>Директор</b></td></tr></table>",
                   "**Иван Иванов**\n**Директор**", "Иван Иванов\nДиректор")
        self.check("<table><tr><td><b>Иван<br>Директор</b></td><td>тел</td></tr></table>",
                   "**Иван**\n**Директор**\nтел", "Иван\nДиректор\nтел")

    def test_bold_across_br_in_data_cell(self):
        text = richtext.html_to_markup("<table><tr><td><b>Имя<br>полное</b></td><td>Б</td></tr>"
                                       "<tr><td>1</td><td>2</td></tr></table>")
        self.assertEqual(text.split("\n")[0], "| **Имя** **полное** | Б |")

    def test_italic_pieces_glued(self):
        self.check("<i>a</i><i>b</i>", "*ab*", "ab")

    def test_bold_inside_bold(self):
        self.check("<b><b>x</b></b>", "**x**", "x")
        self.check("<strong><b>y</b></strong>", "**y**", "y")

    def test_unclosed_and_stray_tags(self):
        self.assertEqual(richtext.html_to_markup("</b>текст"), "текст")
        self.assertEqual(richtext.html_to_markup("<b>незакрытый"), "**незакрытый**")  # закрыт в конце строки


class TsvRandomTabTests(unittest.TestCase):
    def test_random_tab_not_table(self):
        """Случайный Tab в одном абзаце текста — не таблица."""
        self.assertIsNone(richtext.tsv_to_table("абзац\tс табом\nобычный абзац"))

    def test_empty_lines_allowed(self):
        self.assertIsNotNone(richtext.tsv_to_table("a\tb\n\nc\td"))


if __name__ == "__main__":
    unittest.main()
