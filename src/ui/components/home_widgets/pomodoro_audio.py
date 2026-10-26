"""
ui/components/home_widgets/pomodoro_audio.py
--------------------------------------------
End-of-phase sound for the pomodoro card.

Flet 0.84 no longer ships ``ft.Audio``; playback comes from the separate
``flet-audio`` package (``import flet_audio``). That package is an optional
runtime dependency: if it is missing, or the platform has no working audio
backend, the timer still runs and simply stays silent. One log line explains
why.

The players are Flet services, so they live in ``page.services`` and are kept
alive between phases. They are created on first use - opening a group page
must not pay for audio the user never enables.
"""

from __future__ import annotations

import logging

from ui.components.home_widgets.pomodoro_model import SOUND_FILES, SOUND_MUTE

log = logging.getLogger(__name__)

try:  # optional: a source checkout without the extension keeps working
    import flet_audio as fta
except Exception:  # ImportError, or a broken native dependency
    fta = None
    log.info("flet-audio not available; pomodoro sounds are disabled")


class PomodoroAudio:
    """Lazily built, reused audio players keyed by sound name."""

    def __init__(self):
        self._players: dict = {}

    async def play(self, page, sound: str) -> None:
        """Play *sound* on *page*; silently do nothing for mute or no backend."""
        if sound == SOUND_MUTE or page is None or fta is None:
            return
        if sound not in SOUND_FILES:
            return
        player = self._player(page, sound)
        if player is None:
            return
        try:
            await player.play()
        except Exception:
            # A missing GStreamer plugin or busy device must not kill the timer.
            log.warning("could not play pomodoro sound %r", sound, exc_info=True)

    def _player(self, page, sound: str):
        player = self._players.get(sound)
        if player is not None:
            return player
        try:
            player = fta.Audio(
                src=SOUND_FILES[sound],
                volume=0.7,
                release_mode=fta.ReleaseMode.STOP,
            )
            # Flet 0.84 pages hold services in a registry, not in a plain list.
            # register_service also pushes the update to the client.
            page.services.register_service(player)
        except Exception:
            log.warning("could not create audio player for %r", sound, exc_info=True)
            return None
        self._players[sound] = player
        return player
