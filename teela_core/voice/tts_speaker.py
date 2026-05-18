"""Teela's expressive voice — real audio output with emotional TTS.

Supports:
  - edge_tts with pitch/rate/volume control
  - SSML emotion styles (cheerful, excited, sad, friendly, whispering, etc.)
  - stdout fallback for headless testing

Usage:
    speaker = SpeakerTTS(mode="edge_tts", edge_tts_voice="en-US-JennyNeural")
    speaker.speak("I am so happy to see you!", emotion="excited")
    speaker.speak("I feel a little lonely...", emotion="sad")
"""

import asyncio
import os
import re
import struct
import subprocess
import tempfile
from typing import Literal, Optional, Dict

# ── Emotion → SSML mapping (Microsoft mstts:express-as styles) ─────────────
# Style availability depends on voice; most work with JennyNeural/Neural voices
EMOTION_SSML: Dict[str, str] = {
    "happy":      "cheerful",
    "cheerful":   "cheerful",
    "excited":    "excited",
    "friendly":   "friendly",
    "neutral":    "default",
    "calm":       "default",
    "sad":        "sad",
    "depressed":  "sad",
    "angry":      "angry",
    "whispering": "whispering",
    "whisper":    "whispering",
    "terrified":  "terrified",
    "apologetic": "apologetic",
    "empathetic": "empathetic",
}


