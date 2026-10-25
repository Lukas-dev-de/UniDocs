"""
updater.py
----------
Update check + self-update for UniDocs (Windows installer).

Linux and macOS never install by themselves: the check only tells them a
release exists, the update dialog opens the release page.

Deliberately standard-library only (``urllib``) so it keeps working inside the
frozen ``flet build`` bundle without adding another dependency.

Usage
-----
    try:
        release = fetch_latest()
    except UpdateError as ex:
        ...                                   # offline / no release / rate limit
    if is_newer(release.version, APP_VERSION):
        asset = asset_for(release)            # (name, url) or None
        path = download(asset[1], temp_dir, progress=lambda done, total: ...)
        download_and_launch(asset)            # installs + restarts, then quit

Nothing in here touches the UI: the caller runs these functions in a
background thread (``page.run_thread``) and renders the results itself.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app_info import API_LATEST_RELEASE, RELEASES_URL

# GitHub rejects requests without a User-Agent.
USER_AGENT = "UniDocs-Updater"

_CHUNK = 64 * 1024
_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


class UpdateError(RuntimeError):
    """Anything that stopped the update check, with a user-readable message."""


@dataclass(frozen=True)
class Release:
    """The subset of a GitHub release the updater cares about."""

    version: str                      # "2.4.0" (tag without the leading "v")
    tag: str                          # "v2.4.0"
    notes: str                        # release body (markdown)
    page_url: str                     # html_url
    assets: dict[str, str] = field(default_factory=dict)  # name -> download url


# ---------------------------------------------------------------------------
# version handling
# ---------------------------------------------------------------------------

def parse_version(raw: str) -> tuple[int, int, int, int]:
    """``"v2.4.0"`` / ``"2.4.0-rc1"`` -> ``(2, 4, 0, rank)``.

    ``rank`` is 1 for a final release and 0 for a pre-release, so that
    ``2.4.0-rc1`` sorts *before* ``2.4.0``.
    """
    text = (raw or "").strip().lstrip("vV")
    match = _VERSION_RE.match(text)
    if not match or not match.group(1):
        raise UpdateError(f"Cannot read a version from {raw!r}")
    numbers = tuple(int(part) if part else 0 for part in match.groups())
    return (*numbers, 1 if not text[match.end():] else 0)


def is_newer(candidate: str, current: str) -> bool:
    """True when ``candidate`` is a later version than ``current``."""
    return parse_version(candidate) > parse_version(current)


def update_kind(latest: str, current: str) -> str | None:
    """Classify an update as ``"patch" | "minor" | "major"``.

    ``None`` means there is nothing to do (same or older version).

        2.3.0 -> 2.3.1   patch   (bug fixes, installed by itself)
        2.3.0 -> 2.4.0   minor
        2.3.0 -> 3.0.0   major
    """
    new = parse_version(latest)
    old = parse_version(current)
    if new <= old:
        return None
    if new[0] != old[0]:
        return "major"
    if new[1] != old[1]:
        return "minor"
    return "patch"


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

def _request(url: str, timeout: float) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )


def _explain(url: str, ex: Exception) -> str:
    """Turn a low-level urllib failure into one short sentence."""
    if isinstance(ex, urllib.error.HTTPError):
        if ex.code == 404:
            return "The repository has no published release yet."
        if ex.code in (403, 429):
            return "GitHub rate limit reached. Try again later."
        return f"GitHub answered with HTTP {ex.code}."
    if isinstance(ex, urllib.error.URLError):
        return f"No connection to GitHub ({ex.reason})."
    if isinstance(ex, TimeoutError):
        return "GitHub did not answer in time."
    return f"Unexpected error while reading {url}: {ex}"


def fetch_latest(timeout: float = 10.0) -> Release:
    """Read the newest published (non-draft, non-prerelease) release."""
    try:
        with urllib.request.urlopen(_request(API_LATEST_RELEASE, timeout), timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as ex:
        raise UpdateError(_explain(API_LATEST_RELEASE, ex)) from ex

    tag = data.get("tag_name") or ""
    if not tag:
        raise UpdateError("The latest release has no tag.")

    assets = {
        asset["name"]: asset["browser_download_url"]
        for asset in data.get("assets") or []
        if asset.get("name") and asset.get("browser_download_url")
    }

    return Release(
        version=tag.strip().lstrip("vV"),
        tag=tag,
        notes=data.get("body") or "",
        page_url=data.get("html_url") or RELEASES_URL,
        assets=assets,
    )


# ---------------------------------------------------------------------------
# asset selection
# ---------------------------------------------------------------------------

def asset_for(
    release: Release,
    system: str | None = None,
    *,
    appimage: bool | None = None,
) -> tuple[str, str] | None:
    """Pick the download for this OS: ``(asset name, download url)``.

    Matches the names the release workflow produces:

        UniDocs-<version>-windows-x86_64-setup.exe   (preferred on Windows)
        UniDocs-windows-x86_64.zip
        UniDocs-linux-x86_64.tar.gz                  (Linux install.sh build)
        UniDocs-linux-x86_64.AppImage                (preferred when running one)
        UniDocs-macos-universal.zip

    ``appimage`` overrides the "am I running inside an AppImage" detection,
    which the smoke tests need.
    """
    system = (system or platform.system()).lower()
    items = list(release.assets.items())

    def find(*needles: str, suffix: str | None = None) -> tuple[str, str] | None:
        for name, url in items:
            lowered = name.lower()
            if suffix and not lowered.endswith(suffix):
                continue
            if needles and not any(needle in lowered for needle in needles):
                continue
            return name, url
        return None

    if system == "windows":
        return find("windows", suffix=".exe") or find("windows")
    if system == "darwin":
        return find("macos", "mac-universal", "universal")
    if system == "linux":
        want_appimage = is_appimage() if appimage is None else appimage
        if want_appimage:
            return find("linux", suffix=".appimage")
        return (
            find("linux", suffix=".tar.gz")
            or find("linux", suffix=".tgz")
            or find("linux")          # older releases only had a zip
        )
    return None


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

def download(
    url: str,
    target_dir: Path | str,
    progress: Callable[[int, int], None] | None = None,
    timeout: float = 30.0,
) -> Path:
    """Stream ``url`` into ``target_dir`` and return the written file.

    ``progress(done, total)`` is called after every chunk; ``total`` is 0 when
    the server sends no Content-Length.
    """
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / (url.rsplit("/", 1)[-1] or "unidocs-update")

    try:
        with urllib.request.urlopen(_request(url, timeout), timeout=timeout) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with open(destination, "wb") as handle:
                while chunk := resp.read(_CHUNK):
                    handle.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except (urllib.error.URLError, TimeoutError, OSError) as ex:
        destination.unlink(missing_ok=True)
        raise UpdateError(_explain(url, ex)) from ex

    return destination


# ---------------------------------------------------------------------------
# installing
# ---------------------------------------------------------------------------

def appimage_path() -> Path | None:
    """The ``.AppImage`` file this copy runs from, when there is one.

    A running AppImage exports its own path in ``$APPIMAGE``. Only used to pick
    the AppImage asset over the tarball - nothing is ever written to that file.
    """
    raw = os.environ.get("APPIMAGE")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def is_appimage() -> bool:
    """True when UniDocs runs from an AppImage."""
    return appimage_path() is not None


def platform_can_self_update(system: str | None = None) -> bool:
    """Where a self-update is possible at all: Windows only.

    Windows has the Inno Setup installer (fixed AppId, replaces the running
    install). Linux and macOS installs are updated by hand from the release
    page, so nothing there can replace itself - no silent patch install, and the
    settings switch stays off and greyed out.
    """
    return (system or platform.system()).lower() == "windows"


def can_self_update(system: str | None = None) -> bool:
    """True when UniDocs can install its own update instead of just downloading.

    Windows: yes, the Inno Setup installer carries a fixed AppId and replaces
    the running install in place, wherever it lives. Linux and macOS: no, the
    update dialog only opens the release page there.
    """
    return platform_can_self_update(system)


def can_install_asset(asset: tuple[str, str] | None, system: str | None = None) -> bool:
    """True when this asset has an install form on this system.

    A setup ``.exe`` on Windows; a ``.tar.gz``/``.tgz`` archive or an
    ``.AppImage`` on Linux. Saying nothing about whether *this* copy may install
    it - that is ``can_install_update`` / ``can_self_update``.
    """
    if not asset:
        return False
    name = asset[0].lower()
    system = (system or platform.system()).lower()
    if system == "windows":
        return name.endswith(".exe")
    if system == "linux":
        return name.endswith((".tar.gz", ".tgz", ".appimage"))
    return False


def can_install_update(asset: tuple[str, str] | None, system: str | None = None) -> bool:
    """True when UniDocs can install this update itself, not only download it.

    Where ``can_self_update`` guards the *silent* patch install (and the
    settings switch), this is the question the update dialog asks before it
    offers an "install" button instead of a browser download.

    Windows: the setup. Everything else: never - Linux and macOS only open the
    release page, so there is no install button there.
    """
    system = (system or platform.system()).lower()
    return platform_can_self_update(system) and can_install_asset(asset, system)


# Where a downloaded update is parked before the installer picks it up.
UPDATE_TEMP_DIR = Path(tempfile.gettempdir()) / "unidocs-update"


def download_and_launch(
    asset: tuple[str, str],
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Download the Windows setup and hand it over to the installer.

    Returns once the detached helper is running - the caller is expected to
    quit the app right after, that is what the helper waits for.
    """
    if platform.system().lower() != "windows":
        raise UpdateError("UniDocs only installs its own updates on Windows.")
    _, url = asset
    payload = download(url, UPDATE_TEMP_DIR, progress=progress)
    launch_windows_installer(payload)
    return payload


def launch_windows_installer(installer: Path | str, wait_for_pid: int | None = None) -> None:
    """Start the downloaded setup silently, once this process is gone.

    Windows will not let the setup replace ``unidocs.exe`` while UniDocs is
    still running, so a tiny batch helper polls for the current process to
    disappear and only then hands over to the installer. The helper is detached
    from this process, so it survives the app closing. The installer restarts
    the app itself (``[Run]`` in installer/unidocs.iss).
    """
    installer = Path(installer)
    pid = wait_for_pid or os.getpid()
    helper = Path(tempfile.gettempdir()) / "unidocs-update.bat"
    helper.write_text(
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" 2>NUL | find "{pid}" >NUL\r\n'
        "if not errorlevel 1 (\r\n"
        "  ping -n 2 127.0.0.1 >NUL\r\n"
        "  goto wait\r\n"
        ")\r\n"
        f'start "" "{installer}" /SILENT /NORESTART\r\n',
        encoding="utf-8",
        newline="",
    )

    flags = 0
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
        flags |= getattr(subprocess, name, 0)

    subprocess.Popen(
        ["cmd", "/c", str(helper)],
        creationflags=flags,
        close_fds=True,
        cwd=str(installer.parent),
    )
