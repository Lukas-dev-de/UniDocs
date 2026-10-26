"""
ui/components/home_widgets/pomodoro_model.py
--------------------------------------------
Settings and phase logic for the pomodoro card.

Everything here is plain Python: no Flet controls, no storage, no event loop.
The card (:mod:`ui.components.home_widgets.pomodoro`) owns the asyncio loop and
the widgets; this module only answers "which phase comes next" and "what does
the stored option mean". That keeps the state machine testable without a page.

Stored options (all under the ``pomodoro`` key in the group's ``.home.json``):

    focus_minutes, short_break_minutes, long_break_minutes, cycles,
    topic, auto_start, sound

Files written by older builds carried one ``minutes`` total and a ``muted``
flag. :meth:`PomodoroSettings.from_options` still reads both as a fallback, so
an existing card keeps its length and mute choice after the upgrade.
"""

from __future__ import annotations

from dataclasses import dataclass

# Phases of the loop. Focus -> short break -> focus ... -> long break -> focus.
PHASE_FOCUS = "focus"
PHASE_SHORT_BREAK = "short_break"
PHASE_LONG_BREAK = "long_break"

PHASE_LABELS = {
    PHASE_FOCUS: "Focus Time",
    PHASE_SHORT_BREAK: "Short Break",
    PHASE_LONG_BREAK: "Long Break",
}

# End-of-phase sounds. "mute" is the switch-off state, not a file.
SOUND_GONG = "gong"
SOUND_BEEP = "beep"
SOUND_MUTE = "mute"
SOUNDS = (SOUND_GONG, SOUND_BEEP, SOUND_MUTE)
SOUND_LABELS = {
    SOUND_GONG: "Soft Gong",
    SOUND_BEEP: "Digital Beep",
    SOUND_MUTE: "Mute",
}
# Paths relative to the Flet assets directory (src/assets).
SOUND_FILES = {
    SOUND_GONG: "sounds/soft_gong.wav",
    SOUND_BEEP: "sounds/digital_beep.wav",
}

DEFAULT_FOCUS_MINUTES = 25
DEFAULT_SHORT_BREAK_MINUTES = 5
DEFAULT_LONG_BREAK_MINUTES = 15
DEFAULT_CYCLES = 4
DEFAULT_TOPIC = ""
DEFAULT_AUTO_START = True
DEFAULT_SOUND = SOUND_GONG

