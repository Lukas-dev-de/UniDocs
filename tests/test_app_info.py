"""Guards against drifting metadata: app_info vs pyproject / CHANGELOG."""

import re
import subprocess
import sys
from pathlib import Path

import app_info

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"


def _pyproject_text() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


def test_app_version_matches_pyproject():
    # flet build reads the version from pyproject.toml; the UI shows APP_VERSION.
    match = re.search(r'(?m)^version\s*=\s*["\']([^"\']+)["\']', _pyproject_text())
    assert match, "no [project] version in pyproject.toml"
    assert app_info.APP_VERSION == match.group(1)


def test_app_version_matches_changelog():
    text = CHANGELOG.read_text(encoding="utf-8")
    headings = re.findall(r"(?m)^##\s+v?(\d+\.\d+\.\d+)\s*$", text)
    assert headings, "no '## vX.Y.Z' heading in CHANGELOG.md"
    assert app_info.APP_VERSION == headings[0]


def test_flet_pins_agree():
    pins = re.findall(r'"flet[a-z-]*==([^"]+)"', _pyproject_text())
    assert len(pins) == 4, f"expected 4 flet pins, found {pins}"
    assert len(set(pins)) == 1, f"flet pins disagree: {sorted(set(pins))}"


def test_flet_pin_tool_prints_pin():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "flet_pin.py")],
        capture_output=True,
        text=True,
        check=True,
    )
    pins = set(re.findall(r'"flet[a-z-]*==([^"]+)"', _pyproject_text()))
    assert result.stdout.strip() in pins


def test_urls_follow_github_repo():
    assert app_info.GITHUB_REPO.count("/") == 1
    assert app_info.REPO_URL == f"https://github.com/{app_info.GITHUB_REPO}"
    for url in (
        app_info.RELEASES_URL,
        app_info.CHANGELOG_URL,
        app_info.ISSUES_URL,
        app_info.API_LATEST_RELEASE,
    ):
        assert url.startswith(app_info.REPO_URL) or app_info.GITHUB_REPO in url
