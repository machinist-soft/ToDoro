# ToDoro для Android

Приложение для телефона: показывает и меняет задачи ToDoro, которые хранятся на компьютере.
Телефон подключается к значку ToDoro в трее (см. `../phone.py`) по QR-коду из
**☰ Меню → Подключить телефон**.

## Сборка

Нужны JDK 17+ и Android SDK (platform 35, build-tools 35). В `local.properties`:

```
sdk.dir=D\:\Claude\android-tools\sdk
signing.file=D\:\Claude\android-tools\keys\signing.properties
```

`signing.properties` (не в git): `storeFile`, `storePassword`, `keyAlias`, `keyPassword`.
Без него релиз подписывается отладочным ключом.

```
gradlew assembleRelease   →  app/build/outputs/apk/release/app-release.apk
```

Или из папки проекта ToDoro: `python tools/build_apk.py`.
