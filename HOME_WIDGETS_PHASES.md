# Gruppen-Startseite: Phasenplan

Arbeitsplan für die Home-Page der Gruppen (Widget-Grid). Phasen 0–2 sind
umgesetzt, ab Phase 3 ist jede Phase als eigener Chat-Prompt formuliert und
kann so in einen neuen Chat kopiert werden.

## Stand nach Phase 2

Umgesetzt:

| Datei | Inhalt |
| --- | --- |
| `src/ui/group_home.py` | Seite, Widget-Grid, Bearbeiten-Toggle, Inline-Gruppen-Umbenennen |
| `src/ui/components/home_widgets/base.py` | `HomeWidget` Karte (Header, Zahnrad, `body`) |
| `.../quick_links.py` | Links-Kacheln + Edit-Dialog (Name/URL/Icon) |
| `.../recent_modules.py` | letzte 3 geöffnete Module, Klick öffnet Modul |
| `.../todos.py` | Todo-Liste (add/tick/löschen) |
| `.../calendar.py` | nächste Termine aus ICS-Feed + Maximieren-Overlay |
| `.../schedule.py` | **Platzhalter** ("Kein Stundenplan.") |
| `src/app_storage/home_store.py` | `.home.json` pro Gruppe |
| `src/app_storage/ics.py` | read-only ICS-Parser + Fetcher |
| `src/ui/module_sidebar.py` | schreibt `record_module_open` beim Modul-Klick |

Vorhandene API:

- `HomeStore(module_store)`: `load/save`, `set_quick_links`, `add/update/remove_quick_link`,
  `add_todo/toggle_todo/remove_todo`, `recent_modules`, `record_module_open`,
  `set_calendar_ics_url`.
- `HomeWidget`: Klassen-Attribute `TITLE`, `HAS_SETTINGS`; Methoden `refresh()`,
  `set_group(group)`, `set_edit_mode(on)`, `open_settings(e)`, `placeholder(text)`,
  `_safe_update(control)`, `_page()`, `_actions_row` (Buttons vor dem Zahnrad),
  `self.body` (Inhalt der Karte).
- Neuer Widget-Typ: Datei in `home_widgets/` anlegen, in
  `_WIDGET_TYPES` in `group_home.py` eintragen, Default-Liste in
  `home_store.DEFAULT_WIDGETS` ergänzen.

Offene Lücken: Widgets hinzufügen/entfernen/sortieren fehlt, Stundenplan leer,
ICS ohne Cache/Refresh, keine Smoke-Tests, kein CHANGELOG-Eintrag.

## Arbeitsregeln (gelten in jedem neuen Chat)

- Repo: `/home/Lukas/Documents/Projects/UniDocs`.
- **Kein `uv`.** Kein systemweites `python`/`flet`. Immer Venv explizit:
  `./.venv/bin/python`, `./.venv/bin/flet run`, `./.venv/bin/python tools/<script>.py`.
- Sprache im Chat: Caveman-Deutsch (kurz, knapp). Code/Kommentare/Docstrings
  normal; im Modul `home_widgets/` ist die Regel: Docstrings auf Englisch,
  Nutzertexte (Labels, Platzhalter, Dialogbuttons) auf Deutsch.
  Docstring-Aufbau wie in den bestehenden Dateien (Titel, Unterstrich, kurze
  Erklärung, ggf. Beispiel).
- **UI nie selbst testen** (kein headless `flet run`, keine Flet-Interna).
  Stattdessen: `py_compile`, Logik-Test mit `tempfile.mkdtemp()` + gepatchtem
  `update` (siehe Muster unten), danach Klick-Anleitung für den Menschen.
- Unsicherheit offen als Unsicherheit sagen.
- Wenig Befehle pro Frage, dann fragen. Keine Rabbit Holes.
- Branch: `feature/<id>-<kurz>`; Commit-Nachricht normal (Conventional Commits).

Logik-Test-Muster (kopf-los, ohne GUI):

```bash
cd src && ../.venv/bin/python -c "
import tempfile, pathlib
from app_storage.module_store import ModuleStore
from app_storage.home_store import HomeStore
from ui.group_home import GroupHomeDetail
root = pathlib.Path(tempfile.mkdtemp())
store = ModuleStore(root=root); g = store.create_group('School')
gh = GroupHomeDetail(store=store); gh.update = lambda: None
gh.set_group(g); gh._set_edit_mode(True)
for w in gh._widgets.values(): w.update = lambda: None
"
```

