---
alwaysApply: true
---

# Umgebung (wichtig)

- **Kein `uv` auf diesem Rechner.** `uv run ...` und `uv sync` schlagen fehl
  (`command not found`). Nicht mehr versuchen.
- **Kein system-weites `flet`/`python`.** Nacktes `python -` findet `flet` nicht.
- venv liegt im Repo: `./.venv/bin/python`, `./.venv/bin/flet run`,
  `./.venv/bin/python tools/<script>.py`. Immer voller Pfad, nie auf `PATH` verlassen.

# Kontext-Hygiene

- `src/assets/**` (v.a. `icon.svg`, `icon.png`) NIEMALS lesen, greppen oder cat-en.
  Minifizierte Riesen-Dateien, sprengen den Kontext. Icons nur ueber Code-Namen
  behandeln; Inhalt/Design bei Bedarf beim Menschen erfragen.
- Grep/Suche immer auf `src/**.py`, `tools/**.py` oder konkrete Dateien einschraenken.
- Grosse Dateien (>300 Zeilen, z.B. `src/ui/module_detail.py`,
  `src/ui/settings_dialog.py`, `src/app_storage/module_store.py`) nicht komplett
  lesen. Erst `grep`, dann gezielter Zeilenbereich.
- `build/` und `.venv/` nicht durchsuchen.
