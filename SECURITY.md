# Безопасность / Security

## Как сообщить об уязвимости / Reporting a vulnerability

Если вы нашли в ToDoro уязвимость, **не создавайте обычный Issue** — его видят все.
Сообщите о ней приватно:

1. Откройте вкладку [Security](https://github.com/machinist-soft/ToDoro/security) репозитория.
2. Нажмите **Report a vulnerability** и опишите проблему: что происходит, как это повторить,
   версию ToDoro и Windows.

Сообщение увидит только автор. Я постараюсь ответить в течение недели, а после исправления
выпущу новую версию и, если хотите, упомяну вас в списке изменений.

*Please **do not open a public issue** for security problems. Use the
[Security](https://github.com/machinist-soft/ToDoro/security) tab → **Report a vulnerability**
instead — only the maintainer will see it. Include what happens, how to reproduce it, and your
ToDoro and Windows versions. I aim to reply within a week and will publish a fixed release.*

## Поддерживаемые версии / Supported versions

Исправления выходят только для **последней версии**. Программа сама предлагает обновиться
(☰ Меню → Проверить обновления), поэтому достаточно поставить последний выпуск.

*Only the **latest release** receives fixes. The app offers updates itself.*

## Что важно знать / Good to know

- ToDoro — некоммерческий любительский проект, распространяется по лицензии MIT
  «как есть», без гарантий (см. [LICENSE](LICENSE)).
- Установщик скачивайте только со страницы
  [Releases](https://github.com/machinist-soft/ToDoro/releases). При обновлении из программы
  установщик проверяется по контрольной сумме SHA-256, которую публикует GitHub.
- Общая папка команды защищена только правами доступа к самой папке: кто может открыть папку,
  тот видит и может менять общие списки. Давайте доступ к ней только участникам команды.
- Какие данные использует программа — в [PRIVACY.md](PRIVACY.md).

*ToDoro is a non-commercial hobby project provided “as is” under the MIT License. Download the
installer only from Releases; in-app updates are verified with the SHA-256 checksum published by
GitHub. Shared team lists are protected only by the access rights of the network folder itself —
grant access to team members only. See [PRIVACY.md](PRIVACY.md) for what data the app uses.*
