#!/usr/bin/env python3
"""
check_version.py
----------------
Keeps the version number of the project in sync.

The version is written down in three places and it is easy to forget one of
them, which is exactly what leads to a release whose files are labelled 2.2.0
while the app shows 2.3.0:

    pyproject.toml              [project] version
    src/ui/settings_dialog.py   CURRENT_VERSION (what the UI shows)
    CHANGELOG.md                newest "## vX.Y.Z" heading

Usage
-----
    python tools/check_version.py            # development check
    python tools/check_version.py v2.3.0     # strict check against a release tag

Development check
    The newest CHANGELOG heading is taken as the version currently being
    worked on. It must match ``CURRENT_VERSION``. A ``pyproject.toml`` that is
    still on the previous release only produces a warning, because the version
    there is only bumped with the release commit.

Strict check (used by the release workflow)
    The tag, ``pyproject.toml``, ``CURRENT_VERSION`` and the newest CHANGELOG
    heading must all be identical, otherwise the script exits with 1 and the
    build stops before anything is published.

The version that was checked is the only thing written to stdout (everything
else goes to stderr), so it can be captured in CI:

    VERSION=$(python tools/check_version.py v2.3.0)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SETTINGS_DIALOG = ROOT / "src" / "ui" / "settings_dialog.py"
CHANGELOG = ROOT / "CHANGELOG.md"

# X.Y.Z with an optional pre-release / local suffix, e.g. 2.3.0 or 2.3.0-rc1
VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?")


def log(message: str = "") -> None:
    print(message, file=sys.stderr)


def normalize(raw: str) -> str:
    """``v2.3.0``/``"2.3.0"`` -> ``2.3.0``."""
    raw = raw.strip().strip("\"'").strip()
    return raw[1:] if raw[:1] in ("v", "V") else raw


def assert_valid(version: str, source: str) -> str:
    if not VERSION_RE.fullmatch(version):
        log(f"error: '{version}' from {source} is not a version of the form X.Y.Z")
        raise SystemExit(2)
    return version


def read_pyproject_version() -> str | None:
    text = PYPROJECT.read_text(encoding="utf-8")
    try:  # Python 3.11+
        import tomllib

        return normalize(tomllib.loads(text)["project"]["version"])
    except ImportError:
        match = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)["\']', text)
        return normalize(match.group(1)) if match else None


def read_settings_version() -> str | None:
    text = SETTINGS_DIALOG.read_text(encoding="utf-8")
    match = re.search(r'(?m)^CURRENT_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    return normalize(match.group(1)) if match else None


def read_changelog_versions() -> list[str]:
    """All ``## vX.Y.Z`` headings, newest first (the file is newest-first)."""
    text = CHANGELOG.read_text(encoding="utf-8")
    return [normalize(m) for m in re.findall(r"(?m)^##\s+v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)\s*$", text)]


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args and args[0] in ("-h", "--help"):
        log(__doc__.strip())
        return 0
    if len(args) > 1:
        log("usage: python tools/check_version.py [vX.Y.Z]")
        return 2

    strict = bool(args)
    target = assert_valid(normalize(args[0]), "command line") if strict else None

    changelog_versions = read_changelog_versions()
    changelog_top = changelog_versions[0] if changelog_versions else None

    found: dict[str, str | None] = {
        "pyproject.toml": read_pyproject_version(),
        "src/ui/settings_dialog.py": read_settings_version(),
        "CHANGELOG.md (newest heading)": changelog_top,
    }

    problems: list[str] = []
    warnings: list[str] = []

    if strict:
        for source, value in found.items():
            if value is None:
                problems.append(f"{source}: no version found")
            elif value != target:
                problems.append(f"{source}: {value} (expected {target})")
    else:
        # The version under development is the newest CHANGELOG heading.
        target = changelog_top
        if target is None:
            log("error: no '## vX.Y.Z' heading in CHANGELOG.md")
            return 1
        for source, value in found.items():
            if source == "CHANGELOG.md (newest heading)":
                continue
            if value is None:
                problems.append(f"{source}: no version found")
            elif value != target and source == "pyproject.toml":
                warnings.append(
                    f"pyproject.toml is still on {value} - bump it to {target} with the "
                    f"release commit (or run: python tools/check_version.py v{target})"
                )
            elif value != target:
                problems.append(f"{source}: {value} (expected {target})")

    log(f"{'strict' if strict else 'development'} version check: {target}")
    for source, value in found.items():
        mark = "ok   " if value == target else "WRONG"
        log(f"  [{mark}] {source}: {value}")

    if warnings:
        log("")
        for warning in warnings:
            log(f"warning: {warning}")
    if problems:
        log("")
        for problem in problems:
            log(f"error: {problem}")
        log("")
        log("Version numbers do not match - see tools/check_version.py")
        return 1

    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
