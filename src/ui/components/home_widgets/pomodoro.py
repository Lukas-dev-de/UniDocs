"""
ui/components/home_widgets/pomodoro.py
--------------------------------------
Pomodoro timer card for the group home page.

The card shows one big countdown and two buttons: start/pause and reset. The
total time is set in the widget's settings dialog (default 25 minutes). A
switch there mutes the chime that plays when the timer hits zero.

Only two things are stored in the group's .home.json as widget options:
``minutes`` (total length) and ``muted`` (bool). A running timer is *not*
persisted - it lives in the card while the app runs and starts fresh after a
restart.

The timer loop is a plain asyncio task on the page's event loop
(``page.run_task``); it sleeps in one-second steps and repaints the label after
each step. Nothing here touches a worker thread.
"""

from __future__ import annotations

import asyncio

import flet as ft

from ui.components.home_widgets.base import HomeWidget

# Default length and the range the settings dialog offers.
DEFAULT_MINUTES = 25
MIN_MINUTES = 1
MAX_MINUTES = 180
# How long the countdown sleeps between repaints, in seconds.
TICK = 1.0


def format_seconds(seconds: int) -> str:
    """``MM:SS`` (or ``H:MM:SS`` past an hour) for the big label."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def normalize_minutes(value) -> int:
    """Clamp a stored length onto the allowed range; broken input -> default."""
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MINUTES
    return max(MIN_MINUTES, min(MAX_MINUTES, minutes))


@ft.control
class PomodoroWidget(HomeWidget):
    TITLE = "Pomodoro"
    TYPE = "pomodoro"

    def __init__(self, store, module_store=None, on_open_module=None):
        super().__init__(store, module_store, on_open_module)

        # Runtime timer state (not persisted): remaining seconds, whether the
        # loop runs, and the running task so pause/reset can cancel it.
        self._remaining: int = DEFAULT_MINUTES * 60
        self._running: bool = False
        self._task: asyncio.Task | None = None

        # Settings dialog + its controls, built on first open and reused.
        self._settings_dialog = None
        self._minutes_field = None
        self._mute_switch = None

        self._time_text = ft.Text(
            format_seconds(self._remaining),
            size=40,
            weight=ft.FontWeight.BOLD,
        )
        self._start_button = ft.FilledButton(
            "Start",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self._toggle,
        )
        self._reset_button = ft.IconButton(
            icon=ft.Icons.RESTART_ALT,
            tooltip="Zurücksetzen",
            on_click=self._reset,
        )

    #  body 

    def refresh(self):
        """Rebuild body from the stored total (dropping any running state)."""
        self._stop_task()
        self._running = False
        self._remaining = self._total_seconds()
        self.body.controls.clear()
        self.body.controls.append(
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[self._time_text],
            )
        )
        self.body.controls.append(
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=4,
                controls=[self._start_button, self._reset_button],
            )
        )
        self._paint()

    def _total_seconds(self) -> int:
        return normalize_minutes(self.get_option("minutes", DEFAULT_MINUTES)) * 60

    def _paint(self):
        """Write the current state into the label and the buttons."""
        self._time_text.value = format_seconds(self._remaining)
        self._start_button.content = "Pause" if self._running else "Start"
        self._start_button.icon = (
            ft.Icons.PAUSE if self._running else ft.Icons.PLAY_ARROW
        )
        self._safe_update(self._time_text)
        self._safe_update(self._start_button)

    #  timer 

    def _toggle(self, e=None):
        if self._running:
            self._pause()
        else:
            self._start()

    def _start(self):
        if self._running:
            return
        if self._remaining <= 0:
            self._remaining = self._total_seconds()
        page = self._page()
        if page is None:
            return
        self._running = True
        self._paint()
        self._task = page.run_task(self._run)

    def _pause(self):
        self._stop_task()
        self._running = False
        self._paint()

    def _reset(self, e=None):
        self._stop_task()
        self._running = False
        self._remaining = self._total_seconds()
        self._paint()

    def _stop_task(self):
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()

    async def _run(self):
        """Count down one second at a time until zero, pause or cancel."""
        try:
            while self._running and self._remaining > 0:
                await asyncio.sleep(TICK)
                if not self._running:
                    return
                self._remaining = max(0, self._remaining - int(TICK))
                self._paint()
            if self._running and self._remaining <= 0:
                self._running = False
                self._paint()
                await self._chime()
        except asyncio.CancelledError:
            # Pause / reset cancelled us; state already updated by the caller.
            raise

    async def _chime(self):
        """Play the end signal unless the widget is muted."""
        if bool(self.get_option("muted", False)):
            return
        try:
            await ft.Audio.play(ft.Audio.END)
        except Exception:
            # A missing platform sound is not worth a crash.
            pass

    #  settings 

    def open_settings(self, e=None):
        page = self._page()
        if page is None:
            return
        if self._settings_dialog is None:
            self._minutes_field = ft.TextField(
                label="Gesamtzeit (Minuten)",
                dense=True,
                keyboard_type=ft.KeyboardType.NUMBER,
                hint_text=f"z. B. {DEFAULT_MINUTES}",
            )
            self._mute_switch = ft.Switch(
                label="Stumm (kein Ton am Ende)",
                value=False,
            )
            self._settings_dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Pomodoro"),
                content=ft.Container(
                    width=320,
                    content=ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[
                            self._minutes_field,
                            self._mute_switch,
                            ft.Text(
                                f"Zwischen {MIN_MINUTES} und {MAX_MINUTES} Minuten.",
                                size=11,
                                color=ft.Colors.OUTLINE,
                            ),
                        ],
                    ),
                ),
                actions=[
                    ft.TextButton(
                        "Abbrechen", on_click=lambda e: self._close_settings()
                    ),
                    ft.FilledButton("Speichern", on_click=lambda e: self._save()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.overlay.append(self._settings_dialog)

        self._minutes_field.value = str(
            normalize_minutes(self.get_option("minutes", DEFAULT_MINUTES))
        )
        self._mute_switch.value = bool(self.get_option("muted", False))
        self._settings_dialog.open = True
        page.update()

    def _save(self):
        """Store length and mute flag, then restart the card from the new total."""
        try:
            minutes = int((self._minutes_field.value or "").strip())
        except (TypeError, ValueError):
            minutes = DEFAULT_MINUTES
        minutes = normalize_minutes(minutes)
        self.set_option("minutes", minutes)
        self.set_option("muted", bool(self._mute_switch.value))
        self._close_settings()
        self.refresh()
        self._safe_update(self)

    def _close_settings(self):
        self._settings_dialog.open = False
        self._safe_update(self._settings_dialog)
