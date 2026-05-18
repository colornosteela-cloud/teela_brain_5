"""
Wake Word Detection

Teela listens for her name ("Teela") or a custom wake phrase.
When detected, transitions from low-power idle to active listening.

Implementation options:
    - Porcupine by Picovoice (lightweight, offline)
    - OpenWakeWord (open source, ONNX)
    - Whisper live with sliding window (slower but free)
"""

import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np


@dataclass
class WakeEvent:
    keyword: str
    confidence: float
    timestamp: float
    direction_of_arrival: Optional[float] = None  # radians, if microphone array


class WakeWordDetector:
    """Simple wake word detector. Replace with Porcupine for production."""

    WAKE_PHRASES = ["teela", "hey teela", "okay teela"]

    def __init__(self, sensitivity: float = 0.7):
        self.sensitivity = sensitivity
        self._porcupine = None  # lazy init
        self._last_detection_time = 0.0
        self._cooldown_s = 2.0  # don't re-trigger immediately

    def _load_porcupine(self) -> bool:
        """Try to load Porcupine wake word engine."""
        try:
            import pvporcupine  # type: ignore[import]
            # Requires access_key and model file
            # self._porcupine = pvporcupine.create(keywords=["teela"])
            return False  # stub until configured
        except ImportError:
            return False

    def detect(self, audio_chunk: np.ndarray, timestamp: float) -> Optional[WakeEvent]:
        """Check if wake word is present in audio chunk."""
        if timestamp - self._last_detection_time < self._cooldown_s:
            return None

        # TODO: integrate actual wake word engine
        # For now, return None (always-on listening or triggered by button)
        
        # Energy-based placeholder: loud sound = potential wake
        energy = np.sqrt(np.mean(audio_chunk**2))
        if energy > 0.3:  # very loud
            self._last_detection_time = timestamp
            return WakeEvent(
                keyword="teela",
                confidence=0.5,
                timestamp=timestamp,
            )

        return None

    def is_in_cooldown(self, now: float) -> bool:
        return (now - self._last_detection_time) < self._cooldown_s
