"""Deterministic emergency stop phrase matching."""

from __future__ import annotations

import re
import unicodedata


class StopPhraseDetector:
    """Match only an explicit, whole push-to-talk utterance.

    Matching is deliberately independent of inference, skills, planning, and
    external content. TTS feedback is never eligible.
    """

    _PHRASES = frozenset({"thoth stop", "stop thoth"})

    def matches(
        self,
        text: str,
        *,
        push_to_talk_active: bool,
        tts_playing: bool,
    ) -> bool:
        if not push_to_talk_active or tts_playing:
            return False
        normalized = unicodedata.normalize("NFKC", text).casefold()
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
        return normalized in self._PHRASES
