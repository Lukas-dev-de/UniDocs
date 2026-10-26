"""Tests for the pomodoro state machine and option migration (no Flet needed)."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ui.components.home_widgets.pomodoro_model import (  # noqa: E402
    PHASE_FOCUS,
    PHASE_LONG_BREAK,
    PHASE_SHORT_BREAK,
    SOUND_BEEP,
    SOUND_MUTE,
    PomodoroSession,
    PomodoroSettings,
    normalize_cycles,
    normalize_minutes,
    normalize_sound,
    normalize_topic,
)


def _settings(**overrides) -> PomodoroSettings:
    values = {"focus_minutes": 25, "short_break_minutes": 5, "long_break_minutes": 15}
    values.update(overrides)
    return PomodoroSettings(**values)


def test_empty_options_give_defaults():
    settings = PomodoroSettings.from_options(None)
    assert settings.focus_minutes == 25
    assert settings.short_break_minutes == 5
    assert settings.long_break_minutes == 15
    assert settings.cycles == 4
    assert settings.auto_start is True
    assert settings.sound != SOUND_MUTE


def test_old_minutes_and_muted_are_migrated():
    settings = PomodoroSettings.from_options({"minutes": 45, "muted": True})
    assert settings.focus_minutes == 45
    assert settings.sound == SOUND_MUTE


def test_new_keys_win_over_old_ones():
    settings = PomodoroSettings.from_options(
        {"minutes": 45, "focus_minutes": 15, "muted": True, "sound": SOUND_BEEP}
    )
    assert settings.focus_minutes == 15
    assert settings.sound == SOUND_BEEP


def test_normalizers_clamp_broken_values():
    assert normalize_minutes("abc") == 25
    assert normalize_minutes(0) == 1
    assert normalize_minutes(999) == 180
    assert normalize_cycles(0) == 1
    assert normalize_cycles(99) == 12
    assert normalize_sound("nope") == "gong"
    assert normalize_topic("  Mathe   Klausur ") == "Mathe Klausur"


def test_durations_follow_the_phase():
    session = PomodoroSession(_settings())
    assert session.remaining == 25 * 60
    session.finish_phase()
    assert session.phase == PHASE_SHORT_BREAK
    assert session.remaining == 5 * 60
    session.finish_phase()
    assert session.phase == PHASE_FOCUS
    assert session.remaining == 25 * 60


def test_long_break_after_the_configured_cycle_count():
    session = PomodoroSession(_settings(cycles=2))
    assert session.finish_phase() == PHASE_SHORT_BREAK
    assert session.finish_phase() == PHASE_FOCUS
    assert session.finish_phase() == PHASE_LONG_BREAK
    assert session.remaining == 15 * 60
    assert session.dots() == [True, True]
    # After the long break a fresh set starts.
    assert session.finish_phase() == PHASE_FOCUS
    assert session.completed == 0


def test_reset_returns_to_a_fresh_focus_phase():
    session = PomodoroSession(_settings())
    session.remaining = 12
    session.completed = 2
    session.phase = PHASE_LONG_BREAK
    session.reset()
    assert session.phase == PHASE_FOCUS
    assert session.completed == 0
    assert session.remaining == 25 * 60


def test_status_moves_between_ready_paused_and_phase():
    session = PomodoroSession(_settings())
    assert session.status(running=False) == "Ready"
    session.remaining -= 1
    assert session.status(running=False) == "Paused"
    assert session.status(running=True) == "Focus Time"
    # A waiting break keeps its name instead of turning into "Ready".
    session.finish_phase()
    assert session.status(running=False) == "Short Break"


def test_progress_is_clamped():
    session = PomodoroSession(_settings())
    assert session.progress() == 1.0
    session.remaining = 0
    assert session.progress() == 0.0


def test_options_roundtrip():
    settings = _settings(
        cycles=3,
        topic="Mathe",
        auto_start=False,
        sound=SOUND_BEEP,
    )
    assert PomodoroSettings.from_options(settings.to_options()) == settings
