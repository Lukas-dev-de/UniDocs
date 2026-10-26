# CLAUDE.md — Unidocs

## Agent Rules (wichtig, immer befolgen)

### Sprache
- Caveman-Deutsch: kurze Saetze, einfache Worte, knapp. Kein Blabla.
- Keine Hoeflichkeitsfloskeln, kein Fazit am Ende, keine Emojis.
- Code und Kommandos normal, Erklaerung kurz.

### UI-Tests
- Agent testet UI NIE selbst. Kein headless `flet run`, kein Graben in Flet-Interna,
  keine Websocket-/GUI-Simulation.
- Stattdessen: kurze Klick-Anleitung fuer den Menschen:
  "mach X -> erwartet Y -> sag mir Z".
- Code-Analyse reicht (Datei lesen, git, grep). Unsicherheit klar sagen:
  "laut Code X, bitte pruefen".

### Arbeit
- Keine Rabbit Holes. Wenige Befehle pro Frage, dann fragen.
- Bei Unklarheit fragen statt selbst bauen.

### Umgebung (wichtig)
- **Kein `uv` auf diesem Rechner.** `uv run ...` / `uv sync` schlagen fehl
  (`command not found`). Nicht versuchen.
- **Kein system-weites `flet`/`python`.** Nacktes `python -` findet `flet` nicht.
- venv liegt im Repo: `./.venv/bin/python`, `./.venv/bin/flet run`,
  `./.venv/bin/python tools/<script>.py`. Immer voller Pfad, nie auf `PATH` verlassen.

### Kontext-Hygiene
- `src/assets/**` (v.a. `icon.svg`, `icon.png`) NIEMALS lesen, greppen oder cat-en.
  Minifizierte Riesen-Dateien, sprengen den Kontext. Icons nur ueber Code-Namen
  behandeln; Inhalt/Design bei Bedarf beim Menschen erfragen.
- Grep/Suche immer auf `src/**.py`, `tools/**.py` oder konkrete Dateien einschraenken.
- Grosse Dateien (>300 Zeilen, z.B. `src/ui/module_detail.py`,
  `src/ui/settings_dialog.py`, `src/app_storage/module_store.py`) nicht komplett
  lesen. Erst `grep`, dann gezielter Zeilenbereich.
- `build/` und `.venv/` nicht durchsuchen.

## Project Overview
Unidocs ist eine Dokumenten-Management-App mit Flet. Ordnet Dateien in Module,
unterstuetzt Tags und bietet diverse UI-Features.

## Getting Started
- Voraussetzung: Python, venv im Repo (`./.venv`).
- Run: `./.venv/bin/flet run`.
- Web: `./.venv/bin/flet run --web`.
- Tools/Skripte: `./.venv/bin/python tools/<script>.py`.

## Project Structure
- `src/main.py`: Entry point.
- `src/ui/`: UI-Komponenten.
- `src/models/`: Datenstrukturen.
- `src/app_storage/`: Storage-Logik.
- `src/config.json`: Konfiguration.
- `tools/`: Hilfsskripte.

## Development Workflow
- Branching: `category/id-description`.
- Categories: `feature/`, `fix/`, `refactor/`, `style/`, `docs/`.
- Build: `flet build <platform>`.

## Key Concepts
- Module, Tags, Flet-basierte UI.

## Troubleshooting
- Langsamer erster Start: bekanntes Problem.
- Repository-Links in Settings: Fix offen.

## References
- [Flet Documentation](https://flet.dev/docs/)

## Handoff-Notes
- Aeltere Handoffs / offene Verbesserungen liegen in `.continue/notes/`.
  Bei Bedarf gezielt lesen (nicht alle auf einmal).
