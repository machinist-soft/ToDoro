# Конфиденциальность / Privacy

**Коротко:** ToDoro ничего не собирает и никуда не отправляет ваши задачи. Нет учётных записей,
рекламы, статистики и телеметрии. Автор программы не получает никаких ваших данных.

*In short: ToDoro does not collect or send your tasks anywhere. No accounts, ads, analytics or
telemetry. The author receives none of your data.*

## Где хранятся данные / Where your data is stored

- **Личные списки** — задачи, описания, комментарии, вложенные файлы и настройки — лежат только на
  вашем компьютере, в папке `%APPDATA%\ToDoro`.
- **Общие списки** — в сетевой папке, которую вы сами указали в настройках (подпапка `ToDoro`).
  Их видят все, у кого есть доступ к этой папке. Кроме задач там записываются имена участников,
  имена их компьютеров и время последнего входа — чтобы показывать, кто автор, исполнитель и кто
  изменил задачу. Там же хранятся резервные копии за 14 дней.
- Удалить свои данные можно, удалив эти папки.

*Personal lists (tasks, comments, attachments, settings) stay on your computer in
`%APPDATA%\ToDoro`. Shared lists live in the network folder you choose and are visible to
everyone with access to it; they also store member names, computer names and last-seen time, plus
14 days of backups. Delete these folders to remove your data.*

## Outlook

Задача из письма создаётся, только когда вы сами нажимаете Ctrl+Alt+T или «Из письма». Программа
читает выделенное письмо через установленный у вас Outlook и сохраняет его копию и вложения в
задачу, а письму ставит категорию «В ToDoro». Других писем она не читает и никуда их не передаёт.

*A task is created from an e-mail only when you press Ctrl+Alt+T or “From e-mail”. ToDoro reads
the selected message through your local Outlook, saves it and its attachments into the task and
adds the “В ToDoro” category. It does not read other messages or send them anywhere.*

## Интернет / Network access

ToDoro обращается в интернет только в двух случаях:

- **Проверка обновлений** — запрос к GitHub «какая версия последняя» и, если вы согласились,
  загрузка установщика с GitHub. Отправляется только обычный технический запрос (адрес, как у любой
  программы, и название `ToDoro-updater`); задачи и настройки не отправляются.
  GitHub работает по своей [политике конфиденциальности](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement).
- **Обратная связь** — «Сообщить об ошибке» и «Предложить улучшение» лишь открывают в браузере
  форму на GitHub с уже подставленными версиями ToDoro и Windows. Отправляете её вы сами;
  сообщения на GitHub видны всем, поэтому не пишите в них личных данных.

Письмо по задаче открывается в вашей почтовой программе и отправляется только вами.

*ToDoro goes online only to check GitHub for updates (and download the installer if you agree) —
no tasks or settings are sent — and when you open the feedback form on GitHub in your browser,
prefilled with ToDoro and Windows versions; you submit it yourself and it is public. “E-mail a
task” opens your own mail program.*

## Изменения / Changes

Если программа начнёт обращаться с данными иначе, этот файл обновится, а изменение будет указано
в [списке изменений](RELEASE_NOTES.md).

*If data handling ever changes, this file and the release notes will say so.*
