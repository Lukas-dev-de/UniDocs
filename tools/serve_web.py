#!/usr/bin/env python3
"""
serve_web.py
------------
Hosts UniDocs as a dynamic web app + sync API on a home server.

Backwards-compatible entry point: everything lives in ``unidocs_server`` now,
this script only forwards to it. Run it directly from a checkout or use the
``unidocs-server`` console command after ``pip install -e '.[web]'``.

    ./.venv/bin/python tools/serve_web.py --host 0.0.0.0 --port 8550
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from unidocs_server.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
