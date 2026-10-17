"""Значок ToDoro в трее (возле часов) — маленький помощник, который запускается вместе с Windows.

Он не открывает окно ToDoro и почти не занимает памяти, но держит сочетания клавиш:
Ctrl+Alt+T в Outlook — задача из выделенного письма, Ctrl+Alt+S — задача со снимка области
экрана. Помощник запускает ToDoro (или будит уже открытый), и тот делает задачу.
Щелчок по значку открывает ToDoro.

Запускается как «ToDoro.exe --tray» (из исходного кода: pythonw todoro.py --tray).
Автозапуск — значение «ToDoro» в разделе реестра HKCU\\...\\Run (только для текущего пользователя).
"""
import ctypes
import os
import subprocess
import sys
from pathlib import Path

TRAY_FLAG = "--tray"            # запустить помощника в трее
TRAY_QUIT_FLAG = "--tray-quit"  # закрыть помощника (установщик — перед обновлением и удалением)
WINDOW_CLASS = "ToDoroTrayWindow"  # по этому имени окно помощника находят другие копии ToDoro
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "ToDoro"
MUTEX = "Local\\ToDoro-tray"

# Пункты меню значка; пункты действий (письмо, снимок) — MENU_ACTIONS + номер действия
MENU_OPEN, MENU_EXIT, MENU_ACTIONS = 1, 2, 10
RETRY_TIMER, RETRY_MS = 1, 5000  # сочетание занято (открытым ToDoro) — пробуем снова каждые 5 с


def app_command(*args):
    """Команда запуска ToDoro: установленный ToDoro.exe или pythonw todoro.py (без чёрного окна)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    if python.name.lower() == "python.exe" and windowless.exists():
        python = windowless
    return [str(python), str(Path(__file__).resolve().with_name("todoro.py")), *args]


def launch(*args):
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(app_command(*args), close_fds=True, creationflags=flags)


# --- автозапуск вместе с Windows ---

def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return bool(winreg.QueryValueEx(key, RUN_VALUE)[0])
    except OSError:
        return False


def set_autostart(enabled):
    """Включает или выключает запуск помощника вместе с Windows. False — не получилось."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ,
                                  subprocess.list2cmdline(app_command(TRAY_FLAG)))
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


# --- помощник уже запущен? ---

def window():
    try:
        return ctypes.windll.user32.FindWindowW(WINDOW_CLASS, None)
    except (AttributeError, OSError):
        return 0


def is_running():
    return bool(window())


def start():
    """Запускает помощника, если он ещё не запущен."""
    if os.name == "nt" and not is_running():
        try:
            launch(TRAY_FLAG)
        except OSError:
            pass


def stop(wait_s=3.0):
    """Просит помощника закрыться и ждёт, пока его окно исчезнет."""
    import time
    hwnd = window()
    if not hwnd:
        return
    ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
    deadline = time.monotonic() + wait_s
    while window() and time.monotonic() < deadline:
        time.sleep(0.1)


# --- сам помощник ---

