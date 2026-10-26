"""
ui/components/home_widgets/pomodoro.py
--------------------------------------
Pomodoro timer card for the group home page.

The card draws a circular countdown ring with the phase name above the time and
one dot per pomodoro of the current set. Start/Pause is the primary button,
Reset sits next to it as an icon. The loop follows focus -> short break ->
focus ... -> long break after ``cycles`` focus phases; with "auto start" on it
keeps running into the next phase.

The state machine lives in :mod:`ui.components.home_widgets.pomodoro_model`,
the settings dialog in :mod:`ui.components.home_widgets.pomodoro_settings` and
the end signal in :mod:`ui.components.home_widgets.pomodoro_audio`. This module
only wires them to Flet and runs the countdown.

The timer loop is a plain asyncio task on the page's event loop
(``page.run_task``). It wakes every :data:`TICK` seconds and recomputes the
remaining time from a monotonic deadline, so a slow frame does not make the
timer drift. A running timer is *not* persisted - it starts fresh after a
restart.
"""

from __future__ import annotations

import asyncio
import math
from math import pi

import flet as ft
from flet import canvas as cv

from ui.components.home_widgets.base import HomeWidget
from ui.components.home_widgets.pomodoro_audio import PomodoroAudio
from ui.components.home_widgets.pomodoro_model import (
    PHASE_FOCUS,
    PHASE_LABELS,
    PHASE_LONG_BREAK,
    PHASE_SHORT_BREAK,
    PomodoroSession,
    PomodoroSettings,
)
from ui.components.home_widgets.pomodoro_settings import PomodoroSettingsDialog

# Ring geometry in logical pixels and how often the countdown repaints.
RING_SIZE = 176
RING_STROKE = 10
TICK = 0.25

# Muted accents that stay readable in light and dark mode: warm terracotta for
# focus, calm teal for the short break, sage green for the long one.
PHASE_COLORS = {
    PHASE_FOCUS: "#E07A5F",
    PHASE_SHORT_BREAK: "#5FA8A0",
    PHASE_LONG_BREAK: "#6B9E78",
}


def format_seconds(seconds: int) -> str:
    """``MM:SS`` (or ``H:MM:SS`` past an hour) for the big label."""
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def ring_shapes(fraction: float, color: str) -> list[cv.Arc]:
    """Track circle plus progress arc for the countdown ring.

    ``fraction`` is the share still left, so the arc shrinks to nothing while
    the timer runs. The progress arc starts at twelve o'clock and uses round
    caps; the track stays on ``OUTLINE_VARIANT`` so both themes keep it quiet.
    """
    inset = RING_STROKE / 2
    side = RING_SIZE - RING_STROKE
    track_paint = ft.Paint(
        stroke_width=RING_STROKE,
        color=ft.Colors.OUTLINE_VARIANT,
        style=ft.PaintingStyle.STROKE,
        anti_alias=True,
    )
    value_paint = ft.Paint(
        stroke_width=RING_STROKE,
        color=color,
        style=ft.PaintingStyle.STROKE,
        stroke_cap=ft.StrokeCap.ROUND,
        anti_alias=True,
    )
    share = max(0.0, min(1.0, float(fraction)))
    shapes = [
        cv.Arc(
            inset,
            inset,
            side,
            side,
            start_angle=0,
            sweep_angle=2 * pi,
            paint=track_paint,
        )
    ]
    if share > 0:
        # A tiny gap keeps Flutter from collapsing an exact 2*pi arc at 100 %.
        shapes.append(
            cv.Arc(
                inset,
                inset,
                side,
                side,
                start_angle=-pi / 2,
                sweep_angle=(2 * pi - 0.0001) * share,
                paint=value_paint,
            )
        )
    return shapes


