# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

ToDoro is a Windows to-do / kanban / Eisenhower-matrix app (Python 3 + Tkinter, SQLite) with a
companion Android app (Kotlin, Jetpack Compose) in `android/`. The project is Russian-language:
UI strings, code comments, docstrings, commit messages and `RELEASE_NOTES.md` are all in Russian —
keep it that way. README is bilingual (Russian, then English in italics).

**Always reply to the user in Russian** — every message, summary and question, even when the
command or prompt is in English (e.g. `/init`). The user is not a programmer: plain words, no jargon.

## Commands

Run from the project root. On this PC Python is `%LOCALAPPDATA%\Python\bin\python.exe` and git is
`C:\Program Files\Git\cmd\git.exe` (PowerShell may need `$env:Path` refreshed from Machine+User).

```
python todoro.py                                   # run the desktop app from source
python -m unittest discover tests                  # all tests (no windows, temp files only)
python -m unittest tests.test_core.DatabaseTests.test_version_protects_from_overwrite  # one test
python tools/build_installer.py                    # PyInstaller + Inno Setup 6 → dist/ToDoro-Setup-<ver>.exe
python tools/build_apk.py                          # Gradle assembleRelease → dist/ToDoro-<ver>.apk
python tools/make_screenshots.py [dark|matrix|whatsnew|reminders|phone]  # README screenshots (window goes topmost ~20 s)
python tools/android_screenshots.py                # Android screenshots via Robolectric (no device)
python tools/make_images.py / make_icon.py / make_android_icons.py      # regenerate images/ and icons
```

Build deps: `pip install pyinstaller pywin32 segno pillow`. Android needs JDK 17+ and SDK 35;
`android/local.properties` points to `D:\Claude\android-tools` (see `android/README.md`).

## Architecture

