---
alwaysApply: true
---

In the UniDocs repo (/home/Lukas/Documents/Projects/UniDocs) there is NO `uv` on the machine and no system-wide flet/python. Never run `uv run`/`uv sync`/bare `python`/bare `flet`. Use the repo venv explicitly: `./.venv/bin/python`, `./.venv/bin/flet run`, `./.venv/bin/python tools/<script>.py`.