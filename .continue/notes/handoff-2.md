# UniDocs – Handoff (Stand nach Schritt 5)

Alles uncommitted im Working Tree. Basis: Branch wie vorher, Version 2.5.0.

## Erledigt (diese Session)

1. **Atomare Writes** – neu `src/app_storage/io_utils.py` (`write_json`: tmp + `os.replace`,
   mkdir, tmp-cleanup bei Fehler). Umgestellt: `app_config._save`, `home_store.save`,
   `module_store` (`save_order`, `_write_meta`, `_write_doc_tags`, `_write_global_tags`).
2. **`_safe_name` gehaertet** – Konstanten `ILLEGAL_CHARS`, `_WINDOWS_RESERVED`,
   `MAX_NAME_LENGTH=100`. Steuerzeichen raus, `.`/`..`/leer -> `Untitled`, Punkte/Spaces
   am Ende weg, Reserved-Namen (`CON`, `COM1`, …) -> `_` dran, >100 Zeichen gekappt.
   Test: `tools/safe_name_smoke.py`.
3. **config.json** nach `platformdirs.user_config_dir("UniDocs", appauthor=False)`;
   Einmal-Migration aus altem Pfad neben Code (`_LEGACY_CONFIG_PATH`, nur lesen).
4. **pytest + CI** – `tests/` (`conftest`, `test_io_utils`, `test_safe_name`,
   `test_app_config`, `test_models`, `test_module_id`, `test_smoke_scripts` = ruft alle
   `tools/*_smoke.py` als Subprocess). `pyproject.toml`: dev-deps pytest+ruff,
   pytest-ini, ruff-config (`E4,E7,E9,F`, line-length 100, E402-ignore fuer tools/tests).
   Neu `.github/workflows/ci.yml` (Matrix 3.10/3.12, Deps aus pyproject gelesen,
   `ruff check`, `pytest -q`, `tools/check_version.py`).
5. **Architektur** – `import shutil/uuid` oben; `_icon_to_name` nutzt gecachtes Dict
   (`_icon_names()`, `_ICON_NAME_CACHE`, `_ICON_CACHE_LOCK`); `Module`/`Document`/`Tag`
   als Dataclasses, `Module.to_meta/from_meta`, `Tag.to_dict/from_dict`; Store macht nur IO.
   Stabile **Modul-UUID** im `.meta` (`Module.id`), Alt-Module bekommen sie beim Laden
   persistiert; `main.on_module_update` vergleicht IDs statt Titel.

## Verifikation

```
./.venv/bin/python -m pytest -q        # 76 passed
./.venv/bin/ruff check .               # clean
```

## Offen

- **Fehlerbehandlung**: viele `except Exception: pass` / `print(...)` ohne User-Feedback
  (`settings_dialog.py`, `module_detail.py`, `module_sidebar.py`, `ics.py`,
  `module_store._icon_to_name`). Fix: Fehlerdialog statt print + stdlib `logging`.
- **Tooling/Version**: Version 3x (`pyproject`, `settings_dialog.CURRENT_VERSION`,
  `CHANGELOG`), `GITHUB_REPO` doppelt (`updater.py` + `settings_dialog.REPO_URL`),
  Flet-Pins an 4 Stellen. Idee: nur eine Quelle (`importlib.metadata`).
- **`requirements.txt`**: wird nirgends referenziert (kein Workflow/README) und driftet.
  Entscheidung offen: loeschen oder generieren.
- **`.order` auf IDs umstellen**: bewusst NICHT gemacht (Sync-Bug war anders geloest).
  Nur mit Migration + Fallback + eigenem Test anfassen.
- **UX (klein)**: Storage-Picker in `settings_dialog.py` auskommentiert; kein Backup/Export;
  globale Suche ueber Module unklar (pruefen); Watcher-Stop bei App-Close pruefen.

## Regeln (weiterhin)

- Caveman-Deutsch, kurze Saetze.
- Kein `uv`. Immer `./.venv/bin/python`, `./.venv/bin/flet`, `./.venv/bin/ruff`.
- `src/assets/**` nie lesen. Grosse Dateien nur per grep + Zeilenbereich.
- Agent testet UI nie selbst -> Klick-Anleitung an den Menschen.
- **Niemals zwei `multi_edit` parallel** (Tool-Bug in dieser Session: hat zweimal
  `home_store.py` / `module_store.py` mit fremdem Dateiinhalt ueberschrieben).
  Ein Edit-Call pro Datei, danach `git diff` pruefen.