def run(icon_path, tip, open_app, actions):
    """Значок в трее и сочетания клавиш. Работает, пока не выберут «Закрыть значок» или не выйдут
    из Windows. open_app() — показать окно ToDoro; actions — [(сочетание, его название, пункт меню,
    действие)]: задача из письма Outlook, задача со снимка экрана."""
    import win32api
    import win32con
    import win32gui

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel32.CreateMutexW(None, False, MUTEX)
    if (mutex and ctypes.get_last_error() == 183) or is_running():  # ERROR_ALREADY_EXISTS
        return  # помощник уже работает
    user32 = ctypes.windll.user32
    wm_tray = win32con.WM_USER + 20
    taskbar_created = win32gui.RegisterWindowMessage("TaskbarCreated")  # Проводник перезапустился
    registered = set()  # номера действий, чьи сочетания удалось занять

    def register_hotkey(hwnd):
        for index, (hotkey, *_) in enumerate(actions):
            if index not in registered and user32.RegisterHotKey(hwnd, index + 1, *hotkey):
                registered.add(index)
        if len(registered) == len(actions):
            user32.KillTimer(hwnd, RETRY_TIMER)
        else:
            user32.SetTimer(hwnd, RETRY_TIMER, RETRY_MS, None)

    def load_icon():
        size = win32api.GetSystemMetrics(win32con.SM_CXSMICON)
        try:
            return win32gui.LoadImage(0, str(icon_path), win32con.IMAGE_ICON, size, size,
                                      win32con.LR_LOADFROMFILE)
        except win32gui.error:
            return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    icon = load_icon()

    def add_icon(hwnd):
        data = (hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, wm_tray, icon, tip)
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, data)
        except win32gui.error:  # панель задач ещё не готова (сразу после входа в Windows)
            user32.SetTimer(hwnd, 2, 3000, None)

    def show_menu(hwnd):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_OPEN, "Открыть ToDoro")
        for index, (_, hotkey_name, label, _) in enumerate(actions):
            win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_ACTIONS + index,
                                f"{label}\t{hotkey_name}")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_EXIT, "Закрыть значок")
        win32gui.SetMenuDefaultItem(menu, MENU_OPEN, False)
        x, y = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(hwnd)  # иначе меню не закроется щелчком мимо него
        win32gui.TrackPopupMenu(menu, win32con.TPM_RIGHTBUTTON | win32con.TPM_BOTTOMALIGN,
                                x, y, 0, hwnd, None)
        win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)

    def safely(action):
        try:
            action()
        except Exception:  # noqa: BLE001 — помощник не должен падать из-за одного неудачного нажатия
            pass

    def on_tray(hwnd, msg, wparam, lparam):
        if lparam == win32con.WM_LBUTTONUP:
            safely(open_app)
        elif lparam == win32con.WM_RBUTTONUP:
            show_menu(hwnd)
        return 0

    def on_command(hwnd, msg, wparam, lparam):
        command = win32api.LOWORD(wparam)
        if command == MENU_OPEN:
            safely(open_app)
        elif MENU_ACTIONS <= command < MENU_ACTIONS + len(actions):
            safely(actions[command - MENU_ACTIONS][3])
        elif command == MENU_EXIT:
            win32gui.DestroyWindow(hwnd)
        return 0

    def on_hotkey(hwnd, msg, wparam, lparam):
        if 1 <= wparam <= len(actions):
            safely(actions[wparam - 1][3])
        return 0

    def on_timer(hwnd, msg, wparam, lparam):
        if wparam == RETRY_TIMER:
            register_hotkey(hwnd)
        else:
            user32.KillTimer(hwnd, wparam)
            add_icon(hwnd)
        return 0

    def on_close(hwnd, msg, wparam, lparam):
        win32gui.DestroyWindow(hwnd)
        return 0

    def on_end_session(hwnd, msg, wparam, lparam):
        if wparam:
            win32gui.DestroyWindow(hwnd)
        return 0

    def on_destroy(hwnd, msg, wparam, lparam):
        for index in registered:
            user32.UnregisterHotKey(hwnd, index + 1)
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, 0))
        except win32gui.error:
            pass
        win32gui.PostQuitMessage(0)
        return 0

    def on_taskbar_created(hwnd, msg, wparam, lparam):
        add_icon(hwnd)
        return 0

    wc = win32gui.WNDCLASS()
    wc.hInstance = win32api.GetModuleHandle(None)
    wc.lpszClassName = WINDOW_CLASS
    wc.lpfnWndProc = {
        wm_tray: on_tray, win32con.WM_COMMAND: on_command, win32con.WM_HOTKEY: on_hotkey,
        win32con.WM_TIMER: on_timer, win32con.WM_CLOSE: on_close,
        win32con.WM_ENDSESSION: on_end_session, win32con.WM_DESTROY: on_destroy,
        taskbar_created: on_taskbar_created,
    }
    win32gui.RegisterClass(wc)
    # Обычное (не «только для сообщений») скрытое окно: ему Windows и установщик говорят «пора закрываться»
    hwnd = win32gui.CreateWindow(WINDOW_CLASS, "ToDoro", win32con.WS_OVERLAPPED, 0, 0, 0, 0,
                                 0, 0, wc.hInstance, None)
    add_icon(hwnd)
    register_hotkey(hwnd)
    win32gui.PumpMessages()
