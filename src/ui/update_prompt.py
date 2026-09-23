"""
ui/update_prompt.py
-------------------
The update dialog at startup.

``StartupUpdateCheck`` asks GitHub once per app start, in the background:

    patch release (2.3.0 -> 2.3.1) and "install patches automatically" is on
        -> install it silently, no question asked (installed builds: Windows
           setup, Linux install.sh / AppImage)
    anything else
        -> one popup, and only one: the version is remembered in config.json
           (``seen_update``), so a dismissed update never shows up again on the
           next launch. Installing it later is still possible from the settings.

Usage (main.py)
---------------
    StartupUpdateCheck(page, cfg).start()
"""

from __future__ import annotations

import os

import flet as ft

import updater
from app_storage.app_config import AppConfig
from ui.settings_dialog import CURRENT_VERSION
from ui.update_install import UpdateInstaller


def current_version() -> str:
    """``CURRENT_VERSION``, with a dev override for testing.

    No release has to be published to try the update paths out:

        UNIDOCS_FAKE_VERSION=2.2.0 .venv/bin/flet run      # 2.3.0 looks like a new minor
        UNIDOCS_FAKE_VERSION=2.3.0-rc1 .venv/bin/flet run  # 2.3.0 looks like a patch

    In VS Code the "Python: Unidocs (update popup)" launch config does the
    Same. The patch variant only installs itself where UniDocs can replace
    itself (Windows setup, Linux install.sh / AppImage); everywhere else the
    "Download" button just opens the browser.
    """
    return os.environ.get("UNIDOCS_FAKE_VERSION", "").strip() or CURRENT_VERSION


class UpdatePrompt(ft.AlertDialog):
    """One dialog for one release: either asks, or just installs.

    ``install_now`` is the silent path used for patch releases: no buttons, the
    download starts as soon as the dialog is on screen. If that download fails
    the buttons come back, so the user is not stuck with an error and no way
    out.
    """

    def __init__(
        self,
        release: updater.Release,
        asset: tuple[str, str] | None,
        *,
        current: str | None = None,
        kind: str = "minor",
        install_now: bool = False,
    ):
        super().__init__()
        current = current or current_version()
        self._asset = asset
        self._install_now = install_now
        self._self_update = updater.can_install_asset(asset) and updater.can_self_update()

        self._status = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self._ring = ft.ProgressRing(
            width=16, height=16, stroke_width=2, visible=install_now
        )
        self._installer = UpdateInstaller(
            self._status,
            on_busy=self._set_busy,
            on_failed=self._on_failed,
        )

        self._install_button = ft.FilledButton(
            "Install now" if self._self_update else "Download",
            icon=ft.Icons.DOWNLOAD,
            disabled=not asset,
            on_click=self._install if self._self_update else None,
            url=self._asset[1] if asset and not self._self_update else None,
        )
        self._later_button = ft.TextButton("Later", on_click=self._later)
        self._notes_button = ft.TextButton(
            "Release notes", icon=ft.Icons.DESCRIPTION, url=release.page_url
        )

        self.modal = True
        self.title = ft.Row(
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, size=20),
                ft.Text(
                    f"Installing UniDocs {release.version}"
                    if install_now
                    else "Update available",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                ),
            ],
        )

        content: list[ft.Control] = []
        if not install_now:
            content.append(
                ft.Text(
                    f"UniDocs {release.version} is available — you are on {current}."
                )
            )
            if not asset:
                content.append(
                    ft.Text(
                        "This release has no download for your system — the release "
                        "page has the details.",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                )
            else:
                content.append(
                    ft.Text(
                        "UniDocs closes, installs the update and starts itself again."
                        if self._self_update
                        else "The download opens in your browser: unpack it over your "
                        "UniDocs folder, or replace your .AppImage with it.",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    )
                )
                if kind == "patch" and self._self_update:
                    content.append(
                        ft.Text(
                            f"Patch releases like {release.version} can also be "
                            "installed by themselves — that switch is in the settings.",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        )
                    )
            content.append(self._notes_button)
        content.append(ft.Row(spacing=8, controls=[self._ring, self._status]))

        self.content = ft.Container(
            width=380,
            content=ft.Column(tight=True, spacing=10, controls=content),
        )
        # `_action_buttons` fills this in; empty while the silent patch install
        # is running.
        self.actions = [] if install_now else self._action_buttons()

    #  lifecycle 

    def did_mount(self):
        if self._install_now and self._asset:
            self._installer.start(self._asset[1])

    #  actions 

    def _action_buttons(self) -> list[ft.Control]:
        if not self._asset:
            return [ft.TextButton("Close", on_click=self._later)]
        return [self._later_button, self._install_button]

    def _later(self, e):
        self.open = False
        self.update()

    def _install(self, e):
        if self._asset:
            self._installer.start(self._asset[1])

    def _set_busy(self, busy: bool) -> None:
        self._ring.visible = busy
        self._install_button.disabled = busy

    def _on_failed(self, message: str) -> None:
        # Give the user a way out again: the silent install had no buttons.
        if self.page is None:
            return
        self.actions = self._action_buttons()
        self.update()


class StartupUpdateCheck:
    """Background update check that runs once per app start.

    Silent on purpose: no network, no release or a version the user already
    dismissed must not produce anything on screen.
    """

    def __init__(self, page: ft.Page, config: AppConfig, current: str | None = None):
        self._page = page
        self._cfg = config
        self._current = current or current_version()

    def start(self) -> None:
        self._page.run_thread(self._check_worker)

    #  worker (background thread) 

    def _check_worker(self) -> None:
        try:
            release = updater.fetch_latest()
            kind = updater.update_kind(release.version, self._current)
        except updater.UpdateError:
            return

        if kind is None or release.version == self._cfg.seen_update:
            return

        asset = updater.asset_for(release)
        auto = (
            kind == "patch"
            and self._cfg.auto_install_patches
            and updater.can_install_asset(asset)
            and updater.can_self_update()
        )
        self._page.run_task(self._offer, release, asset, kind, auto)

    #  event loop 

    async def _offer(
        self,
        release: updater.Release,
        asset: tuple[str, str] | None,
        kind: str,
        auto: bool,
    ) -> None:
        # Remembered *before* showing it: one popup per version, whether the
        # user installs right away, dismisses it or the download fails.
        self._cfg.seen_update = release.version

        prompt = UpdatePrompt(
            release,
            asset,
            current=self._current,
            kind=kind,
            install_now=auto,
        )
        self._page.overlay.append(prompt)
        prompt.open = True
        self._page.update()