Netzwerk in Tests: `ui.components.home_widgets.calendar.fetch_ics` patchen,
nie echten Feed holen. `self.page` wirft bei nicht montierten Controls
`RuntimeError` – deshalb immer `HomeWidget._page()` benutzen.

---

## Phase 3 – Stundenplan-Widget

```
Neuer Chat, UniDocs-Repo (/home/Lukas/Documents/Projects/UniDocs), Branch feature/….
Lies zuerst HOME_WIDGETS_PHASES.md (Abschnitt "Stand nach Phase 2" und
"Arbeitsregeln"), dann src/ui/components/home_widgets/schedule.py,
base.py, quick_links.py und src/app_storage/ics.py.

Aufgabe: ScheduleWidget (Platzhalter) füllen.

Zuerst fragen, nicht bauen: Quelle des Stundenplans?
  A) eigene Einträge in der .home.json (Wochentag, Von/Bis, Titel, Raum, Farbe),
     Bearbeiten hinter dem Zahnrad wie bei Quick Links
  B) Termine aus dem ICS-Feed der Gruppe, gefiltert auf die aktuelle Woche
     (dann braucht es zusätzlich einfache RRULE-Expansion, siehe Phase 6)
  C) eigene Einträge, ICS später optional dazu
Meine Vorgabe: erst A umsetzen (offline, kein Netz nötig), C als Endziel.

Scope: nur schedule.py + HomeStore-Methoden (analog quick_links:
set_schedule_entries o.ä.) + Dialog. Keine Änderungen an anderen Widgets,
keine Widget-Verwaltung, kein Resize.

Anzeige: Wochenraster Mo–Fr als Spalten oder kompakte Liste "Mo 08:15–09:45
Analysis, HS 2"; heute hervorheben; Kachelhöhe begrenzt, Maximieren-Overlay
wie beim Kalender (gleiches Muster, inkl. _maximize_btn in _actions_row).

Definition of done:
- py_compile grün, Logik-Test (tempdir) grün: Eintrag speichern, Kachel rendert,
  nach set_group-Wechsel wieder da, ungültige Zeiten (Bis <= Von) werden
  abgelehnt.
- Klick-Anleitung für mich im Chat.
- Unsicherheiten klar benannt.
```

## Phase 4 – Widgets verwalten (hinzufügen / entfernen / sortieren)

```
Neuer Chat, UniDocs-Repo, Branch feature/….
Lies HOME_WIDGETS_PHASES.md (Stand + Arbeitsregeln), dann src/ui/group_home.py,
src/app_storage/home_store.py (Feld "widgets") und base.py.

Aufgabe: Widget-Grid im Bearbeiten-Modus konfigurierbar machen.
- Leere Zelle / "Widget hinzufügen"-Kachel öffnet Auswahl der verfügbaren
  Widget-Typen (_WIDGET_TYPES).
- Karte entfernen (X oder Kontextmenü im Bearbeiten-Modus), ohne die Daten in
  der .home.json zu löschen – erneutes Hinzufügen zeigt Links/Todos wieder.
  Also: "widgets" = Reihenfolge/Sichtbarkeit, Daten bleiben separat.
- Reihenfolge per Kontextmenü hoch/runter (Muster: module_sidebar.py) ODER
  Drag & Drop, wenn ohne Zusatz-Dependency machbar. Drag & Drop nicht erzwingen.
- Alles in HomeStore kapseln: add_widget/remove_widget/move_widget(order).
Definition of done: py_compile + Logik-Test (Reihenfolge bleibt nach Neustart
erhalten, Entfernen + Wiederhinzufügen bringt Daten zurück), Klick-Anleitung.
```

## Phase 5 – Karten-Optionen

```
Neuer Chat, UniDocs-Repo, Branch feature/….
Lies HOME_WIDGETS_PHASES.md, dann base.py, calendar.py, todos.py, group_home.py.

Aufgabe: pro Karte Optionen hinter dem Zahnrad, gespeichert in der .home.json
unter "widget_options": {"calendar": {...}, "todos": {...}}.
- Größe der Karte: klein / breit / groß (GridView-Item-Einstellung, max_extent
  oder col/row über einen Wrapper-Container; prüfe, was GridView in der
  installierten Flet-Version kann – bei Unsicherheit fragen).
- Kalender: Anzahl sichtbarer Termine.
- Todos: erledigte ausblenden (Anzeige), Standardfilter.
- Quick Links: Liste neu sortieren (optional).
Basis-API: HomeWidget.get_option(key, default) / set_option(key, value), das
liest/schreibt über HomeStore; jeder Karten-`refresh()` wertet die Optionen aus.
Definition of done: Optionen überleben Gruppenwechsel und Neustart, Default
bleibt bei fehlenden Keys, Logik-Test + Klick-Anleitung.
```