MIN_MINUTES = 1
MAX_MINUTES = 180
MIN_CYCLES = 1
MAX_CYCLES = 12
TOPIC_MAX_LENGTH = 60


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value, default: bool) -> bool:
    """Hand-edited JSON can leave strings behind; treat the usual no-words as off."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off", "nein")
    return bool(value)


def normalize_minutes(value, default: int = DEFAULT_FOCUS_MINUTES) -> int:
    """Clamp a stored length onto 1 … 180 minutes; broken input -> *default*."""
    minutes = _as_int(value, default)
    return max(MIN_MINUTES, min(MAX_MINUTES, minutes))


def normalize_cycles(value) -> int:
    """Clamp the pomodoros-before-long-break count onto 1 … 12."""
    cycles = _as_int(value, DEFAULT_CYCLES)
    return max(MIN_CYCLES, min(MAX_CYCLES, cycles))


def normalize_sound(value) -> str:
    """Map a stored sound choice onto :data:`SOUNDS`, else the gong."""
    if isinstance(value, str):
        sound = value.strip().lower()
        if sound in SOUNDS:
            return sound
    return DEFAULT_SOUND


def normalize_topic(value) -> str:
    """Collapse whitespace and cap the topic so it fits under the timer."""
    if not isinstance(value, str):
        return DEFAULT_TOPIC
    return " ".join(value.split())[:TOPIC_MAX_LENGTH]


@dataclass(frozen=True)
class PomodoroSettings:
    """User-facing knobs, independent of where they are stored."""

    focus_minutes: int = DEFAULT_FOCUS_MINUTES
    short_break_minutes: int = DEFAULT_SHORT_BREAK_MINUTES
    long_break_minutes: int = DEFAULT_LONG_BREAK_MINUTES
    cycles: int = DEFAULT_CYCLES
    topic: str = DEFAULT_TOPIC
    auto_start: bool = DEFAULT_AUTO_START
    sound: str = DEFAULT_SOUND

    @classmethod
    def from_options(cls, options: dict | None) -> "PomodoroSettings":
        """Build settings from a widget-options dict, migrating old keys."""
        options = options or {}
        focus = options.get("focus_minutes")
        if focus is None:
            focus = options.get("minutes", DEFAULT_FOCUS_MINUTES)
        sound = options.get("sound")
        if sound is None:
            sound = SOUND_MUTE if options.get("muted") else DEFAULT_SOUND
        return cls(
            focus_minutes=normalize_minutes(focus, DEFAULT_FOCUS_MINUTES),
            short_break_minutes=normalize_minutes(
                options.get("short_break_minutes"), DEFAULT_SHORT_BREAK_MINUTES
            ),
            long_break_minutes=normalize_minutes(
                options.get("long_break_minutes"), DEFAULT_LONG_BREAK_MINUTES
            ),
            cycles=normalize_cycles(options.get("cycles")),
            topic=normalize_topic(options.get("topic")),
            auto_start=_as_bool(options.get("auto_start"), DEFAULT_AUTO_START),
            sound=normalize_sound(sound),
        )

    def to_options(self) -> dict:
        """The dict written back into ``.home.json`` (one key per setting)."""
        return {
            "focus_minutes": self.focus_minutes,
            "short_break_minutes": self.short_break_minutes,
            "long_break_minutes": self.long_break_minutes,
            "cycles": self.cycles,
            "topic": self.topic,
            "auto_start": self.auto_start,
            "sound": self.sound,
        }


@dataclass
class PomodoroSession:
    """Where the loop currently is: phase, completed pomodoros, seconds left.

    ``remaining`` counts down; :meth:`finish_phase` advances to the next phase
    and refills it. The widget replaces :attr:`settings` and calls
    :meth:`reset` when the dialog saves.
    """

    settings: PomodoroSettings
    phase: str = PHASE_FOCUS
    completed: int = 0
    remaining: int = 0

    def __post_init__(self):
        if self.phase not in PHASE_LABELS:
            self.phase = PHASE_FOCUS
        self.completed = max(0, min(self.settings.cycles, self.completed))
        if self.remaining <= 0:
            self.remaining = self.duration()

    #  phases

    def duration(self, phase: str | None = None) -> int:
        """Length of *phase* (default: the current one) in seconds."""
        phase = phase or self.phase
        minutes = {
            PHASE_FOCUS: self.settings.focus_minutes,
            PHASE_SHORT_BREAK: self.settings.short_break_minutes,
            PHASE_LONG_BREAK: self.settings.long_break_minutes,
        }.get(phase, self.settings.focus_minutes)
        return minutes * 60

    def progress(self) -> float:
        """Share of the phase still left, ``1.0`` … ``0.0`` for the ring."""
        total = self.duration()
        if total <= 0:
            return 0.0
        return max(0.0, min(1.0, self.remaining / total))

    def reset(self) -> None:
        """Back to the start of a fresh focus phase and a fresh cycle."""
        self.phase = PHASE_FOCUS
        self.completed = 0
        self.remaining = self.duration()

    def finish_phase(self) -> str:
        """Advance after the countdown hit zero; returns the new phase.

        A finished focus counts as one pomodoro. The long break starts once
        that count reaches ``cycles``; it then clears the count for the next
        set. Breaks always lead back to focus.
        """
        if self.phase == PHASE_FOCUS:
            self.completed += 1
            self.phase = (
                PHASE_LONG_BREAK
                if self.completed >= self.settings.cycles
                else PHASE_SHORT_BREAK
            )
        elif self.phase == PHASE_SHORT_BREAK:
            self.phase = PHASE_FOCUS
        else:  # long break done -> new set
            self.completed = 0
            self.phase = PHASE_FOCUS
        self.remaining = self.duration()
        return self.phase

    #  labels

    def status(self, running: bool) -> str:
        """Text above the timer: the phase while running, else Ready/Paused.

        A break that waits for "Start" (auto start off) keeps its phase name -
        otherwise the card would say "Ready" and hide where the loop stands.
        """
        if running:
            return PHASE_LABELS[self.phase]
        if self.remaining < self.duration():
            return "Paused"
        if self.phase != PHASE_FOCUS:
            return PHASE_LABELS[self.phase]
        return "Ready"

    def dots(self) -> list[bool]:
        """One entry per pomodoro in the set; ``True`` = already done."""
        return [index < self.completed for index in range(self.settings.cycles)]
