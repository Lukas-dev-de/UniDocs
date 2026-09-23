"""
Startup update flow smoke test.

``ui.update_prompt.StartupUpdateCheck`` decides between four outcomes on every
app start, and getting that wrong is either nagging (popup on every launch) or
a silent install the user did not want. This script drives the real check with
a fake page, so the decision table is verified without network or GUI.

    patch release + "install patches automatically" on an install that can
    replace itself (Windows setup, Linux install.sh / AppImage)
        -> silent install, no buttons
    anything else that is newer
        -> one popup with "Install now"/"Download" + "Later"
    nothing newer, or that version was shown already, or check failed
        -> nothing at all
"""

import asyncio
import sys
import tempfile
from pathlib import Path

# The app package lives in <repo>/src and uses absolute imports
# (``from ui.theme import ...``), so put that directory on the path.
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from unittest import mock  # noqa: E402

import updater  # noqa: E402
from app_storage.app_config import AppConfig  # noqa: E402
from ui.update_prompt import StartupUpdateCheck  # noqa: E402

SETUP = ("UniDocs-2.3.1-windows-x86_64-setup.exe", "https://example.invalid/setup")
TAR = ("UniDocs-linux-x86_64.tar.gz", "https://example.invalid/tar")
APPIMAGE = ("UniDocs-linux-x86_64.AppImage", "https://example.invalid/appimage")

failures: list[str] = []


def check(label: str, got, expected) -> None:
    if got == expected:
        print(f"  ok   {label}")
        return
    failures.append(label)
    print(f"  FAIL {label}: got {got!r}, expected {expected!r}")


class FakePage:
    """Just enough page for the check: threads run inline, tasks are collected."""

    def __init__(self):
        self.overlay: list = []
        self.pending: list = []
        self.updates = 0

    def run_thread(self, handler, *args):
        handler(*args)  # flet runs this in a worker thread; inline is close enough

    def run_task(self, handler, *args):
        self.pending.append((handler, args))

    def update(self):
        self.updates += 1

    def drain(self):
        """Run everything the worker posted to the event loop."""
        while self.pending:
            handler, args = self.pending.pop(0)
            asyncio.run(handler(*args))
        return self.overlay


def run_check(
    released_version: str,
    current: str,
    *,
    asset=SETUP,
    system: str = "Windows",
    self_update: bool = True,
    patch_auto: bool = True,
    seen: str = "",
    release_error: str | None = None,
    config_path: Path | None = None,
):
    """Run one startup check and return (overlay, config, page).

    ``system`` is what ``platform.system()`` reports, so the asset/self-update
    rules can be exercised for Windows, Linux and macOS from any machine.
    """
    page = FakePage()
    cfg = AppConfig(config_path=config_path or Path(tempfile.mkdtemp()) / "config.json")
    cfg.auto_install_patches = patch_auto
    if seen:
        cfg.seen_update = seen

    release = updater.Release(
        version=released_version,
        tag=f"v{released_version}",
        notes="",
        page_url="https://example.invalid/release",
        assets=dict([asset] if asset else []),
    )

    def fake_fetch(timeout: float = 10.0):
        if release_error:
            raise updater.UpdateError(release_error)
        return release

    with (
        mock.patch.object(updater, "fetch_latest", fake_fetch),
        mock.patch.object(updater, "asset_for", lambda release, system=None: asset),
        mock.patch.object(updater, "can_self_update", lambda *a, **k: self_update),
        # can_install_asset() reads platform.system() itself; without this the
        # "Windows" cases would pass or fail depending on the machine running
        # this script.
        mock.patch.object(updater.platform, "system", lambda: system),
    ):
        check_run = StartupUpdateCheck(page, cfg, current=current)
        check_run.start()
        overlay = page.drain()

    return overlay, cfg, page