## Phase 6 – ICS-Härtung (Cache, Refresh, Serientermine, Zeitzonen)

```
Neuer Chat, UniDocs-Repo, Branch feature/….
Lies HOME_WIDGETS_PHASES.md, dann src/app_storage/ics.py und calendar.py.

Aufgabe, in dieser Reihenfolge, je Schritt einzeln bestätigen lassen:
1. Cache: letzte Antwort (Rohtext + Zeitstempel + ETag/Last-Modified) pro
   Gruppe ablegen, statt bei jedem Anzeigen neu zu laden. Ablage: Neben-Datei
   im Gruppenordner (z.B. .home.cache.json) oder HomeStore-Key. Dateiname muss
   vom Watcher ignoriert werden (siehe module_store-Watcher).
2. Refresh: ETag/If-Modified-Since nutzen, Fehler -> alten Cache anzeigen mit
   Hinweis "Stand <Zeit>".
3. RRULE: einfache Expansion für FREQ=WEEKLY, INTERVAL, BYDAY, UNTIL/COUNT.
   Alles andere (MONTHLY, BYSETPOS, EXDATE) ausdrücklich als "nicht unterstützt"
   dokumentieren, nicht still falsch anzeigen.
4. Zeitzonen: TZID auflösen (über zoneinfo) statt lokale Zeit anzunehmen;
   Verhalten dokumentieren.
5. Manueller "Neu laden"-Button im Kalender-Overlay.
Definition of done: alle Punkte per Logik-Test abgedeckt (ICS-Strings als
Fixtures, kein Netz), Grenzen im Docstring, Klick-Anleitung.
```

## Phase 7 – Qualität, Tests, Doku

```
Neuer Chat, UniDocs-Repo, Branch feature/….
Lies HOME_WIDGETS_PHASES.md und schau in tools/ (dort liegen bereits
*_smoke.py). Aufgabenvorschlag, vorher bestätigen lassen:
- tools/home_widgets_smoke.py im Stil der vorhandenen Smoke-Tests: tempdir,
  alle Widgets, Widget-Verwaltung, ICS-Fixtures.
- .home.json: kaputtes JSON / fehlende Keys / unbekannte Keys -> Defaults,
  Test dazu.
- .home.json + Watcher: prüfen, dass Schreiben aus der App keinen Reload und
  damit Modal-/Fokusverlust auslöst (analog .home.json-Handling, das in
  module_store schon existiert).
- CHANGELOG.md: Eintrag für die Startseiten-Widgets (neue Features, Verhalten).
- README.md: kurzer Abschnitt zu Startseite/Widgets/.home.json, falls noch
  nicht vorhanden.
Definition of done: Smoke-Test läuft grün über ./.venv/bin/python
tools/home_widgets_smoke.py, CHANGELOG-Eintrag, keine offenen TODOs im Code.
```

## Phase 8 – Vorlagen und Import/Export

```
Neuer Chat, UniDocs-Repo, Branch feature/….
Lies HOME_WIDGETS_PHASES.md, dann home_store.py und group_home.py.

Aufgabe: Gruppen-Konfiguration übertragbar machen.
- In der .home.json eine Vorlage aus einer anderen Gruppe übernehmen
  ("Widgets von <Gruppe> übernehmen"), Daten der Zielgruppe bleiben unberührt.
- Default-Konfiguration aus config.json statt Code-Konstanten (welche Widgets
  eine neue Gruppe startet).
- Export/Import der Widget-Konfiguration als Datei (JSON), ohne Links/Todos,
  wenn der Nutzer das so will – vorher fragen, welcher Umfang.
Definition of done: Logik-Test (Kopie legt nur "widgets"/"widget_options" um),
Klick-Anleitung, Doku der Dateistruktur.
```

---

## Prüf-Checkliste (jede Phase)

1. `./.venv/bin/python -m py_compile <geänderte Dateien>` grün.
2. Logik-Test mit tempdir grün, ohne Netz und ohne GUI.
3. Regressionstest der Vorphase (kurz wiederholen), da `base.py` zentral ist.
4. Klick-Anleitung im Chat: "mach X -> erwartet Y -> sag mir Z".
5. Unsicherheiten auflisten (Layout, Flet-Version, verschachtelte Dialoge).
6. Erst danach nächste Phase.
