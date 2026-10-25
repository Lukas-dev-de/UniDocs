"""Runs every hand-written smoke script under ``tools/`` as a pytest case.

The scripts already collect failures and exit non-zero, so this needs no
rewrite: it only makes them part of the normal ``pytest`` run and of CI.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((ROOT / "tools").glob("*_smoke.py"))


def test_scripts_were_found():
    assert SCRIPTS, "no tools/*_smoke.py found - did the layout change?"


@pytest.mark.parametrize("script", SCRIPTS, ids=[s.stem for s in SCRIPTS])
def test_smoke_script(script):
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, (
        f"{script.name} failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
