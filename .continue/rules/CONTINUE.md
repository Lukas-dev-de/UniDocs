# Project: Unidocs

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
