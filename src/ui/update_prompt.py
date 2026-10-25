"""
ui/update_prompt.py
-------------------
The update dialog at startup.

``StartupUpdateCheck`` asks GitHub once per app start, in the background:

    patch release (2.3.0 -> 2.3.1) and "install patches automatically" is on,
    on an install that can replace itself (Windows setup)
        -> install it silently, no question asked
    anything else
        -> one popup, and only one: the version is remembered in config.json
           (``seen_update``), so a dismissed update never shows up again on the
           next launch. Installing it later is still possible from the settings.

On Linux and macOS nothing is installed by the app itself: the button opens the
release page and the user picks the download there.

Usage (main.py)
---------------
    StartupUpdateCheck(page, cfg).start()
"""

from __future__ import annotations

import os

import flet as ft

import updater
from app_info import APP_VERSION
from app_storage.app_config import AppConfig
from ui.update_install import UpdateInstaller


def current_version() -> str:
    """``APP_VERSION``, with a dev override for testing.

    No release has to be published to try the update paths out:

        UNIDOCS_FAKE_VERSION=2.2.0 .venv/bin/flet run      # 2.3.0 looks like a new minor
        UNIDOCS_FAKE_VERSION=2.3.0-rc1 .venv/bin/flet run  # 2.3.0 looks like a patch

    In VS Code the "Python: Unidocs (update popup)" launch config does the
    Same. Only the Windows setup installs itself in place; on Linux, macOS and
    for a plain zip the same button just opens the release page in the browser.
    """
    return os.environ.get("UNIDOCS_FAKE_VERSION", "").strip() or APP_VERSION


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
        self._self_update = updater.can_install_update(asset)

        self._status = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self._ring = ft.ProgressRing(
            width=16, height=16, stroke_width=2, visible=install_now
        )
        self._installer = UpdateInstaller(
            self._status,
            on_busy=self._set_busy,
            on_failed=self._on_failed,
        )

        # Two shapes: an install button (Windows setup, needs an asset) or a
        # plain link to the release page - Linux, macOS and a Windows zip have
        # to be sorted out by hand there, so nothing is downloaded behind the
        # user's back.
        self._install_button = ft.FilledButton(
            self._install_label(),
            icon=ft.Icons.DOWNLOAD if self._self_update else ft.Icons.OPEN_IN_NEW,
            disabled=self._self_update and not asset,
            on_click=self._install if self._self_update else None,
            url=None if self._self_update else release.page_url,
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
                        else "The release page opens in your browser - download the "
                        "build for your system there and unpack it over your "
                        "UniDocs folder.",
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
            self._installer.start(self._asset)

    #  actions 

    def _install_label(self) -> str:
        return "Install now" if self._self_update else "Open release page"

    def _action_buttons(self) -> list[ft.Control]:
        # Always the same two buttons: a Windows setup without an asset only
        # greys the install button out (see __init__).
        return [self._later_button, self._install_button]

    def _later(self, e):
        self.open = False
        self.update()

    def _install(self, e):
        if self._asset:
            self._installer.start(self._asset)

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