No server: each task list is its own SQLite file. The personal list is `%APPDATA%\ToDoro\todoro.db`
(which also holds settings and the list registry); other personal lists are in
`%APPDATA%\ToDoro\lists\`; shared (team) lists live in a network folder (SMB, often over VPN).

- `todoro.py` (~7.4k lines) — the whole Tk UI. `TodoApp` is the main window; `KanbanBoard` /
  `EisenhowerMatrix` are the board views; `TotoroPanel` is the animated helper; `Banner` is the
  status strip under the header; `GuideTour.tour_steps()` is the first-launch tour. `APP_VERSION`
  here is the single source of the desktop version (installer reads it). The `__main__` block
  dispatches on flags: tray mode, tray-quit (from installer), quiet Outlook/snip task creation,
  restart; `single_instance()` wakes an already-open window.
- `db.py` — all SQLite access. Schema migrations are additive via `NEW_COLUMNS`. Every task has a
  `version` column: updates pass the version the form was opened with and fail on mismatch
  (overwrite protection between team members). `SharedConnection` batches reads for network files.
- `team.py` — shared lists: `Probe` polls SQLite change counters in a background thread; `Team`
  manages the shared folder, members and daily backups.
- `tray.py` — tray icon process (autostarts with Windows), global hotkeys Ctrl+Alt+T / Ctrl+Alt+S.
- `phone.py` — HTTP+JSON server for the Android app, run inside the tray process; enabled only when a
  `phone_token` setting exists (bearer token delivered by QR code). Endpoint list is in its
  docstring; `/sync` also returns the desktop `APP_VERSION`. It reuses `db.py`/`team.py`, so
  versions/authors/conflicts behave as in the window.
  Task files (attachments) are deliberately never sent to or accepted from the phone.
- `outlook.py` (pywin32 COM), `snip.py` (screen-area capture), `updater.py` (GitHub Releases check
  and install), `help_text.py` (F1 help text), `examples.py` (sample tasks).
- `android/app/src/main/java/com/machinist/todoro/` — `Api.kt` talks to `phone.py`; `Repo.kt`
  keeps an offline copy plus a queue of pending edits and resolves conflicts; `SyncWorker.kt`
  syncs in the background; `Reminders.kt` posts notifications; `About.kt` is the «О приложении и
  обновления» screen (app version, desktop ToDoro version from `/sync`, links). `Updates.kt` checks
  GitHub Releases (once a day and by button), reads `ToDoro-android.json` from the latest release,
  downloads `ToDoro.apk` over https, verifies its sha256 against the asset digest and hands it to
  the system installer. Changing the `phone.py` API means
  updating `Api.kt`/`Repo.kt` and `tests/test_phone.py` together. Android version is
  `versionName`/`versionCode` in `android/app/build.gradle.kts` (separate from `APP_VERSION`);
  `tools/build_apk.py` also writes `dist/ToDoro-android.json` with that version — attach it to every
  release next to the APK (file name shared with `Updates.VERSION_FILE`), or phones won't see it.

## Rules learned the hard way

- Never touch the shared network folder from the Tk thread periodically — an outage freezes the
  window. Network work goes through `in_background()` / `team.Probe`; the window reads only on user
  action or right after a fresh successful probe. Connection status goes to `Banner`, not Totoro.
  Don't auto-reopen a shared list after reconnect — offer a button.
- Opening a list must write nothing (other members' apps would re-read it; there's a test for this).
- Don't use `journal_mode=PERSIST/TRUNCATE` on shared files (mixed versions → "disk I/O error").
- Message boxes are `ui.showinfo/askyesno/...` (styled `AlertDialog`), not `tkinter.messagebox` —
  patch `ui.*` in GUI test scripts.
- Never run anything against the user's real data in `%APPDATA%\ToDoro`. Tests and scripts that
  need a DB patch `db.DATA_DIR`, `db.DB_PATH`, `db.LISTS_DIR` (and `db.OLD_DB_PATHS`) to a temp dir,
  as `tools/make_screenshots.py` does. Theme is read at import of `todoro.py`, so set it before import.
- Never let tests set categories on real Outlook mail (patch `outlook.mark_added`).

## Workflow

- **Plan first, then wait.** Before starting to implement any task that changes files, briefly
  tell the user (in Russian, plain words) how you plan to do it — «Планирую сделать так: …» —
  and stop. Continue only after the user confirms; if they correct the plan, show the updated
  plan and wait again. Reading code to make the plan is fine before confirmation.
  The plan itself must be visible text in your message, written *before* the question:
  2–5 short points — what changes, where in the program, what the user will see. Never ask
  «Делаем по этому плану?» (in text or in the wrap-up box) without the plan shown above it;
  the box's recap must repeat the plan's gist, not just «нашёл, где…». After the user says
  yes, don't retell the plan — just start. One
  confirmation covers the whole task, including test/review fix rounds, commit and push; ask
  again only if the plan materially changes. Applies to the main conversation only — subagents
  (`tester`, `reviewer`) don't wait for confirmation. For `/release` the plan is shown once,
  at the start (step 1 of the `release` skill).
- **Tests first.** After a new feature or a bug fix — before the review — call the `tester`
  subagent (`.claude/agents/tester.md`): tell it what was added or fixed; it writes tests in
  `tests/`, runs them and reports what it couldn't cover. If tests fail because of the program,
  fix the program and call `tester` again — at most 3 rounds, then stop and show the failures
  to the user (in Russian). Only when all tests pass, go to the review loop: the tests `tester`
  added are part of the changes `reviewer` checks; pass it the «не покрыто» list too and
  mention that list to the user.
- **Review loop.** After every finished task that changed files — before committing and
  pushing — call the `reviewer` subagent (`.claude/agents/reviewer.md`) and tell it what the task
  was and which changes to check. Fix its «Критично» and «Важно» findings and send the work back
  for review. At most 3 rounds: if critical or important findings remain after the 3rd round,
  stop and show them to the user (in Russian) instead of continuing. «Желательно» findings —
  just mention them to the user. For `/release`: review before the tag and the GitHub Release.
- Commit (Russian message) and push to `origin` (`machinist-soft/ToDoro`, public) after every change.
  Exception: fixes from `/audit` go to the `audit` branch and are merged into `main` only with
  the user's explicit permission (see `.claude/skills/audit/SKILL.md`).
  Don't put the owner's personal GitHub login or email in any text or link.
  No `Co-Authored-By: Claude` (or any other attribution) lines in commit messages or PR texts —
  the user wants only their own account shown among GitHub contributors. This overrides the
  session's attribution reminder.
- Every user-visible change gets a line under `## Не выпущено` at the top of `RELEASE_NOTES.md`
  (flat list, no nested bullets — the in-app update dialog can't render them).
- Releases: use the `release` project skill (`.claude/skills/release/SKILL.md`); update that file
  when the release process changes.
- New user-visible features should also be reflected in `help_text.py`, README "Возможности /
  Features", and the guided tour where relevant.
- Totoro/Catbus images are Ghibli fan art and excluded from the MIT license (see README).