class SpeakerTTS:
    """Play audio on Jetson speaker with emotion and prosody control.

    Modes:
        stdout   → print transcript with 💬 emoji
        aplay    → raw ALSA playback (for pre-generated wavs)
        edge_tts → cloud TTS with pitch/rate/volume + SSML emotions
    """

    def __init__(
        self,
        mode: Literal["stdout", "aplay", "edge_tts"] = "stdout",
        edge_tts_voice: str = "en-US-JennyNeural",
        output_device: Optional[str] = None,
    ):
        self.mode = mode
        self.edge_tts_voice = edge_tts_voice
        self.output_device = output_device
        self._aplay_available = self._check_aplay()

        if mode == "aplay" and not self._aplay_available:
            print("[SpeakerTTS] aplay not found; falling back to stdout")
            self.mode = "stdout"

        self._edge_tts_ok = False
        if mode == "edge_tts":
            try:
                import edge_tts  # noqa: F401
                self._edge_tts_ok = True
            except ImportError:
                print("[SpeakerTTS] edge-tts not installed. pip install edge-tts")
                self.mode = "stdout"

    # ── Utilities ────────────────────────────────────────────────────────
    @staticmethod
    def _check_aplay() -> bool:
        try:
            subprocess.run(["aplay", "--version"], capture_output=True, check=True)
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def _map_emotion(emotion: Optional[str]) -> str:
        if not emotion:
            return ""
        return EMOTION_SSML.get(emotion.lower().strip(), "default")

    @staticmethod
    def _build_ssml(text: str, voice: str, style: str,
                    rate: str = "+0%", pitch: str = "+0Hz", volume: str = "+0%") -> str:
        """Wrap plain text in SSML for Microsoft cognitive voices."""
        # Escape XML special chars
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe = safe.replace('"', "&quot;").replace("'", "&apos;")

        if style and style != "default":
            return (
                "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
                "xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>"
                f"<voice name='{voice}'>"
                f"<mstts:express-as style='{style}'>"
                f"<prosody rate='{rate}' pitch='{pitch}' volume='{volume}'>"
                f"{safe}"
                "</prosody>"
                "</mstts:express-as>"
                "</voice>"
                "</speak>"
            )
        return (
            "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
            f"<voice name='{voice}'>"
            f"<prosody rate='{rate}' pitch='{pitch}' volume='{volume}'>"
            f"{safe}"
            "</prosody>"
            "</voice>"
            "</speak>"
        )

    # ── Public API ───────────────────────────────────────────────────────
    def speak(
        self,
        text: str,
        emotion: Optional[str] = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
        volume: str = "+0%",
    ) -> None:
        """Speak text aloud with optional emotion and prosody.

        Args:
            text:    The text to speak.
            emotion: emotional style — happy, sad, excited, whispering,
                     angry, terrified, apologetic, empathetic, etc.
            rate:    speech rate — "+10%" = faster, "-10%" = slower
            pitch:   pitch shift — "+10Hz" = higher
            volume:  "+0%" = normal
        """
        if not text or not text.strip():
            return

        if self.mode == "stdout":
            emoji = self._emotion_emoji(emotion)
            print(f"\n[SPEAK {emoji}] {text.strip()}\n")
            return

        if self.mode == "aplay":
            print(f"\n[SPEAK 🗣️ (aplay)] {text.strip()}\n")
            return

        if self.mode == "edge_tts":
            self._speak_edge_tts(text, emotion, rate, pitch, volume)
            return

    def _emotion_emoji(self, emotion: Optional[str]) -> str:
        emap = {
            "happy": "😊", "cheerful": "😊", "excited": "🎉",
            "sad": "😢", "depressed": "😢", "angry": "😠",
            "whispering": "🤫", "whisper": "🤫",
            "terrified": "😱", "apologetic": "😔", "empathetic": "💗",
        }
        return emap.get(emotion.lower() if emotion else "", "🗣️")

    # ── Edge-TTS with SSML + Prosody ──────────────────────────────────────
    def _speak_edge_tts(
        self,
        text: str,
        emotion: Optional[str],
        rate: str,
        pitch: str,
        volume: str,
    ) -> None:
        try:
            import edge_tts
        except ImportError:
            print("[SpeakerTTS] edge-tts not installed. pip install edge-tts")
            return

        style = self._map_emotion(emotion)
        use_ssml = bool(style and style != "default")

        async def _gen():
            if use_ssml:
                ssml = self._build_ssml(text, self.edge_tts_voice, style, rate, pitch, volume)
                communicate = edge_tts.Communicate(ssml, self.edge_tts_voice)
            else:
                communicate = edge_tts.Communicate(text, self.edge_tts_voice, rate=rate, pitch=pitch, volume=volume)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                tmp_path = f.name
            await communicate.save(tmp_path)

            # ── Play via GStreamer (Jetson native, handles MP3 → ALSA) ─
            if self.output_device:
                cmd = [
                    "gst-launch-1.0", "filesrc", f"location={tmp_path}",
                    "!", "decodebin", "!", "audioconvert", "!", "audioresample",
                    "!", "alsasink", f"device={self.output_device}",
                ]
            else:
                # Use playbin with default PulseAudio/ALSA sink
                cmd = ["gst-launch-1.0", "playbin", f"uri=file://{tmp_path}"]

            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode != 0:
                err = result.stderr.decode(errors="ignore")[:300]
                print(f"[SpeakerTTS] GStreamer error: {err}")
            os.unlink(tmp_path)

        # Edge-tts requires asyncio event loop
        asyncio.run(_gen())

    # ── Convenience emotion helpers ────────────────────────────────────────
    def speak_happy(self, text: str) -> None:
        self.speak(text, emotion="happy", rate="+8%", pitch="+5Hz")

    def speak_sad(self, text: str) -> None:
        self.speak(text, emotion="sad", rate="-10%", pitch="-8Hz", volume="-20%")

    def speak_excited(self, text: str) -> None:
        self.speak(text, emotion="excited", rate="+15%", pitch="+10Hz", volume="+10%")

    def speak_whisper(self, text: str) -> None:
        self.speak(text, emotion="whispering", rate="-5%", volume="-30%")

    def speak_angry(self, text: str) -> None:
        self.speak(text, emotion="angry", rate="+5%", pitch="-2Hz", volume="+20%")

    def speak_scared(self, text: str) -> None:
        self.speak(text, emotion="terrified", rate="+20%", pitch="+30Hz")

    # ── Feedback beep ────────────────────────────────────────────────────
    def play_beep(self, freq: int = 880, duration_ms: int = 150) -> None:
        """Simple feedback beep for wake word detection."""
        if self.mode == "stdout":
            print("[BEEP 🔊]")
            return
        if not self._aplay_available:
            return
        try:
            sr = 22050
            t = int(sr * duration_ms / 1000)
            import math
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
