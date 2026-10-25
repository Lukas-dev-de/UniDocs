"""Guards the pins the build workflows cannot read from a shared file.

``FLUTTER_SDK_VERSION`` is a workflow-level env, so ``release-build.yml`` and
``ios.yml`` each carry their own copy. There is no file to read it from, but
there *is* an authoritative value: the Flutter version the pinned flet expects
(``flet.version.flutter_version``). This test fails as soon as one workflow is
bumped without the other, or without a flet upgrade that wants it.

The workflows are parsed with a regex instead of PyYAML on purpose: no extra
dev dependency, and only the two ``KEY: "value"`` lines are of interest.
"""

import re
from pathlib import Path

import flet.version

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
FLUTTER_ENV_RE = re.compile(r'(?m)^\s*FLUTTER_SDK_VERSION:\s*"([^"]+)"')


def _flutter_pin(workflow: str) -> str:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    matches = FLUTTER_ENV_RE.findall(text)
    assert len(matches) == 1, f"{workflow}: expected 1 FLUTTER_SDK_VERSION, got {matches}"
    return matches[0]


def test_workflows_pin_the_same_flutter_version():
    assert _flutter_pin("release-build.yml") == _flutter_pin("ios.yml")


def test_flutter_pin_matches_flet():
    # flet's client shell is built against this Flutter version; a mismatch
    # shows up as a blank window at runtime, not as a build error.
    assert _flutter_pin("release-build.yml") == flet.version.flutter_version


def test_flet_cli_version_is_not_hardcoded():
    """The flet pin must stay in pyproject.toml (tools/flet_pin.py reads it)."""
    for workflow in ("release-build.yml", "ios.yml"):
        text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
        assert "FLET_CLI_VERSION:" not in text, (
            f"{workflow}: FLET_CLI_VERSION must come from tools/flet_pin.py"
        )
