# ToDoro

Простой список дел и канбан-доска для Windows с Тоторо-помощником.
A simple to-do list and kanban board for Windows with a Totoro helper.

**[⬇ Скачать установщик / Download](https://github.com/amfilippov/ToDoro/releases/latest)**

![Список задач и Тоторо-помощник / Task list with the Totoro helper](docs/screenshots/list.png)

> **Фан-проект / Fan project**
>
> Это некоммерческий любительский проект. Тоторо и Котобус — персонажи студии
> Ghibli (© Studio Ghibli). Их изображения в программе (папка `images` и
> `icon.ico`) — любительские рисунки, сделанные из любви к фильму. Программа не
> связана со студией Ghibli и не одобрена ею. Лицензия MIT распространяется только
> на код и не даёт никаких прав на персонажей. Если правообладатель попросит,
> изображения будут удалены.
>
> This is a non-commercial fan project. Totoro and the Catbus are characters
> owned by Studio Ghibli (© Studio Ghibli). Their images in this program (the
> `images` folder and `icon.ico`) are fan art made out of love for the film. This
> program is not affiliated with or endorsed by Studio Ghibli. The MIT License
> covers the code only and grants no rights to the characters. The images will be
> removed upon request of the rights holder.

## Возможности / Features

**Котобус увозит выполненную задачу** — отметьте задачу выполненной, и по низу окна проедет Котобус.
*The Catbus carries away a finished task.*

![Котобус увозит выполненную задачу / The Catbus carries away a finished task](docs/screenshots/catbus.gif)

**Канбан-доска** — колонки-статусы со своими цветами, карточки и колонки перетаскиваются мышью.
*Kanban board with colored status columns; drag cards and columns with the mouse.*

![Канбан-доска / Kanban board](docs/screenshots/board.png)

**Карточка задачи** — описание, срок, напоминание и кнопки действий в правой панели.
*Task card with description, due date, reminder and actions in the side panel.*

![Карточка задачи / Task card](docs/screenshots/card.png)

**Изменение задачи** — заголовок, описание, статус, срок с календарём, приоритет «Срочно / Важно»,
напоминание.
*Edit a task: title, description, status, due date with a calendar, urgent / important priority,
reminder.*

![Форма изменения задачи / Task edit form](docs/screenshots/form.png)

**Обновления в один клик** — программа сама сообщает о новой версии и ставит её, задачи сохраняются.
*One-click updates: the app tells you about a new version and installs it, keeping your tasks.*

![Окно обновления / Update dialog](docs/screenshots/update.png)

А ещё: экспорт и импорт задач в CSV (Excel), сортировка по столбцам, напоминания, письмо по задаче,
подробная справка (F1).
*Also: CSV export / import (Excel), column sorting, reminders, e-mail a task, built-in help (F1).*

## Запуск / Running

Проще всего — скачать установщик `ToDoro-Setup-*.exe` в разделе [Releases](https://github.com/amfilippov/ToDoro/releases).
Easiest: download the installer from [Releases](https://github.com/amfilippov/ToDoro/releases).

Из исходного кода нужен Python 3 с Tkinter / From source, requires Python 3 with Tkinter:

```
python todoro.py
```

Задачи хранятся в файле `%APPDATA%\ToDoro\todoro.db`.
Tasks are stored in `%APPDATA%\ToDoro\todoro.db`.

## Нашли ошибку? / Found a bug?

[Сообщите об ошибке](https://github.com/amfilippov/ToDoro/issues/new?template=bug_report.yml) или
[предложите идею](https://github.com/amfilippov/ToDoro/issues/new?template=feature_request.yml) —
прямо из программы: **☰ Меню → Обратная связь**.
*[Report a bug](https://github.com/amfilippov/ToDoro/issues/new?template=bug_report.yml) or
[suggest a feature](https://github.com/amfilippov/ToDoro/issues/new?template=feature_request.yml).*

## Что нового / Release notes

См. [RELEASE_NOTES.md](RELEASE_NOTES.md). Установщик — в разделе [Releases](https://github.com/amfilippov/ToDoro/releases).

## Лицензия / License

Код — MIT, © 2026 Machinist. См. [LICENSE](LICENSE).
Code is MIT-licensed, © 2026 Machinist. See [LICENSE](LICENSE).
