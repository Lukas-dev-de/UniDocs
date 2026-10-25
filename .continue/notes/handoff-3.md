# UniDocs – Handoff (Stand nach Schritt 6: Fehlerbehandlung + Tooling/Version)

Alles uncommitted im Working Tree, Branch `main`, Version 2.5.0.
Vorgaenger: `.continue/notes/handoff-2.md` (Schritte 1-5: atomare Writes,
`_safe_name`, config-Pfad, pytest+CI, Architektur/Dataclasses/Modul-UUID).
Der Stand aus handoff-2 ist weiterhin im Working Tree und nicht committet.

## Erledigt in dieser Session

### 3. Fehlerbehandlung (still -> User-Feedback + logging)

Neu **`src/app_logging.py`**:

- rotierendes Datei-Log (`RotatingFileHandler`, 512 KB, 2 Backups)
- Pfad via `platformdirs.user_log_dir("UniDocs", appauthor=False)`:
  Linux `~/.local/state/UniDocs/log/UniDocs.log`, macOS `~/Library/Logs/UniDocs/`,
  Windows `%LOCALAPPDATA%\UniDocs\Logs\`
- Namespace `unidocs.*`, `propagate=False` (kein Flet-Rauschen im Log)
- faellt bei unschreibbarem Ordner auf `StreamHandler` zurueck, wirft nie
- `setup_logging()` einmal am Anfang von `main()`, sonst `get_logger(__name__)`
- Handler bekommt `set_name("unidocs")` -> Tests koennen ihn von pytest-Handlern trennen
- Test: `tests/test_app_logging.py` (4 Tests, inkl. Fallback + Idempotenz)

Umgestellt (alle `print()` in `src/` sind weg):

| Stelle | jetzt |
|---|---|
| `module_detail` Rename / Description / Datei oeffnen | `log.exception` + `show_error` (Snackbar) |
| `module_detail` Keyboard-Hook fehlt | `log.warning` (kein Dialog) |
| `module_detail` unmount Hook-Clear | `log.debug` |
| `module_sidebar` Modul loeschen | `log.exception` + neue `show_error` |
| `module_sidebar` Watchdog-Refresh | `log.debug` |
| `settings_dialog` durchgereichter Fremd-Key-Handler (2x) | `log.warning` |
| `ics` TZ / TZID / /etc/localtime / /etc/timezone | `log.debug` (Fallbacks) |
| `module_store._icon_names` / `_icon_to_name` | `log.debug` |
| `group_home` Gruppe umbenennen | `log.exception` + Snackbar |

Zusatz: `_commit_description` rollt bei Speicherfehler auf alten Text zurueck.
`show_error` in `module_detail` hat jetzt (wie die anderen) einen None-Page-Guard.

Bewusst still gelassen:
- `except RuntimeError: pass` um `control.update()` (`icon_selector`,
  `color_selector`, `home_widgets/*`, `group_home`) = Guard "noch nicht auf Page".
- `io_utils` tmp-`unlink` `except OSError: pass` = best effort im Fehlerpfad.

### Flet-0.84-API-Bruch (wichtig)

`page.show_snack_bar()` existiert in Flet 0.84 **nicht mehr**. Richtig:

```python
page.show_dialog(ft.SnackBar(content=ft.Text(message)))
```

Falscher Aufruf crasht erst zur Laufzeit im Click-Handler
(`AttributeError: 'Page' object has no attribute 'show_snack_bar'`).
Betroffen waren `module_detail`, `module_sidebar`, `group_home` -> alle 3 gefixt.

### Deprecations (Flet 0.83 entfernt die Helfer)

12 Stellen `ft.padding.*` / `ft.margin.*` / `ft.border.*` -> Klassenmethoden:
`ft.Padding.symmetric`, `ft.Margin.only/symmetric`, `ft.Border.all/only`.
Dateien: `module_detail`, `home_widgets/{base,calendar,quick_links,recent_modules,schedule}`,
`module_sidebar`, `group_home`.
In `src/` gibt es kein `ft.border.` / `ft.margin.` / `ft.padding.` mehr.

### Tooling / Version / Pins

Neu **`src/app_info.py`** = einzige Code-Quelle fuer Metadaten:

```python
APP_VERSION = "2.5.0"
GITHUB_REPO = "Lukas-dev-de/UniDocs"
REPO_URL / RELEASES_URL / CHANGELOG_URL / ISSUES_URL / API_LATEST_RELEASE
```

- `settings_dialog.CURRENT_VERSION` und `REPO_URL`-Block geloescht, importiert aus `app_info`
- `updater.GITHUB_REPO` / `RELEASES_PAGE` geloescht, importiert aus `app_info`
- `update_prompt` nutzt `APP_VERSION`
- `tools/check_version.py` liest jetzt `src/app_info.py` (Regex `APP_VERSION`)
  statt `settings_dialog.CURRENT_VERSION`; prueft weiter pyproject + CHANGELOG
- `pyproject.toml` behaelt `2.5.0` (flet build liest `project.version`, bestaetigt
  in `flet_cli/commands/build.py`); ohne `[build-system]` kein dynamic-version
- Neu `tests/test_app_info.py`: app_info == pyproject == CHANGELOG, alle 4 Flet-Pins
  gleich, `tools/flet_pin.py`-Output == Pin, URLs folgen `GITHUB_REPO`

Flet-Pins nur noch in `pyproject.toml`:

- neu **`tools/flet_pin.py`** -> druckt den Pin (`0.84.0`), exit 1 bei ungleichen Pins
- `FLET_CLI_VERSION: "0.84.0"` aus `.github/workflows/release-build.yml` und
  `ios.yml` entfernt; neuer Schritt:
  `python tools/flet_pin.py | sed 's/^/FLET_CLI_VERSION=/' >> "$GITHUB_ENV"`
  (`shell: bash`; beide Workflows haben `setup-python` vorher)
- **`requirements.txt` geloescht** (`git rm`); war nirgends referenziert, CI liest
  Deps aus pyproject

## Verifikation

```
./.venv/bin/python -m pytest -q        # 85 passed
./.venv/bin/ruff check .               # clean
./.venv/bin/python tools/check_version.py   # 2.5.0, alle 3 "ok"
```

Manuell vom Menschen bestaetigt: Snackbar bei Delete-Fehler funktioniert,
Log-Datei enthaelt Traceback.

## Offen / Unsicher

- **Workflow-Aenderungen sind lokal NICHT getestet.** YAML parst (pyyaml),
  aber `shell: bash` + `python` in Git Bash auf Windows-Runner ist ungeprueft.
  Beim naechsten Release-Build/ios-Dispatch: Schritt "Read flet pin from
  pyproject.toml" muss `FLET_CLI_VERSION=0.84.0` setzen, sonst bricht
  `pip install "flet-cli=="`.
- `FLUTTER_SDK_VERSION` steht weiter 2x (`release-build.yml`, `ios.yml`);
  pyproject hat kein Feld dafuer. Entweder `tools/flet_pin.py` erweitern oder lassen.
- `test_app_config.py` nutzt `"2.5.0"` als Fixture-String (kein Versionsbezug).
- UX klein: Storage-Picker in `settings_dialog.py` auskommentiert; kein Backup/Export;
  globale Suche ueber Module unklar (pruefen); Watcher-Stop bei App-Close pruefen.
- `.order` auf IDs umstellen: bewusst offen (nur mit Migration + Fallback + Test).
- Referenzen in `CHANGELOG.md` fuer 2.5.0 wurden nicht angefasst.

## Regeln (weiterhin)

- Caveman-Deutsch, kurze Saetze.
- Kein `uv`. Immer `./.venv/bin/python`, `./.venv/bin/flet`, `./.venv/bin/ruff`.
- `src/assets/**` nie lesen. Grosse Dateien (>300 Zeilen) nur per grep + Zeilenbereich.
- Agent testet UI nie selbst -> Klick-Anleitung an den Menschen.
- **Niemals zwei `multi_edit` parallel** (Tool-Bug). Ein Edit-Call pro Datei,
  danach `git diff` pruefen.
- Flet 0.84: Snackbar = `page.show_dialog(ft.SnackBar(...))`, Helfer nur als
  Klassenmethoden (`ft.Padding.symmetric`, `ft.Border.all`, `ft.Margin.only`).
