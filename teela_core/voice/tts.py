"""
Text-to-Speech Pipeline

Output: audio bytes sent to speaker.
Supports:
    - pyttsx3 (offline, robotic but instant)
    - Coqui TTS (offline, higher quality)
    - Edge TTS (online, very natural)
    - Piper TTS (offline, fast)

Teela's voice should be:
    - Slightly higher pitch than average
    - Warm but not overly cheerful
    - Consistent across sessions (same TTS model)
"""

import io
import subprocess
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class SpeechParams:
    wpm: int = 140
    pitch: int = 0  # Hz shift
    volume_db: int = -10


class TTSEngine:
    """TTS with prosodic modulation."""

    def __init__(self, engine: str = "edge-tts"):
        self.engine = engine
        self._last_speech_time = 0.0

    def speak(self, text: str, params: Optional[SpeechParams] = None) -> Optional[bytes]:
        """Convert text to audio bytes. Returns None if engine unavailable."""
        params = params or SpeechParams()
        self._last_speech_time = time.time()

        if self.engine == "edge-tts":
            return self._edge_tts(text, params)
        elif self.engine == "piper":
            return self._piper_tts(text, params)
        elif self.engine == "pyttsx3":
            return self._pyttsx3_tts(text, params)
        return None

    def _edge_tts(self, text: str, params: SpeechParams) -> Optional[bytes]:
        """Use Microsoft Edge TTS cloud service. Requires internet."""
        try:
            import edge_tts  # type: ignore[import]
            communicate = edge_tts.Communicate(text, voice="en-US-AriaNeural")
            output = io.BytesIO()
            for chunk in communicate.stream_sync():
                if chunk["type"] == "audio":
                    output.write(chunk["data"])
            return output.getvalue()
        except Exception:
            return None

    def _piper_tts(self, text: str, params: SpeechParams) -> Optional[bytes]:
        """Piper: fast, decent quality, fully offline."""
        try:
            result = subprocess.run(
                ["piper", "--model", "en_US-lessac-medium.onnx", "--output_file", "-"],
                input=text.encode(),
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        return None

    def _pyttsx3_tts(self, text: str, params: SpeechParams) -> Optional[bytes]:
        """pyttsx3: no external dependencies, robotic but reliable."""
        try:
            import pyttsx3  # type: ignore[import]
            engine = pyttsx3.init()
            engine.setProperty("rate", params.wpm)
            engine.setProperty("volume", 0.5 + params.volume_db / 60)
            # pyttsx3 doesn't return bytes easily; this is a structural stub
            # In practice you'd save to a tempfile and read back
            return None
        except Exception:
            return None

    def get_idle_sounds(self, emotion: dict) -> Optional[str]:
        """Occasional ambient vocalizations: hmm, ah, etc. when thoughtful."""
        if emotion.get("arousal", 0) < 0.2 and emotion.get("pleasure", 0) > -0.2:
            return random.choice(["hmm.", "aha.", "oh.", ""])
        return None
