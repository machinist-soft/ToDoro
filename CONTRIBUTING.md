# Как помочь проекту / Contributing

Спасибо, что хотите помочь! ToDoro — небольшой любительский проект одного автора, поэтому
правила простые.
*Thanks for helping! ToDoro is a small hobby project by one maintainer, so the rules are simple.*

## Ошибки и идеи / Bugs and ideas

[Сообщите об ошибке](https://github.com/machinist-soft/ToDoro/issues/new?template=bug_report.yml) или
[предложите идею](https://github.com/machinist-soft/ToDoro/issues/new?template=feature_request.yml).
Об уязвимостях — приватно, см. [SECURITY.md](SECURITY.md).
*Use the issue templates. Report vulnerabilities privately — see [SECURITY.md](SECURITY.md).*

## Запуск и тесты / Run and test

```
python todoro.py                      # запустить из исходников / run from source
python -m unittest discover tests     # все тесты / all tests
```

Тесты работают на временных файлах и не трогают ваши настоящие списки.
Устройство программы — в [docs/architecture.md](docs/architecture.md).
*Tests use temporary files and never touch your real lists. See [docs/architecture.md](docs/architecture.md).*

## Правила для правок / Rules for changes

- Интерфейс, комментарии, docstring'и и сообщения коммитов — **на русском**.
  *UI strings, comments, docstrings and commit messages are in Russian.*
- Новая функция или исправление — с тестом в `tests/`.
  *New features and fixes come with a test.*
- Заметную пользователю правку записывайте строкой в начало `RELEASE_NOTES.md`, в раздел
  `## Не выпущено` (плоский список, без вложенных пунктов).
  *Add a flat one-line entry under `## Не выпущено` in `RELEASE_NOTES.md`.*
- Новая функция — ещё и в справку (`help_text.py`) и в README.
  *Document new features in `help_text.py` and the README.*
- Работа с сетью — только в фоне (`in_background()`, `team.Probe`), никогда в потоке окна.
  Открытие списка ничего не пишет в файл.
  *Network work goes in the background only; opening a list must write nothing.*
- Окна сообщений — `ui.showinfo/askyesno`, не `tkinter.messagebox`.
  *Use `ui.*` dialogs, not `tkinter.messagebox`.*

## Pull request

1. Сделайте форк и ветку от `main`.
2. Проверьте, что все тесты проходят.
3. Опишите в PR, что изменилось и зачем.

*Fork, branch from `main`, make sure all tests pass, and describe what and why in the PR.*

Код распространяется по лицензии MIT, картинки Тоторо и Catbus — исключение (см. [NOTICE.md](NOTICE.md)).
*Code is MIT-licensed; the Totoro/Catbus images are excluded (see [NOTICE.md](NOTICE.md)).*
