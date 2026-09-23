"""
updater.py
----------
Update check + self-update for UniDocs (Windows installer, Linux install.sh
and AppImage).

Deliberately standard-library only (``urllib``) so it keeps working inside the
frozen ``flet build`` bundle without adding another dependency.

Usage
-----
    try:
        release = fetch_latest()
    except UpdateError as ex:
        ...                                   # offline / no release / rate limit
    if is_newer(release.version, CURRENT_VERSION):
        asset = asset_for(release)            # (name, url) or None
        path = download(asset[1], temp_dir, progress=lambda done, total: ...)
        download_and_launch(asset[1])         # installs + restarts, then quit

Nothing in here touches the UI: the caller runs these functions in a
background thread (``page.run_thread``) and renders the results itself.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Keep in sync with REPO_URL in src/ui/settings_dialog.py.
GITHUB_REPO = "Lukas-dev-de/UniDocs"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
API_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

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
        page_url=data.get("html_url") or RELEASES_PAGE,
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

    A running AppImage exports its own path in ``$APPIMAGE``. The app itself
    lives read-only inside a temporary mount, so that env var is the only way
    to reach the file that has to be replaced.
    """
    raw = os.environ.get("APPIMAGE")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def is_appimage() -> bool:
    """True when UniDocs runs from an AppImage."""
    return appimage_path() is not None


def bundle_dir() -> Path:
    """The folder the frozen app lives in (``unidocs`` + ``data``/``lib``)."""
    return Path(sys.executable).resolve().parent


def _is_frozen_bundle() -> bool:
    """True when this process runs from a ``flet build`` bundle.

    Guards the Linux install route: under ``flet run`` ``sys.executable`` is a
    plain interpreter and unpacking a release archive over it would be a nasty
    surprise. The bundle is recognised by the launcher name and the ``data``
    folder Flutter puts next to it.
    """
    exe = Path(sys.executable)
    return (exe.name.lower().startswith("unidocs")
            and (exe.resolve().parent / "data").is_dir())


def platform_can_self_update(system: str | None = None) -> bool:
    """Where a self-update is possible at all: Windows and Linux.

    Windows has the Inno Setup installer (fixed AppId, replaces the running
    install). Linux has the per-user install (``installer/install.sh``) and the
    AppImage. macOS only ships a portable ``.app`` zip that cannot replace
    itself.
    """
    return (system or platform.system()).lower() in ("windows", "linux")


def location_is_replaceable(system: str | None = None) -> bool:
    """True when the *currently running* copy may overwrite itself.

    Linux only, and only asked from there (see ``can_self_update``): an AppImage
    can always be overwritten, a folder install only when it really is a bundle
    the user may write to. Running from source (``flet run``) is never
    replaceable.
    """
    if (system or platform.system()).lower() != "linux":
        return False
    appimage = appimage_path()
    if appimage is not None:
        return os.access(appimage, os.W_OK)
    return _is_frozen_bundle() and os.access(bundle_dir(), os.W_OK)


def can_self_update(system: str | None = None) -> bool:
    """True when UniDocs can install its own update instead of just downloading.

    Windows: yes, the Inno Setup installer carries a fixed AppId and replaces
    the running install in place, wherever it lives. Linux: only when this copy
    can really be overwritten, see ``location_is_replaceable``. macOS: no.
    """
    system = (system or platform.system()).lower()
    if not platform_can_self_update(system):
        return False
    if system == "linux":
        return location_is_replaceable(system)
    return True


def can_install_asset(asset: tuple[str, str] | None, system: str | None = None) -> bool:
    """True when this asset is something UniDocs can install by itself.

    A setup ``.exe`` on Windows; a ``.tar.gz``/``.tgz`` archive or an
    ``.AppImage`` on Linux. A Windows *zip* and anything macOS only get offered
    as a download.
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


# Where a downloaded update is parked before the installer picks it up.
UPDATE_TEMP_DIR = Path(tempfile.gettempdir()) / "unidocs-update"


def download_and_launch(url: str, progress: Callable[[int, int], None] | None = None) -> Path:
    """Download an update asset and hand it over to the platform's installer.

    Returns once the detached helper is running - the caller is expected to
    quit the app right after, that is what the helper waits for.
    """
    payload = download(url, UPDATE_TEMP_DIR, progress=progress)
    system = platform.system().lower()
    if system == "windows":
        launch_windows_installer(payload)
    elif system == "linux":
        launch_linux_installer(payload)
    else:
        raise UpdateError("UniDocs cannot install its own update on this platform.")
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


#  Linux  

# Swaps the install once the app has quit: an AppImage is overwritten in place,
# an install.sh build is replaced folder-by-folder. Written out next to the
# other update temp files before it is started detached.
_LINUX_HELPER = r"""#!/usr/bin/env bash
set -u
pid="$1"; payload="$2"; mode="$3"; target="$4"
while kill -0 "$pid" 2>/dev/null; do sleep 1; done

if [ "$mode" = "appimage" ]; then
  cp -f "$payload" "$target" && chmod +x "$target" || exit 1
  exec "$target"
fi

# archive mode: unpack beside the install, then swap the folders
new="$target.new.$$"
old="$target.old.$$"
rm -rf "$new"; mkdir -p "$new" || exit 1
tar -xzf "$payload" -C "$new" || { rm -rf "$new"; exit 1; }
mv "$target" "$old" || { rm -rf "$new"; exit 1; }
if ! mv "$new" "$target"; then mv "$old" "$target"; exit 1; fi
rm -rf "$old"
chmod +x "$target/unidocs" 2>/dev/null
cd "$target" && exec ./unidocs
"""


def launch_linux_installer(payload: Path | str, wait_for_pid: int | None = None) -> None:
    """Install a downloaded Linux update once this process is gone.

    Two shapes, picked from the file name:

    * ``.AppImage`` - over the file the app was started from (``$APPIMAGE``).
      ``$APPIMAGE`` points at the real file, the running app is a copy in a
      read-only mount, so this is the one thing that can be replaced.
    * ``.tar.gz``/``.tgz`` - unpacked over the install folder (the ``flet
      build`` bundle next to ``sys.executable``). That needs a folder install
      the user may write to, see ``location_is_replaceable``.

    Either way a bash helper waits for the process to exit, swaps the files and
    starts UniDocs again. It is detached, so it survives the app closing.
    """
    payload = Path(payload)
    name = payload.name.lower()
    pid = wait_for_pid or os.getpid()

    if name.endswith(".appimage"):
        target = appimage_path()
        if target is None:
            raise UpdateError("This copy is not running from an AppImage.")
        if not os.access(target, os.W_OK):
            raise UpdateError(f"Cannot write to {target}.")
        mode, target_arg = "appimage", str(target)
    elif name.endswith((".tar.gz", ".tgz")):
        if not location_is_replaceable("linux"):
            raise UpdateError("This UniDocs folder cannot replace itself.")
        mode, target_arg = "archive", str(bundle_dir())
    else:
        raise UpdateError(f"UniDocs cannot install {payload.name} by itself.")

    helper = UPDATE_TEMP_DIR / "unidocs-update.sh"
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(_LINUX_HELPER, encoding="utf-8", newline="\n")
    helper.chmod(0o755)

    subprocess.Popen(
        ["bash", str(helper), str(pid), str(payload), mode, target_arg],
        start_new_session=True,
        close_fds=True,
        cwd=str(helper.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
