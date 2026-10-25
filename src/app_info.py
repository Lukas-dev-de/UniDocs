"""Application metadata: version and links.

One place for the version the app itself reports and for the GitHub URLs, so
the UI, the updater and the tests cannot drift apart. ``pyproject.toml`` still
carries the same version number because ``flet build`` reads it for the bundle
metadata - ``tools/check_version.py`` (release) and ``tests/test_app_info.py``
(CI) verify that the two match.
"""

APP_VERSION = "2.5.0"

GITHUB_REPO = "Lukas-dev-de/UniDocs"          # owner/name, for the GitHub API
REPO_URL = f"https://github.com/{GITHUB_REPO}"
RELEASES_URL = f"{REPO_URL}/releases"
CHANGELOG_URL = f"{REPO_URL}/blob/main/CHANGELOG.md"
ISSUES_URL = f"{REPO_URL}/issues"
API_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
