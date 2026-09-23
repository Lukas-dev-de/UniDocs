"""
ui/update_install.py
--------------------
The "download the update and restart into it" mechanics, shared by the startup
popup (``ui/update_prompt.py``) and the button in the settings menu.

Only the wrapping is UI: the network work runs in a background thread
(``page.run_thread``) and never touches a widget. Every widget write is posted
back with ``page.run_task``, so it happens on the page's event loop.

Usage
-----
    installer = UpdateInstaller(status_text, on_busy=self._set_busy,
                                on_failed=self._install_failed)
    installer.start(asset_url)
"""

from __future__ import annotations

from typing import Callable

import flet as ft

import updater


class UpdateInstaller:
    """Downloads one update asset and restarts UniDocs into the new version.

    ``status`` is the Text control the progress and errors are written into.
    ``on_busy(bool)`` fires before/after the run so the caller can disable its
    buttons, ``on_failed(message)`` fires when nothing was installed.
    """

    def __init__(
        self,
        status: ft.Text,
        *,
        on_busy: Callable[[bool], None] | None = None,
        on_failed: Callable[[str], None] | None = None,
    ):
        self._status = status
        self._on_busy = on_busy
        self._on_failed = on_failed
        self._last_percent = -1

    #  public 

    def start(self, url: str) -> None:
        page = self._status.page
        if page is None or not url:
            return
        self._last_percent = 0
        self._write_status("Downloading update… 0 %")
        if self._on_busy:
            self._on_busy(True)
        page.update()
        page.run_thread(self._download_worker, url)

    #  worker (background thread) 

    def _download_worker(self, url: str) -> None:
        page = self._status.page
        if page is None:  # window went away while we were busy
            return
        try:
            updater.download_and_launch(url, progress=self._report_progress)
        except (updater.UpdateError, OSError) as ex:
            page.run_task(self._failed, str(ex))
            return
        page.run_task(self._restarting)

    #  progress 

    def _report_progress(self, done: int, total: int) -> None:
        """Called from the download thread; throttled to whole percents."""
        page = self._status.page
        if not total or page is None:
            return
        percent = max(1, done * 100 // total)
        if percent == self._last_percent:
            return
        self._last_percent = percent
        page.run_task(self._show_progress, percent)

    async def _show_progress(self, percent: int) -> None:
        page = self._status.page
        if page is None:
            return
        self._write_status(f"Downloading update… {percent} %")
        page.update()

    #  outcome (event loop) 

    async def _failed(self, message: str) -> None:
        page = self._status.page
        if page is None:
            return
        self._last_percent = -1
        if self._on_busy:
            self._on_busy(False)
        self._write_status(f"Update failed: {message}", error=True)
        page.update()
        if self._on_failed:
            self._on_failed(message)

    async def _restarting(self) -> None:
        # The detached installer helper waits for this process to exit, swaps
        # the files and starts UniDocs again.
        page = self._status.page
        if page is None:
            return
        self._write_status("Installing update — UniDocs will restart…")
        page.update()
        await page.window.close()

    #  helpers 

    def _write_status(self, message: str, *, error: bool = False) -> None:
        self._status.value = message
        self._status.color = ft.Colors.ERROR if error else ft.Colors.ON_SURFACE_VARIANT
