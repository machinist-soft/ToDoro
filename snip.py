"""Снимок области экрана: экран «замирает» и темнеет, мышью выделяется нужная часть.

select_area(root) возвращает картинку Pillow с выделенной областью или None (Esc, правая кнопка
мыши, слишком маленькая область). Снимок делается сразу — на нём остаются и всплывающие
подсказки, и открытые меню, как в «Ножницах» Windows.
"""
import ctypes
import tkinter as tk

MIN_SIZE = 4  # меньше — считаем, что просто щёлкнули мимо
TIMEOUT_MS = 120_000  # через 2 минуты без выделения — отмена
DIM = 0.5     # насколько темнеет экран вокруг выделения
LINE = "#4f8cff"
HINT = "Выделите область мышью  ·  Esc — отмена"


def virtual_screen():
    """Все мониторы вместе: (x, y, ширина, высота) в координатах окон этой программы."""
    try:
        metrics = ctypes.windll.user32.GetSystemMetrics
        x, y, width, height = (metrics(i) for i in (76, 77, 78, 79))  # SM_*VIRTUALSCREEN
        if width and height:
            return x, y, width, height
    except (AttributeError, OSError):
        pass
    return None


def select_area(root):
    from PIL import Image, ImageEnhance, ImageGrab, ImageTk

    shot = ImageGrab.grab(all_screens=True)  # в настоящих пикселях экрана
    screen = virtual_screen() or (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
    left, top, width, height = screen
    # При масштабе Windows 125–150 % окна программы меряются в «крупных» точках,
    # а снимок — в настоящих пикселях: показываем уменьшенную копию, вырезаем из настоящей.
    scale_x, scale_y = shot.width / width, shot.height / height
    shown = shot if shot.size == (width, height) else shot.resize((width, height), Image.LANCZOS)
    bright = ImageTk.PhotoImage(shown, master=root)
    dark = ImageTk.PhotoImage(ImageEnhance.Brightness(shown).enhance(DIM), master=root)

    window = tk.Toplevel(root, name="snip")  # по имени его находят проверки
    window.overrideredirect(True)
    window.geometry(f"{width}x{height}+{left}+{top}")
    window.attributes("-topmost", True)
    canvas = tk.Canvas(window, width=width, height=height, highlightthickness=0, bd=0,
                       cursor="crosshair")
    canvas.pack()
    canvas.create_image(0, 0, image=dark, anchor="nw")
    piece = tk.PhotoImage(master=root)  # светлая часть внутри выделения
    piece_item = canvas.create_image(0, 0, image=piece, anchor="nw", state="hidden")
    frame = canvas.create_rectangle(0, 0, 0, 0, outline=LINE, width=2, state="hidden")
    size_label = canvas.create_text(0, 0, anchor="sw", fill="white", font=("Segoe UI", 10),
                                    state="hidden")
    hint_x, hint_y = root.winfo_pointerx() - left, root.winfo_pointery() - top + 28
    hint = canvas.create_text(hint_x, hint_y, text=HINT, fill="white", font=("Segoe UI", 11))
    hint_box = canvas.create_rectangle(canvas.bbox(hint), fill="#1f2937", outline="")
    canvas.tag_raise(hint)
    state = {"start": None, "box": None, "result": None}

    def box(event):
        x0, y0 = state["start"]
        x1 = min(max(event.x, 0), width)
        y1 = min(max(event.y, 0), height)
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    def press(event):
        state["start"] = (event.x, event.y)
        canvas.delete(hint, hint_box)

    def drag(event):
        if state["start"] is None:
            return
        x0, y0, x1, y1 = state["box"] = box(event)
        piece.blank()
        if x1 - x0 >= 1 and y1 - y0 >= 1:
            piece.configure(width=x1 - x0, height=y1 - y0)
            piece.tk.call(piece, "copy", bright, "-from", x0, y0, x1, y1)
        canvas.coords(piece_item, x0, y0)
        canvas.coords(frame, x0, y0, x1, y1)
        real_w, real_h = round((x1 - x0) * scale_x), round((y1 - y0) * scale_y)
        canvas.coords(size_label, x0 + 2, y0 - 4 if y0 > 22 else y1 + 20)
        canvas.itemconfigure(size_label, text=f"{real_w} × {real_h}")
        for item in (piece_item, frame, size_label):
            canvas.itemconfigure(item, state="normal")

    def release(event):
        if state["start"] is None:
            return
        x0, y0, x1, y1 = box(event)
        if x1 - x0 >= MIN_SIZE and y1 - y0 >= MIN_SIZE:
            state["result"] = shot.crop((round(x0 * scale_x), round(y0 * scale_y),
                                         round(x1 * scale_x), round(y1 * scale_y)))
            window.destroy()
        else:  # просто щелчок — начинаем заново
            state["start"] = None
            for item in (piece_item, frame, size_label):
                canvas.itemconfigure(item, state="hidden")

    canvas.bind("<ButtonPress-1>", press)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<ButtonRelease-1>", release)
    for sequence in ("<Escape>", "<ButtonPress-3>"):
        window.bind(sequence, lambda e: window.destroy())
    # Забыли про выделение (или не дошли нажатия) — экран не должен оставаться тёмным навсегда
    window.after(TIMEOUT_MS, window.destroy)
    window.update_idletasks()
    window.lift()
    take_focus(window)
    window.after(150, lambda: take_focus(window))  # Windows иногда отдаёт фокус не сразу
    root.wait_window(window)
    return state["result"]


def take_focus(window):
    """Окну без рамки Windows не всегда даёт фокус клавиатуры — без него не сработает Esc."""
    if not window.winfo_exists():
        return
    try:
        ctypes.windll.user32.SetForegroundWindow(int(window.wm_frame(), 16))
    except (AttributeError, OSError, ValueError, tk.TclError):
        pass
    window.focus_force()
