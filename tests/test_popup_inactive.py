"""Всплывающие окна закрываются, когда ToDoro перестаёт быть активной программой (сообщение #4):
открытый список ttk.Combobox, календарь срока (DatePicker) и меню (PopupMenu). Настоящий Tk,
окна за краем экрана; переключение в другую программу изображаем подменой app_is_active,
а не настоящим переключением окон. Данные пользователя не трогаются (пути db — во временной
папке)."""

import os
import shutil
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402

OFFSCREEN = "+-5000+-5000"
CHECK_MS = 20  # ускоренная проверка вместо APP_CHECK_MS, чтобы тесты шли быстро
TMP = None


def setUpModule():
    global TMP
    TMP = tempfile.mkdtemp()
    tmp = Path(TMP)
    patches = [mock.patch.object(db, "DATA_DIR", tmp),
               mock.patch.object(db, "DB_PATH", tmp / "todoro.db"),
               mock.patch.object(db, "LISTS_DIR", tmp / "lists"),
               mock.patch.object(db, "OLD_DB_PATHS", [])]
    for p in patches:
        p.start()
        unittest.addModuleCleanup(p.stop)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class PopupInactiveTests(unittest.TestCase):
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
        self.active = True
        self.T._watched_popups.clear()
        # настоящие старые правила — для проверок «старое и новое правило вместе»
        self.real_close_if_unfocused = self.T.DatePicker.close_if_unfocused
        self.real_check_focus = self.T._MenuWindow.check_focus
        # фоновые ошибки Tcl (например, «invalid command name» у отложенной проверки) копим
        self.root.tk.eval('set ::bgerrors {}; proc bgerror {msg} {lappend ::bgerrors $msg}')
        self.callback_errors = []
        patches = [mock.patch.object(self.root, "report_callback_exception",
                                     lambda *a: self.callback_errors.append(a)),mock.patch.object(self.T, "app_is_active", lambda: self.active),
                   mock.patch.object(self.T, "APP_CHECK_MS", CHECK_MS),
                   # закрытие по потере фокуса — отдельное старое правило; в тестах окно
                   # за краем экрана фокус может и не получить, поэтому его выключаем
                   mock.patch.object(self.T.DatePicker, "close_if_unfocused", lambda s: None),
                   mock.patch.object(self.T._MenuWindow, "check_focus", lambda s: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.frame = ttk.Frame(self.root)
        self.frame.pack(fill="both", expand=True)
        self.root.update()

    def tearDown(self):
        current = self.T._MenuWindow.current
        if current is not None:
            current.close()
        self.frame.destroy()
        self.pump(3 * CHECK_MS)

    def pump(self, ms):
        end = time.monotonic() + ms / 1000
        while True:
            self.root.update()
            if time.monotonic() >= end:
                break
            time.sleep(0.005)

    def pending_checks(self):
        """Сколько отложенных проверок close_when_inactive ещё ждёт в очереди Tk."""
        count = 0
        for after_id in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            try:
                script = self.root.tk.call("after", "info", after_id)
            except tk.TclError:
                continue
            if "check" in str(script):
                count += 1
        return count

    # --- выпадающий список ttk.Combobox ---

    def make_combobox(self):
        box = ttk.Combobox(self.frame, values=["Нет", "За 15 минут", "За час", "За день"],
                           state="readonly")
        box.pack()
        box.current(2)
        self.root.update()
        return box

    def posted(self, box):
        popdown = str(box) + ".popdown"
        return bool(int(self.root.tk.eval(
            f"expr {{[winfo exists {popdown}] && [winfo ismapped {popdown}]}}")))

    def post(self, box):
        self.root.tk.call("ttk::combobox::Post", str(box))
        self.pump(CHECK_MS)
        self.assertTrue(self.posted(box), "список не открылся")

    def unpost(self, box):
        self.root.tk.call("ttk::combobox::Unpost", str(box))
        self.pump(CHECK_MS)

    def test_combobox_stays_open_while_app_active(self):
        box = self.make_combobox()
        self.post(box)
        self.pump(6 * CHECK_MS)
        self.assertTrue(self.posted(box))
        self.assertGreater(self.pending_checks(), 0, "слежка за открытым списком не идёт")
        self.unpost(box)

    def test_combobox_closes_when_app_inactive_value_kept(self):
        box = self.make_combobox()
        self.post(box)
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertFalse(self.posted(box))
        self.assertEqual(box.get(), "За час")
        self.assertEqual(box.current(), 2)
        self.assertEqual(self.pending_checks(), 0)

    def test_combobox_can_reopen_after_auto_close(self):
        """После закрытия из-за другой программы список снова открывается и снова закрывается."""
        box = self.make_combobox()
        self.post(box)
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertFalse(self.posted(box))
        self.active = True
        self.post(box)
        self.pump(3 * CHECK_MS)
        self.assertTrue(self.posted(box))
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertFalse(self.posted(box))
        self.assertEqual(box.get(), "За час")

    def test_combobox_watch_stops_after_normal_close(self):
        box = self.make_combobox()
        self.post(box)
        self.unpost(box)
        self.pump(3 * CHECK_MS)
        self.assertEqual(self.pending_checks(), 0)
        with mock.patch.object(self.T, "app_is_active", lambda: False):
            self.pump(3 * CHECK_MS)  # программа неактивна, но слежки уже нет — ничего не делаем
        self.assertFalse(self.posted(box))

    def test_combobox_watch_stops_when_combobox_destroyed(self):
        box = self.make_combobox()
        self.post(box)
        self.unpost(box)
        box.destroy()
        self.pump(3 * CHECK_MS)
        self.assertEqual(self.pending_checks(), 0)

    def test_combobox_destroyed_while_posted(self):
        """Поле удалили вместе с открытым списком (закрыли форму) — без ошибок, слежка кончается."""
        box = self.make_combobox()
        self.post(box)
        errors = []
        with mock.patch.object(self.root, "report_callback_exception",
                               lambda *a: errors.append(a)):
            box.destroy()
            self.active = False
            self.pump(4 * CHECK_MS)
        self.assertEqual(errors, [])
        self.assertEqual(self.pending_checks(), 0)

    def test_one_watch_per_open(self):
        """Повторное открытие списка не плодит лишние проверки."""
        box = self.make_combobox()
        for _ in range(3):
            self.post(box)
            self.unpost(box)
        self.post(box)
        self.pump(2 * CHECK_MS)
        self.assertEqual(self.pending_checks(), 1)
        self.unpost(box)

    # --- календарь срока ---

    def test_date_picker_closes_when_app_inactive(self):
        picker = self.T.DatePicker(self.frame)
        picker.pack()
        self.root.update()
        picker.toggle_popup()
        popup = picker.popup
        self.pump(4 * CHECK_MS)
        self.assertIsNotNone(picker.popup, "календарь закрылся при активной программе")
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertIsNone(picker.popup)
        self.assertFalse(popup.winfo_exists())
        self.assertIsNone(picker.value)
        self.assertEqual(self.pending_checks(), 0)

    def test_date_picker_watch_stops_after_normal_close(self):
        picker = self.T.DatePicker(self.frame)
        picker.pack()
        self.root.update()
        picker.toggle_popup()
        self.pump(2 * CHECK_MS)
        picker.toggle_popup()  # обычное закрытие
        self.assertIsNone(picker.popup)
        self.pump(3 * CHECK_MS)
        self.assertEqual(self.pending_checks(), 0)
        # снова открыть — снова следит и закрывается при неактивной программе
        picker.toggle_popup()
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertIsNone(picker.popup)

    # --- меню ---

    def make_menu(self):
        sub = self.T.PopupMenu().command("Вложенный", lambda: None)
        return (self.T.PopupMenu().command("Первый", lambda: None)
                .submenu("Ещё", sub))

    def test_menu_closes_with_submenu_when_app_inactive(self):
        command = mock.Mock()
        menu = self.T.PopupMenu().command("Первый", command).submenu(
            "Ещё", self.T.PopupMenu().command("Вложенный", command))
        menu.popup(self.root, -4900, -4900)
        top = self.T._MenuWindow.current
        self.assertIsNotNone(top)
        submenu_row = top.rows[1][0]
        top.open_submenu(submenu_row)
        child = top.child
        self.assertIsNotNone(child)
        self.pump(4 * CHECK_MS)
        self.assertTrue(top.winfo_exists(), "меню закрылось при активной программе")
        self.assertEqual(self.pending_checks(), 1, "подменю не должно следить само")
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertIsNone(self.T._MenuWindow.current)
        self.assertFalse(top.winfo_exists())
        self.assertFalse(child.winfo_exists())
        command.assert_not_called()
        self.assertEqual(self.pending_checks(), 0)

    def test_menu_watch_stops_after_normal_close(self):
        self.make_menu().popup(self.root, -4900, -4900)
        top = self.T._MenuWindow.current
        self.pump(2 * CHECK_MS)
        top.close()
        self.pump(3 * CHECK_MS)
        self.assertEqual(self.pending_checks(), 0)

    def test_menu_watch_stops_after_command(self):
        """Выбор пункта закрывает меню и выполняет команду — слежка после этого не остаётся."""
        command = mock.Mock()
        self.T.PopupMenu().command("Первый", command).popup(self.root, -4900, -4900)
        top = self.T._MenuWindow.current
        top.activate(top.rows[0][0])
        self.pump(3 * CHECK_MS)
        command.assert_called_once()
        self.assertEqual(self.pending_checks(), 0)


    # --- повторный вызов, список слежки, фоновые ошибки ---

    def assert_no_errors(self):
        self.assertEqual(self.root.tk.splitlist(self.root.tk.eval("set ::bgerrors")), ())
        self.assertEqual(self.callback_errors, [])

    def test_fast_reopen_keeps_single_watch(self):
        """5 открытий и закрытий быстрее проверки, затем открытие — проверка одна."""
        box = self.make_combobox()
        for _ in range(5):
            self.root.tk.call("ttk::combobox::Post", str(box))
            self.root.update()
            self.root.tk.call("ttk::combobox::Unpost", str(box))
            self.root.update()
        self.root.tk.call("ttk::combobox::Post", str(box))
        self.root.update()
        self.assertTrue(self.posted(box))
        self.assertEqual(self.pending_checks(), 1)
        self.pump(3 * CHECK_MS)
        self.assertEqual(self.pending_checks(), 1)
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertFalse(self.posted(box))
        self.assertEqual(self.pending_checks(), 0)
        self.assert_no_errors()

    def test_watched_path_removed_after_normal_close(self):
        box = self.make_combobox()
        self.post(box)
        popdown = str(box) + ".popdown"
        self.assertIn(popdown, self.T._watched_popups)
        self.unpost(box)
        self.pump(3 * CHECK_MS)
        self.assertNotIn(popdown, self.T._watched_popups)

    def test_watched_path_removed_after_inactive_close(self):
        box = self.make_combobox()
        self.post(box)
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertEqual(self.T._watched_popups, set())

    def test_watched_path_removed_for_date_picker_and_menu(self):
        picker = self.T.DatePicker(self.frame)
        picker.pack()
        self.root.update()
        picker.toggle_popup()
        popup_path = str(picker.popup)
        self.make_menu().popup(self.root, -4900, -4900)
        menu_path = str(self.T._MenuWindow.current)
        self.assertEqual(self.T._watched_popups, {popup_path, menu_path})
        picker.close_popup()
        self.pump(3 * CHECK_MS)
        self.assertEqual(self.T._watched_popups, {menu_path})
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertEqual(self.T._watched_popups, set())

    def test_watched_path_removed_after_tcl_error(self):
        """Ошибка Tcl при проверке (испорченное имя окна) — слежка кончается, путь убран."""
        self.T.close_when_inactive(self.root, mock.Mock(), ".bad name {")
        self.assertIn(".bad name {", self.T._watched_popups)
        self.pump(3 * CHECK_MS)
        self.assertNotIn(".bad name {", self.T._watched_popups)
        self.assertEqual(self.pending_checks(), 0)

    def test_date_picker_close_leaves_no_tcl_error(self):
        """Календарь закрыт, а его проверка ещё ждёт — не падает с «invalid command name»."""
        picker = self.T.DatePicker(self.frame)
        picker.pack()
        self.root.update()
        picker.toggle_popup()
        picker.close_popup()  # сразу, до первой проверки
        self.pump(4 * CHECK_MS)
        self.assert_no_errors()
        self.assertEqual(self.pending_checks(), 0)

    def test_menu_close_leaves_no_tcl_error(self):
        self.make_menu().popup(self.root, -4900, -4900)
        self.T._MenuWindow.current.close()  # сразу, до первой проверки
        self.pump(4 * CHECK_MS)
        self.assert_no_errors()
        self.assertEqual(self.pending_checks(), 0)

    # --- старое правило (потеря фокуса) и новое (неактивная программа) вместе ---

    def test_date_picker_old_rule_after_inactive_close(self):
        picker = self.T.DatePicker(self.frame)
        picker.pack()
        self.root.update()
        picker.toggle_popup()
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertIsNone(picker.popup)
        self.real_close_if_unfocused(picker)
        self.pump(2 * CHECK_MS)
        self.assertIsNone(picker.popup)
        self.assert_no_errors()

    def test_date_picker_inactive_after_old_rule_close(self):
        picker = self.T.DatePicker(self.frame)
        picker.pack()
        self.root.update()
        picker.toggle_popup()
        with mock.patch.object(picker.popup, "focus_get", return_value=None):
            self.real_close_if_unfocused(picker)  # фокус ушёл мимо календаря
        self.assertIsNone(picker.popup)
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertEqual(self.pending_checks(), 0)
        self.assertEqual(self.T._watched_popups, set())
        self.assert_no_errors()

    def test_menu_old_rule_after_inactive_close(self):
        self.make_menu().popup(self.root, -4900, -4900)
        top = self.T._MenuWindow.current
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertFalse(top.winfo_exists())
        self.real_check_focus(top)
        self.pump(2 * CHECK_MS)
        self.assert_no_errors()

    def test_menu_inactive_after_old_rule_close(self):
        self.make_menu().popup(self.root, -4900, -4900)
        top = self.T._MenuWindow.current
        with mock.patch.object(top, "focus_get", return_value=None):
            self.real_check_focus(top)  # фокус ушёл из меню
        self.assertFalse(top.winfo_exists())
        self.assertIsNone(self.T._MenuWindow.current)
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertEqual(self.pending_checks(), 0)
        self.assertEqual(self.T._watched_popups, set())
        self.assert_no_errors()

    def test_menu_from_modal_dialog_returns_grab(self):
        """Меню из модального окна закрылось из-за другой программы — окно снова модальное."""
        dialog = tk.Toplevel(self.root)
        dialog.geometry("200x100" + OFFSCREEN)
        self.addCleanup(dialog.destroy)
        dialog.update()
        dialog.grab_set()
        self.addCleanup(dialog.grab_release)
        self.make_menu().popup(dialog, -4900, -4900)
        top = self.T._MenuWindow.current
        self.assertIs(top.previous_grab, dialog)
        self.assertIs(dialog.grab_current(), top)
        self.active = False
        self.pump(4 * CHECK_MS)
        self.assertFalse(top.winfo_exists())
        self.assertIs(dialog.grab_current(), dialog)
        self.assert_no_errors()


class AppIsActiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import todoro
        cls.T = todoro

    def fake_user32(self, hwnd, pid):
        user32 = mock.Mock()
        user32.GetForegroundWindow.return_value = hwnd

        def thread_process_id(window, ref):
            ref._obj.value = pid
            return 1
        user32.GetWindowThreadProcessId.side_effect = thread_process_id
        return mock.Mock(user32=user32)

    @unittest.skipUnless(os.name == "nt", "только Windows")
    def test_no_foreground_window_counts_as_active(self):
        """Windows как раз переключает окна (активного нет) — ничего не закрываем."""
        with mock.patch.object(self.T.ctypes, "windll", self.fake_user32(0, 1)):
            self.assertIs(self.T.app_is_active(), True)

    @unittest.skipUnless(os.name == "nt", "только Windows")
    def test_own_window_active(self):
        with mock.patch.object(self.T.ctypes, "windll", self.fake_user32(1234, os.getpid())):
            self.assertIs(self.T.app_is_active(), True)

    @unittest.skipUnless(os.name == "nt", "только Windows")
    def test_other_program_window_inactive(self):
        with mock.patch.object(self.T.ctypes, "windll", self.fake_user32(1234, os.getpid() + 1)):
            self.assertIs(self.T.app_is_active(), False)

    @unittest.skipUnless(os.name == "nt", "только Windows")
    def test_api_error_counts_as_active(self):
        windll = mock.Mock()
        windll.user32.GetForegroundWindow.side_effect = OSError("нет доступа")
        with mock.patch.object(self.T.ctypes, "windll", windll):
            self.assertIs(self.T.app_is_active(), True)

    def test_not_windows_counts_as_active(self):
        with mock.patch.object(self.T.os, "name", "posix"):
            self.assertIs(self.T.app_is_active(), True)

    @unittest.skipUnless(os.name == "nt", "только Windows")
    def test_real_call_returns_bool(self):
        self.assertIsInstance(self.T.app_is_active(), bool)


if __name__ == "__main__":
    unittest.main()
