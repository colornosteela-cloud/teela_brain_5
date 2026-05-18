"""Real audio output for Jetson.

Uses simpleaudio (portable) or aplay (linux) to play TTS audio.
Also supports edge-tts for cloud-based speech.

For development without audio, prints transcript with [SPEAK] tag.
"""

import base64
import io
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Literal, Optional


class SpeakerTTS:
    """Play audio on Jetson speaker or stdout fallback.

    Modes:
        stdout  → just print [SPEAK] transcript (for headless debugging)
        aplay   → linux ALSA aplay command
        tts     → generate audio via edge-tts / openai-tts then play
    """

    def __init__(
        self,
        mode: Literal["stdout", "aplay", "edge_tts"] = "stdout",
        edge_tts_voice: str = "en-US-AriaNeural",
        output_device: Optional[str] = None,
    ):
        self.mode = mode
        self.edge_tts_voice = edge_tts_voice
        self.output_device = output_device
        self._aplay_available = self._check_aplay()

        if mode == "aplay" and not self._aplay_available:
            print("[SpeakerTTS] aplay not found; falling back to stdout")
            self.mode = "stdout"

    @staticmethod
    def _check_aplay() -> bool:
        try:
            subprocess.run(["aplay", "--version"], capture_output=True, check=True)
            return True
        except FileNotFoundError:
            return False

    def speak(self, text: str, prosody: Optional[dict] = None) -> None:
        """Speak text aloud or print it."""
        if not text or not text.strip():
            return

        if self.mode == "stdout":
            print(f"\n[SPEAK 🗣️] {text.strip()}\n")
            return

        if self.mode == "aplay":
            # If we already have a wav / mp3, play it. Otherwise stdout.
            # Hook for future TTS integration
            print(f"\n[SPEAK 🗣️ (aplay)] {text.strip()}\n")
            return

        if self.mode == "edge_tts":
            self._speak_edge_tts(text)
            return

    def _speak_edge_tts(self, text: str) -> None:
        """Generate audio via edge-tts and play with aplay."""
        try:
            import edge_tts
            import asyncio

            async def _gen():
                communicate = edge_tts.Communicate(text, self.edge_tts_voice)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                    tmp_path = f.name
                await communicate.save(tmp_path)
                if self._aplay_available:
                    subprocess.run(
                        ["aplay", "-D", self.output_device or "default", tmp_path]
                        if self.output_device
                        else ["aplay", tmp_path],
                        capture_output=True,
                    )
                os.unlink(tmp_path)

            asyncio.run(_gen())
        except ImportError:
            print("[SpeakerTTS] edge-tts not installed. pip install edge-tts")
            print(f"\n[SPEAK fallback] {text.strip()}\n")
        except Exception as e:
            print(f"[SpeakerTTS] edge-tts error: {e}")

    def play_beep(self, freq: int = 880, duration_ms: int = 150) -> None:
        """Simple feedback beep. Useful for wake word detected, etc."""
        if self.mode == "stdout":
            print("[BEEP 🔊]")
            return
        if not self._aplay_available:
            return
        # Generate a simple sine wav via sox or python
        try:
            from scipy.io import wavfile
            import numpy as np
            sr = 22050
            t = np.linspace(0, duration_ms / 1000, int(sr * duration_ms / 1000), False)
            tone = np.sin(freq * 2 * np.pi * t) * 0.3
            tone = (tone * 32767).astype(np.int16)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wavfile.write(f.name, sr, tone)
                tmp = f.name
            subprocess.run(["aplay", tmp], capture_output=True)
            os.unlink(tmp)
        except Exception:
            pass