@ft.control
class PomodoroWidget(HomeWidget):
    TITLE = "Pomodoro"
    TYPE = "pomodoro"

    def __init__(self, store, module_store=None, on_open_module=None):
        super().__init__(store, module_store, on_open_module)

        # Runtime timer state (not persisted) plus the clock task.
        self._settings = PomodoroSettings()
        self._session = PomodoroSession(self._settings)
        self._running = False
        self._task: asyncio.Task | None = None
        # Bumped by pause/reset so a phase that already ended cannot auto-start
        # on top of a state the user changed in the meantime.
        self._epoch = 0
        self._audio = PomodoroAudio()

        # Settings dialog, built on first open and reused afterwards.
        self._dialog = None

        self._status_text = ft.Text(
            "Ready",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.OUTLINE,
        )
        self._time_text = ft.Text(
            format_seconds(self._session.remaining),
            size=36,
            weight=ft.FontWeight.BOLD,
        )
        self._topic_text = ft.Text(
            "",
            size=11,
            color=ft.Colors.OUTLINE,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            text_align=ft.TextAlign.CENTER,
            width=RING_SIZE - 2 * RING_STROKE - 12,
            visible=False,
        )
        self._ring = cv.Canvas(
            width=RING_SIZE,
            height=RING_SIZE,
            shapes=ring_shapes(1.0, PHASE_COLORS[PHASE_FOCUS]),
        )
        self._ring_stack = ft.Stack(
            width=RING_SIZE,
            height=RING_SIZE,
            alignment=ft.Alignment.CENTER,
            controls=[
                self._ring,
                ft.Column(
                    tight=True,
                    spacing=2,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        self._status_text,
                        self._time_text,
                        self._topic_text,
                    ],
                ),
            ],
        )
        self._dots_row = ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=6,
            controls=[],
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
        """Rebuild the body from the stored options (dropping running state)."""
        self._epoch += 1
        self._stop_task()
        self._running = False
        self._settings = PomodoroSettings.from_options(self._widget_options())
        self._session = PomodoroSession(self._settings)

        self.body.controls.clear()
        self._rebuild_dots()
        self.body.controls.append(
            ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[self._ring_stack])
        )
        self.body.controls.append(
            ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[self._dots_row])
        )
        self.body.controls.append(
            ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=4,
                controls=[self._start_button, self._reset_button],
            )
        )
        self._paint(push=False)

    def _widget_options(self) -> dict:
        return self._store.get_widget_options(self._group, self.TYPE)

    def _rebuild_dots(self):
        self._dots_row.controls = [
            ft.Container(width=7, height=7, border_radius=4)
            for _ in range(self._settings.cycles)
        ]

    def _paint(self, push: bool = True):
        """Write the current session into ring, texts, dots and buttons."""
        session = self._session
        accent = PHASE_COLORS.get(session.phase, PHASE_COLORS[PHASE_FOCUS])

        self._time_text.value = format_seconds(session.remaining)
        self._status_text.value = session.status(self._running)
        self._status_text.color = accent if self._running else ft.Colors.OUTLINE
        self._ring.shapes = ring_shapes(session.progress(), accent)

        topic = self._settings.topic
        self._topic_text.value = topic
        self._topic_text.visible = bool(topic)

        dots = session.dots()
        for dot, done in zip(self._dots_row.controls, dots):
            dot.bgcolor = accent if done else ft.Colors.with_opacity(0.22, accent)

        self._start_button.content = "Pause" if self._running else "Start"
        self._start_button.icon = (
            ft.Icons.PAUSE if self._running else ft.Icons.PLAY_ARROW
        )

        if not push:
            return
        for control in (
            self._status_text,
            self._time_text,
            self._topic_text,
            self._ring,
            self._dots_row,
            self._start_button,
        ):
            self._safe_update(control)

    #  timer

    def _toggle(self, e=None):
        if self._running:
            self._pause()
        else:
            self._start()

    def _start(self):
        if self._running:
            return
        if self._session.remaining <= 0:
            self._session.remaining = self._session.duration()
        page = self._page()
        if page is None:
            return
        self._running = True
        self._paint()
        self._task = page.run_task(self._run)

    def _pause(self):
        self._epoch += 1
        self._stop_task()
        self._running = False
        self._paint()

    def _reset(self, e=None):
        self._epoch += 1
        self._stop_task()
        self._running = False
        self._session.reset()
        self._paint()

    def _stop_task(self):
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()

    async def _run(self):
        """Count down to zero, then hand over to the next phase."""
        epoch = self._epoch
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._session.remaining
        try:
            while self._running:
                await asyncio.sleep(TICK)
                if not self._running:
                    return
                self._session.remaining = max(0, math.ceil(deadline - loop.time()))
                self._paint()
                if self._session.remaining > 0:
                    continue
                self._running = False
                self._task = None
                await self._phase_finished(epoch)
                return
        except asyncio.CancelledError:
            # Pause / reset cancelled us; state already updated by the caller.
            raise

    async def _phase_finished(self, epoch: int):
        """Play the signal, advance the loop and optionally auto-start it."""
        finished = self._session.phase
        self._session.finish_phase()
        self._paint()

        page = self._page()
        if page is not None:
            next_label = PHASE_LABELS[self._session.phase]
            page.show_dialog(
                ft.SnackBar(
                    content=ft.Text(f"{PHASE_LABELS[finished]} vorbei – {next_label}.")
                )
            )
        await self._audio.play(page, self._settings.sound)
        if (
            self._settings.auto_start
            and self._epoch == epoch
            and self._page() is not None
        ):
            self._start()

    #  settings

    def open_settings(self, e=None):
        page = self._page()
        if page is None:
            return
        if self._dialog is None:
            self._dialog = PomodoroSettingsDialog(
                on_save=self._apply_settings,
                on_close=self._close_dialog,
            )
            page.overlay.append(self._dialog)
        self._dialog.load(self._settings)
        self._dialog.open = True
        page.update()

    def _apply_settings(self, settings: PomodoroSettings):
        """Store every option, then restart the card from the new settings."""
        for key, value in settings.to_options().items():
            self.set_option(key, value)
        self.refresh()
        self._safe_update(self)

    def _close_dialog(self, dialog):
        # Hide only: a dialog pulled out of the overlay upsets Flutter.
        dialog.open = False
        page = self._page()
        if page is not None:
            page.update()
