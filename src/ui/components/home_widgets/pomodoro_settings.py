"""
ui/components/home_widgets/pomodoro_settings.py
-----------------------------------------------
Settings dialog for the pomodoro card.

Kept out of the widget module so the card only deals with its state machine
and drawing. The dialog owns its controls, validates the minute fields and
hands a complete :class:`PomodoroSettings` back through ``on_save``; the card
then stores the options and restarts.

Preset chips only fill the focus field - the field stays editable, so any
value between 1 and 180 minutes is allowed. The sound switch is the mute
shortcut: off means ``sound = "mute"``, and the dropdown keeps the last real
choice for when it is switched back on.
"""

from __future__ import annotations

import flet as ft

from ui.components.home_widgets.pomodoro_model import (
    MAX_CYCLES,
    MAX_MINUTES,
    MIN_CYCLES,
    MIN_MINUTES,
    SOUND_BEEP,
    SOUND_GONG,
    SOUND_LABELS,
    SOUND_MUTE,
    TOPIC_MAX_LENGTH,
    PomodoroSettings,
    normalize_cycles,
    normalize_minutes,
    normalize_sound,
    normalize_topic,
)

# Quick picks in minutes; the field next to them stays editable.
PRESETS = (15, 25, 45, 60)


class PomodoroSettingsDialog(ft.AlertDialog):
    """One reusable dialog: :meth:`load` fills it, Save emits new settings."""

    def __init__(self, on_save, on_close=None):
        self._on_save = on_save
        self._on_close = on_close
        # Last non-mute choice, restored when the sound switch comes back on.
        self._last_sound = SOUND_GONG

        self._focus_field = ft.TextField(
            label="Fokuszeit (Minuten)",
            dense=True,
            width=132,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._preset_chips = [
            ft.Chip(
                label=ft.Text(f"{minutes}m"),
                show_checkmark=False,
                on_click=lambda e, value=minutes: self._pick_preset(value),
            )
            for minutes in PRESETS
        ]
        self._short_field = ft.TextField(
            label="Kurze Pause (Minuten)",
            dense=True,
            expand=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text="5",
        )
        self._long_field = ft.TextField(
            label="Lange Pause (Minuten)",
            dense=True,
            expand=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text="15",
        )
        self._cycles_field = ft.TextField(
            label="Pomodoros bis zur langen Pause",
            dense=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            hint_text="4",
        )
        self._topic_field = ft.TextField(
            label="Aktuelles Thema / Fach",
            dense=True,
            hint_text="z. B. Mathe Klausur",
            max_length=TOPIC_MAX_LENGTH,
        )
        self._auto_switch = ft.Switch(
            label="Nächste Phase automatisch starten",
            value=True,
        )
        self._sound_switch = ft.Switch(
            label="Ton am Ende",
            value=True,
            on_change=self._toggle_sound,
        )
        self._sound_dropdown = ft.Dropdown(
            label="Klang",
            dense=True,
            expand=True,
            options=[
                ft.DropdownOption(key=SOUND_GONG, text=SOUND_LABELS[SOUND_GONG]),
                ft.DropdownOption(key=SOUND_BEEP, text=SOUND_LABELS[SOUND_BEEP]),
            ],
        )
        self._status = ft.Text("", size=12, color=ft.Colors.ERROR)

        super().__init__(
            modal=True,
            title=ft.Text("Pomodoro"),
            content=ft.Container(
                width=380,
                content=ft.Column(
                    tight=True,
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                    height=360,
                    controls=[
                        self._section("Fokus & Pausen"),
                        ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                self._focus_field,
                                ft.Row(
                                    wrap=True,
                                    spacing=6,
                                    run_spacing=6,
                                    expand=True,
                                    controls=self._preset_chips,
                                ),
                            ],
                        ),
                        ft.Row(
                            spacing=10,
                            controls=[self._short_field, self._long_field],
                        ),
                        self._cycles_field,
                        ft.Divider(height=1),
                        self._section("Aufgabe"),
                        self._topic_field,
                        ft.Divider(height=1),
                        self._section("Ton"),
                        ft.Row(
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[self._sound_switch, self._sound_dropdown],
                        ),
                        self._auto_switch,
                        self._status,
                        ft.Text(
                            f"Fokus und Pausen: {MIN_MINUTES}–{MAX_MINUTES} Minuten, "
                            f"{MIN_CYCLES}–{MAX_CYCLES} Pomodoros pro Satz.",
                            size=11,
                            color=ft.Colors.OUTLINE,
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton("Abbrechen", on_click=lambda e: self.close()),
                ft.FilledButton("Speichern", on_click=self._save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    #  loading

    def load(self, settings: PomodoroSettings) -> None:
        """Fill the controls from *settings* (the dialog is reused)."""
        self._focus_field.value = str(settings.focus_minutes)
        self._short_field.value = str(settings.short_break_minutes)
        self._long_field.value = str(settings.long_break_minutes)
        self._cycles_field.value = str(settings.cycles)
        self._topic_field.value = settings.topic
        self._auto_switch.value = settings.auto_start

        muted = settings.sound == SOUND_MUTE
        if not muted:
            self._last_sound = settings.sound
        self._sound_switch.value = not muted
        self._sound_dropdown.value = self._last_sound
        self._sound_dropdown.disabled = muted
        self._status.value = ""
        self._sync_presets(settings.focus_minutes)

    def _section(self, text: str) -> ft.Text:
        return ft.Text(
            text,
            size=12,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )

    def _pick_preset(self, minutes: int) -> None:
        self._focus_field.value = str(minutes)
        self._sync_presets(minutes)
        self._safe_update(self._focus_field)
        for chip in self._preset_chips:
            self._safe_update(chip)

    def _sync_presets(self, value) -> None:
        current = str(value).strip()
        for minutes, chip in zip(PRESETS, self._preset_chips):
            chip.selected = current == str(minutes)

    def _toggle_sound(self, e=None) -> None:
        enabled = bool(self._sound_switch.value)
        self._sound_dropdown.disabled = not enabled
        if enabled and self._sound_dropdown.value:
            self._last_sound = self._sound_dropdown.value
        self._safe_update(self._sound_dropdown)

    #  saving

    def _collect(self) -> tuple[PomodoroSettings | None, str | None]:
        """Validate the fields into ``(settings, None)`` or ``(None, message)``."""
        focus = self._minutes(self._focus_field, "Fokuszeit")
        if isinstance(focus, str):
            return None, focus
        short = self._minutes(self._short_field, "Kurze Pause")
        if isinstance(short, str):
            return None, short
        long = self._minutes(self._long_field, "Lange Pause")
        if isinstance(long, str):
            return None, long
        cycles = self._integer(self._cycles_field, "Pomodoros", MIN_CYCLES, MAX_CYCLES)
        if isinstance(cycles, str):
            return None, cycles

        sound = self._sound_dropdown.value if self._sound_switch.value else SOUND_MUTE
        return (
            PomodoroSettings(
                focus_minutes=normalize_minutes(focus),
                short_break_minutes=normalize_minutes(short),
                long_break_minutes=normalize_minutes(long),
                cycles=normalize_cycles(cycles),
                topic=normalize_topic(self._topic_field.value),
                auto_start=bool(self._auto_switch.value),
                sound=normalize_sound(sound),
            ),
            None,
        )

    @staticmethod
    def _integer(field, name: str, low: int, high: int) -> int | str:
        """Parse *field*; returns the number or a German error message."""
        text = (field.value or "").strip()
        try:
            value = int(text)
        except ValueError:
            return f"{name}: bitte eine ganze Zahl zwischen {low} und {high} eingeben."
        if not low <= value <= high:
            return f"{name}: bitte eine Zahl zwischen {low} und {high} eingeben."
        return value

    def _minutes(self, field, name: str) -> int | str:
        return self._integer(field, name, MIN_MINUTES, MAX_MINUTES)

    def _save(self, e=None) -> None:
        settings, error = self._collect()
        if error:
            self._status.value = error
            self._safe_update(self._status)
            return
        self._status.value = ""
        self.close()
        self._on_save(settings)

    #  helpers

    def _safe_update(self, control) -> None:
        try:
            control.update()
        except RuntimeError:
            pass

    def close(self):
        self.open = False
        self._safe_update(self)
        if self._on_close:
            self._on_close(self)