print("silent patch install (2.3.0 -> 2.3.1, Windows, switch on):")
overlay, cfg, page = run_check("2.3.1", "2.3.0")
check("one prompt", len(overlay), 1)
prompt = overlay[0] if overlay else None
check("install starts by itself", getattr(prompt, "_install_now", None), True)
check("no buttons while it runs", prompt.actions if prompt else "n/a", [])
check("title says what is happening", prompt.title.controls[1].value if prompt else None,
      "Installing UniDocs 2.3.1")
check("version remembered (no nagging next start)", cfg.seen_update, "2.3.1")
check("dialog is on screen", prompt.open if prompt else None, True)

print("silent patch install on Linux (install.sh build, switch on):")
overlay, _cfg, _ = run_check("2.3.1", "2.3.0", asset=TAR, system="Linux")
prompt = overlay[0] if overlay else None
check("one prompt", len(overlay), 1)
check("install starts by itself", getattr(prompt, "_install_now", None), True)

print("silent patch install from an AppImage, switch on:")
overlay, _cfg, _ = run_check("2.3.1", "2.3.0", asset=APPIMAGE, system="Linux")
prompt = overlay[0] if overlay else None
check("install starts by itself", getattr(prompt, "_install_now", None), True)

print("patch release, switch off -> asks instead:")
overlay, cfg, _ = run_check("2.3.1", "2.3.0", patch_auto=False)
check("one prompt", len(overlay), 1)
prompt = overlay[0] if overlay else None
check("waits for the user", getattr(prompt, "_install_now", None), False)
check("Later + Install now", [b.content for b in prompt.actions] if prompt else None,
      ["Later", "Install now"])
check("version remembered", cfg.seen_update, "2.3.1")

print("patch release on an install that cannot replace itself -> asks instead:")
overlay, _cfg, _ = run_check("2.3.1", "2.3.0", asset=TAR, system="Linux", self_update=False)
prompt = overlay[0] if overlay else None
check("still one prompt", len(overlay), 1)
check("offers a download, not an install", getattr(prompt, "_self_update", None), False)
check("button hands over to the browser", prompt._install_button.url if prompt else None,
      "https://example.invalid/tar")

print("patch release with a macOS zip -> download only:")
overlay, _cfg, _ = run_check(
    "2.3.1", "2.3.0",
    asset=("UniDocs-macos-universal.zip", "https://example.invalid/mac"),
    system="Darwin",
)
prompt = overlay[0] if overlay else None
check("offers a download, not an install", getattr(prompt, "_self_update", None), False)
check("button hands over to the browser", prompt._install_button.url if prompt else None,
      "https://example.invalid/mac")

print("minor release (2.4.0), switch on -> never silent:")
overlay, _cfg, _ = run_check("2.4.0", "2.3.0")
prompt = overlay[0] if overlay else None
check("one prompt", len(overlay), 1)
check("waits for the user", getattr(prompt, "_install_now", None), False)

print("nothing to do:")
overlay, cfg, _ = run_check("2.3.0", "2.3.0")
check("same version -> no dialog", overlay, [])
check("nothing written either", cfg.seen_update, "")
overlay, _cfg, _ = run_check("3.0.0", "2.3.0", seen="3.0.0")
check("already shown once -> no second popup", overlay, [])
overlay, _cfg, _ = run_check("2.3.1", "2.3.0", patch_auto=False, seen="2.3.1")
check("dismissed version -> no second popup", overlay, [])

print("release with nothing for this system:")
overlay, _cfg, _ = run_check("2.4.0", "2.3.0", asset=None)
prompt = overlay[0] if overlay else None
check("still tells the user", len(overlay), 1)
check("bottom line says so", "no download for your system" in prompt.content.content.controls[1].value
      if prompt else None, True)
check("close instead of install", [b.content for b in prompt.actions] if prompt else None,
      ["Close"])

print("check failed (offline / rate limit):")
overlay, cfg, _ = run_check("", "2.3.0", release_error="No connection to GitHub.")
check("stays quiet", overlay, [])
check("does not remember anything", cfg.seen_update, "")

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("UPDATE FLOW OK")
