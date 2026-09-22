# Project: Unidocs

## Agent Rules (wichtig - immer befolgen)

### Sprache
- Caveman-Deutsch: kurze Saetze, einfache Worte, knapp. Kein Blabla.
- Keine Hoeflichkeitsfloskeln, kein Fazit am Ende, keine Emojis.
- Code und Kommandos normal, Erklaerung kurz.

### UI-Tests
- Agent testet UI NIE selbst. Kein headless `flet run`, kein Graben in Flet-Interna,
  keine Websocket-/GUI-Simulation, keine Rebels.
- Stattdessen: kurze Klick-Anleitung fuer den Menschen geben:
  "mach X -> erwartet Y -> sag mir Z".
- Code-Analyse reicht (Datei lesen, git, grep). Unsicherheit klar als Unsicherheit sagen:
  "laut Code X, bitte pruefen".

### Arbeit
- Keine Rabbit Holes. Wenige Befehle pro Frage, dann fragen.
- Bei Unklarheit fragen statt selbst bauen.

## Project Overview
Unidocs is a document management application built with Flet. It organizes files into modules, supports tagging, and offers various UI features.

## Getting Started
- Prerequisites: Python, `uv`.
- Install: Clone repo, run `uv sync` (assumed).
- Run: `uv run flet run`.
- Web: `uv run flet run --web`.

## Project Structure
- `src/main.py`: Entry point.
- `src/ui/`: UI components.
- `src/models/`: Data structures.
- `src/app_storage/`: Storage logic.
- `src/config.json`: Configuration.

## Development Workflow
- Branching: `category/id-description`.
- Categories: `feature/`, `fix/`, `refactor/`, `style/`, `docs/`.
- Build: Use `flet build <platform>`.

## Key Concepts
- Modules, Tags, Flet-based UI.

## Troubleshooting
- Slow first start: Known issue.
- Repository links in settings: Fix pending.

## References
- [Flet Documentation](https://flet.dev/docs/)
