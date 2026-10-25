# UniDocs – offene Improvements (Stand 2.5.0)

Notiz fuer neuen Chat. Enthaelt nur Analyse, **nichts umgesetzt**.
Basis: Lesen von `src/main.py`, `src/models/*`, `src/app_storage/*`,
`src/ui/settings_dialog.py`, `src/updater.py`, `pyproject.toml`,
`requirements.txt`, `.github/workflows/*`, `tools/check_version.py`.
UI wurde nicht getestet (Regel: Agent testet UI nie selbst).

## Reihenfolge (Empfehlung)

1. `_atomic_write` Helper
2. `_safe_name` haerten
3. `config.json`-Pfad
4. pytest + CI
5. Rest (Architektur, Tooling, UX)

---

## 1. Datenverlust (hoch)

### 1.1 Nicht-atomare Writes
Alle JSON-Writes gehen direkt raus (`path.write_text(json.dumps(...))`).
Crash oder Stromausfall mitten im Write = kaputte Datei, Daten weg.

Betroffene Stellen:
- `src/app_storage/app_config.py` -> `AppConfig._save`
- `src/app_storage/home_store.py` -> `save`
- `src/app_storage/module_store.py` -> `save_order`, `_write_meta`,
  `_write_doc_tags`, `_write_global_tags`

Fix: ein Helper, z.B. in neuem `src/app_storage/io_utils.py`:

    def write_json(path, data):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

Alle o.g. Stellen darauf umstellen. Kein Verhalten sonst aendern.

### 1.2 `config.json` liegt im Code-Ordner
`app_config.py`: `_CONFIG_PATH = Path(__file__).parent.parent / "config.json"`.
Installiert (Windows Program Files, /Applications, AppImage read-only) kann
die App dort nicht schreiben -> Settings speichern failt oder crasht.
`.gitignore` ignoriert `config.json`, also ist es als User-Datei gedacht.

Fix: `platformdirs.user_config_dir("UniDocs")` (platformdirs ist schon
Dependency). Migration: alten Pfad einmal lesen, wenn vorhanden.

Zu pruefen: wie `__file__` im `flet build` Bundle aussieht.

### 1.3 `_safe_name` filtert `..` nicht
`module_store.py`:

    illegal = r'\/:*?"<>|'
    return "".join(c for c in title if c not in illegal).strip() or "Untitled"

Titel `".."` bleibt `".."` -> `_folder_for(module)` = `root/..` = Elternordner.
`save_module` macht dort `mkdir(parents=True)` + schreibt `.meta`,
`delete_module` macht `shutil.rmtree` auf den Elternordner.
Ausserdem offen: Windows-Reserved (`CON`, `NUL`, `PRN`, ...), Steuerzeichen,
Punkt/Leerzeichen am Ende, sehr lange Namen.

Fix: Whitelist + explizit `.`/`..` ablehnen + Tests.

## 2. Tests + CI (hoch)

- Kein pytest im Repo. `tools/*_smoke.py` sind handgeschriebene Skripte und
  laufen in keiner Pipeline.
- CI besteht nur aus `release-build.yml` (Version-Check + Build) und
  `ios.yml`. Kein Testjob.
- Kein Linter/Formatter konfiguriert (ruff fehlt).
- `requirements.txt` dupliziert `pyproject.toml` und pinnt `watchdog` nicht
  -> Drift-Risiko.

Vorschlag:
- Smoke-Checks nach `tests/` als pytest ueberfuehren (gleiche Asserts).
- `.github/workflows/ci.yml`: `ruff check`, `pytest`,
  `python tools/check_version.py`, Matrix Python 3.10 + 3.12.
- Dev-Deps: `pytest`, `ruff` in `[dependency-groups] dev`.
- `requirements.txt` entweder loeschen oder aus pyproject generieren.

## 3. Fehlerbehandlung

- Viele `except Exception: pass` / `print(...)` ohne User-Feedback:
  `settings_dialog.py`, `module_detail.py`, `module_sidebar.py`, `ics.py`,
  `module_store._icon_to_name`.
- `module_sidebar` Delete-Fehler und `module_detail` Rename-Fehler landen nur
  im Terminal. User merkt nichts.
- Fix: Fehlerdialog statt `print`, Logging-Setup (stdlib `logging`) fuer den
  Rest.

## 4. Architektur (mittel)

- `models/module.py`, `models/document.py`, `models/tag.py` = nackte Klassen
  ohne Typen und ohne Serialisierung. JSON-Bau steckt stattdessen im Store.
  Fix: `@dataclass` + `to_dict()` / `from_dict()` in models, Store macht nur IO.
- `_icon_to_name` scannt `dir(ft.Icons)` linear, einmal pro Modul.
  Fix: einmal ein Dict `{value: name}` bauen, cachen.
- Keine stabile Modul-ID. Rename + Gruppenwechsel in einem Schritt ist fragil:
  `main.on_module_update` vergleicht den alten Titel.
  Fix: UUID ins `.meta`, `.order` auf IDs umstellen (mit Fallback auf Namen
  fuer alte Ordner).
- `import shutil` mitten in Methoden (`module_store.delete_module`,
  `add_document`) -> nach oben.

## 5. Tooling / Version

- Version steht 3x: `pyproject.toml`, `src/ui/settings_dialog.py`
  (`CURRENT_VERSION`), `CHANGELOG.md`. `tools/check_version.py` prueft das,
  aber besser: nur eine Quelle (`importlib.metadata.version("unidocs")`),
  `check_version.py` prueft dann nur noch CHANGELOG vs. Code.
- `GITHUB_REPO` steht doppelt: `updater.py` und `settings_dialog.py`
  (`REPO_URL`); Kommentar sagt schon "keep in sync".
- Flet-Pins sind an 4 Stellen (pyproject, requirements, Workflow env,
  `FLET_CLI_VERSION`) – siehe Kommentar in `pyproject.toml`, bewusst so,
  aber ein Check-Script waere billig.

## 6. UX / Features (klein, pruefen ob gewollt)

- Storage-Ordner-Picker in `settings_dialog.py` ist auskommentiert
  ("TODO: auskommentiert, kommt spaeter wieder rein"). Entweder fertig bauen
  oder Issue anlegen.
- Kein Backup/Export. Bei reinem JSON-Store waere "Export als zip" billig
  und wertvoll.
- Globale Suche ueber Module + Dokumente habe ich im Code nicht gefunden
  **bitte pruefen**, ob sie irgendwo steckt (nur pro Modul?).
- Watcher (`watchdog`) Lifecycle: pruefen, ob der Observer beim App-Close
  sauber gestoppt wird (`page.on_close`). Nicht verifiziert.

## Regeln fuer die Umsetzung

- Kleine Schritte, pro Schritt Smoke-/pytest-Lauf.
- Kein UI-Selbsttest durch Agent. Klick-Anleitung an den Menschen.
- Kein `uv`, immer `./.venv/bin/python`.
- Nicht `src/assets/**` lesen.