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
        """Generate audio via edge-tts and play with GStreamer (Jetson native)."""
        try:
            import edge_tts
            import asyncio
            import subprocess, os, tempfile

            async def _gen():
                communicate = edge_tts.Communicate(text, self.edge_tts_voice)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                    tmp_path = f.name
                await communicate.save(tmp_path)
                # GStreamer: decode MP3 and play via ALSA
                cmd = [
                    "gst-launch-1.0", "playbin",
                    f"uri=file://{tmp_path}"
                ]
                # If specific ALSA device requested, override audio-sink
                if self.output_device:
                    cmd.append(f"audio-sink=alsasink device={self.output_device}")
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                if result.returncode != 0:
                    print(f"[SpeakerTTS] GStreamer error: {result.stderr.decode()[:200]}")
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
            import struct, math, tempfile, os
            sr = 22050
            t = int(sr * duration_ms / 1000)
            samples = []
            for i in range(t):
                v = int(math.sin(freq * 2 * math.pi * i / sr) * 0.3 * 32767)
                samples.append(struct.pack('<h', v))
            data = b''.join(samples)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                # WAV header
                f.write(b'RIFF')
                f.write(struct.pack('<I', 36 + len(data)))
                f.write(b'WAVEfmt ')
                f.write(struct.pack('<IHHIIHH', 16, 1, 1, sr, sr*2, 2, 16))
                f.write(b'data')
                f.write(struct.pack('<I', len(data)))
                f.write(data)
                tmp = f.name
            subprocess.run(["aplay", "-D", self.output_device or "default", tmp], capture_output=True)
            os.unlink(tmp)
        except Exception:
            pass
