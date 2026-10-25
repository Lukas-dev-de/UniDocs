#!/usr/bin/env python3
"""
flet_pin.py
-----------
Prints the flet version pinned in ``pyproject.toml``.

There are several flet pins (``flet``, ``flet-cli``, ``flet-desktop``,
``flet-web``) and they all have to be the same version: the client shell that
``flet build`` bundles comes from ``flet-cli``, and a client/Python mismatch
keeps the app window blank. pyproject.toml is the only place they are written
down; the build workflows read the number from here instead of repeating it:

    pip install "flet-cli==$(python tools/flet_pin.py)"

Exits 1 (and says why) if the pins in pyproject.toml disagree.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
PIN_RE = re.compile(r'"flet[a-z-]*==([^"]+)"')


def main() -> int:
    pins = PIN_RE.findall(PYPROJECT.read_text(encoding="utf-8"))
    if not pins:
        print("error: no flet pin in pyproject.toml", file=sys.stderr)
        return 1
    if len(set(pins)) > 1:
        print(f"error: flet pins disagree in pyproject.toml: {sorted(set(pins))}", file=sys.stderr)
        return 1
    print(pins[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
