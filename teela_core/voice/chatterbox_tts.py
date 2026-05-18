"""Teela's expressive voice — Chatterbox-Turbo with emotional intelligence.

This module is a drop-in replacement for tts_speaker.py.
It uses:
  1. Chatterbox-Turbo with Jade's cloned voice (15 emotions)
  2. Auto-detects emotion from text
  3. Falls back to Edge-TTS if offline

Usage:
    from teela_core.voice.chatterbox_tts import ChatterboxSpeaker
    
    speaker = ChatterboxSpeaker(voices_dir="voices/jade_cloned")
    speaker.speak("I'm so excited!", emotion="excited")
    speaker.speak("I miss you...")  # Auto-detects 'sad'
    
Or via emotion tag:
    speaker.speak("[EMOTION: happy] Hey there! Good to see you!")
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal, Optional, Dict

# Ensure chatterbox is in path
_HOME = Path.home()
sys.path.insert(0, str(_HOME / ".local" / "lib" / "python3.10" / "site-packages"))

# ── Emotion → Voice file + Tags mapping ───────────────────────
EMOTION_VOICE_MAP: Dict[str, Dict] = {
    "happy":      {"file": "teela_clone_01_happy.wav", "emoji": "😊"},
    "general":    {"file": "teela_clone_01_happy.wav", "emoji": "🙂"},
    "surprised":  {"file": "teela_clone_02_surprised.wav", "emoji": "😲"},
    "angry":      {"file": "teela_clone_03_angry.wav", "emoji": "😠"},
    "proud":      {"file": "teela_clone_04_proud.wav", "emoji": "💪"},
    "whispering": {"file": "teela_clone_05_whispering.wav", "emoji": "🤫"},
    "sad":        {"file": "teela_clone_06_sad.wav", "emoji": "😢"},
    "curious":    {"file": "teela_clone_07_curious_awed.wav", "emoji": "🤩"},
    "sassy":      {"file": "teela_clone_08_sassy.wav", "emoji": "💅"},
    "flirty":     {"file": "teela_clone_09_flirty.wav", "emoji": "😘"},
    "sleepy":     {"file": "teela_clone_10_sleepy.wav", "emoji": "😴"},
    "scared":     {"file": "teela_clone_11_scared.wav", "emoji": "😨"},
    "loving":     {"file": "teela_clone_12_loving.wav", "emoji": "💖"},
    "confused":   {"file": "teela_clone_13_confused.wav", "emoji": "🤔"},
    "excited":    {"file": "teela_clone_14_excited.wav", "emoji": "🎉"},
    "disappointed": {"file": "teela_clone_15_disappointed.wav", "emoji": "😞"},
}

EMOTION_PATTERNS = {
    "sad": ["sad", "cry", "tear", "miss", "lonely", "hurt", "pain", "upset", "sorry", "miss you"],
    "angry": ["angry", "mad", "furious", "hate", "stupid", "annoy", "frustrat", "unfair"],
    "happy": ["happy", "joy", "glad", "cheerful", "great", "wonderful", "love", "laugh", "amazing"],
    "surprised": ["wow", "whoa", "omg", "unbelievable", "shocked", "amazed", "incredible"],
    "curious": ["wonder", "curious", "how", "why", "what if", "mystery", "strange", "fascinating"],
    "confused": ["confused", "puzzled", "lost", "don't understand", "huh", "what do you mean"],
    "scared": ["scared", "afraid", "fear", "terrified", "spooky", "scary", "panic", "nervous"],
    "loving": ["love you", "care", "sweet", "dear", "honey", "darling", "adore", "cherish"],
    "proud": ["proud", "achieve", "success", "win", "victory", "mastered", "nailed"],
    "sassy": ["seriously", "as if", "whatever", "duh", "obvi", "slay", "iconic"],
    "flirty": ["cute", "handsome", "pretty", "gorgeous", "hot", "flirt", "wink", "come closer"],
    "disappointed": ["disappointed", "let down", "expected better", "failed", "sigh", "regrettably"],
    "excited": ["excited", "pumped", "hyped", "can't wait", "let's go", "yahoo", "woo"],
    "sleepy": ["tired", "sleepy", "exhausted", "yawn", "nap", "bed", "sleep", "drowsy"],
    "whispering": ["secret", "quiet", "shh", "whisper", "private", "don't tell"],
}


def _detect_emotion(text: str) -> str:
    """Simple keyword-based emotion detection."""
    text_lower = text.lower()
    scores = {}
    for emotion, keywords in EMOTION_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[emotion] = score
    if not scores:
        return "general"
    return max(scores, key=scores.get)


def _check_player() -> Optional[str]:
    """Find best available audio player."""
    for cmd in ["gst-play-1.0", "ffplay", "aplay"]:
        try:
            subprocess.run(["which", cmd], check=True, capture_output=True)
            return cmd
        except subprocess.CalledProcessError:
            continue
    return None


def _play_wav(path: str, player: str) -> None:
    """Play WAV file via best available method."""
    if player == "ffplay":
        subprocess.run(["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet", path], capture_output=True)
    elif player == "gst-play-1.0":
        subprocess.run(["gst-play-1.0", "--quiet", path], capture_output=True)
    elif player == "aplay":
        subprocess.run(["aplay", path], capture_output=True)


class ChatterboxSpeaker:
    """Drop-in replacement for SpeakerTTS using Chatterbox-Turbo + cloned emotions.

    Modes:
      chatterbox → Chatterbox-Turbo with Jade's cloned voice (default, offline)
      stdout     → print transcript with emoji
      edge_tts   → cloud TTS fallback (when chatterbox unavailable)
    """

    def __init__(
        self,
        mode: Literal["chatterbox", "stdout", "edge_tts"] = "chatterbox",
        voices_dir: str = "voices/jade_cloned",  # relative to project root
        device: str = "cpu",
        output_device: Optional[str] = None,
        edge_tts_voice: str = "en-US-JennyNeural",
    ):
        self.mode = mode
        self.voices_dir = Path(voices_dir)
        self.device = device
        self.output_device = output_device
        self.edge_tts_voice = edge_tts_voice
        self.player = _check_player()
        self._model = None
        self._model_loaded = False

        # Find voices_dir relative to project root
        project_root = Path(__file__).parent.parent.parent
        self.full_voices_dir = project_root / voices_dir
        if not self.full_voices_dir.exists() and Path(voices_dir).is_absolute():
            self.full_voices_dir = Path(voices_dir)

        # Try loading Chatterbox model on init
        if mode == "chatterbox":
            self._ensure_model()

    # ── Model Lazy Loading ────────────────────────────────────
    def _ensure_model(self) -> bool:
        """Lazy-load Chatterbox. Returns True if available."""
        if self._model_loaded:
            return self._model is not None
        try:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            import torchaudio
            print("🎙️  [ChatterboxSpeaker] Loading Chatterbox-Turbo...")
            self._model = ChatterboxTurboTTS.from_pretrained(device=self.device)
            self._model_loaded = True
            print("     ✅ Model ready!")
            return True
        except ImportError:
            print("⚠️  [ChatterboxSpeaker] chatterbox-tts not installed. Falling back to stdout.")
            self.mode = "stdout"
            self._model_loaded = True
            return False
        except Exception as e:
            print(f"⚠️  [ChatterboxSpeaker] Failed to load: {e}. Falling back to stdout.")
            self.mode = "stdout"
            self._model_loaded = True
            return False

    # ── Public API (matches SpeakerTTS interface) ──────────────
    def speak(
        self,
        text: str,
        emotion: Optional[str] = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
        volume: str = "+0%",
    ) -> None:
        """Speak text aloud with Chatterbox-Turbo emotion cloning.

        Emotion is auto-detected from text if not provided.
        """
        if not text or not text.strip():
            return

        # Strip explicit [EMOTION: xxx] tags
        raw_text = text.strip()
        emo_match = re.match(r'\[\s*EMOTION\s*:\s*(\w+)\s*\]\s*(.*)', raw_text, re.IGNORECASE)
        if emo_match:
            emotion = emo_match.group(1).lower().strip()
            raw_text = emo_match.group(2).strip()

        # Auto-detect if no emotion
        if not emotion:
            emotion = _detect_emotion(raw_text)

        emotion = emotion.lower().strip()
        config = EMOTION_VOICE_MAP.get(emotion, EMOTION_VOICE_MAP["general"])
        emoji = config["emoji"]

        # === stdout fallback ===
        if self.mode == "stdout":
            print(f"\n[SPEAK {emoji}] {raw_text}\n")
            print(f"       (emotion={emotion}, voice={config['file']})")
            return

        # === Chatterbox ===
        if self.mode == "chatterbox":
            if not self._ensure_model():
                print("\n[SPEAK {emoji}] {raw_text}\n")
                return

            voice_path = self.full_voices_dir / config["file"]
            if not voice_path.exists():
                print(f"⚠️  Voice file not found: {voice_path}, using reference")
                voice_path = self.full_voices_dir / "reference.wav"

            try:
                t0 = time.time()
                wav = self._model.generate(raw_text, audio_prompt_path=str(voice_path))
                
                import torchaudio
                tmp_path = f"/tmp/teela_voice_{int(time.time())}.wav"
                torchaudio.save(tmp_path, wav, self._model.sr)
                elapsed = time.time() - t0
                
                print(f"\n[SPEAK {emoji} ⚡{elapsed:.1f}s] {raw_text}")
                
                if self.player:
                    _play_wav(tmp_path, self.player)
                else:
                    print(f"       (no player — saved to {tmp_path})")
                    
            except Exception as e:
                print(f"❌ [Chatterbox error: {e}]")
                print(f"\n[SPEAK {emoji}] {raw_text}\n")
            return

        # === Edge TTS fallback ===
        if self.mode == "edge_tts":
            self._speak_edge_tts(raw_text, emotion, rate, pitch, volume)
            return

    # ── Legacy API compatibility ──────────────────────────────
    def speak_happy(self, text: str) -> None:
        self.speak(text, emotion="happy")

    def speak_sad(self, text: str) -> None:
        self.speak(text, emotion="sad")

    def speak_excited(self, text: str) -> None:
        self.speak(text, emotion="excited")

    def speak_whisper(self, text: str) -> None:
        self.speak(text, emotion="whispering")

    def speak_angry(self, text: str) -> None:
        self.speak(text, emotion="angry")

    def speak_scared(self, text: str) -> None:
        self.speak(text, emotion="scared")

    def speak_loving(self, text: str) -> None:
        self.speak(text, emotion="loving")

    def speak_sassy(self, text: str) -> None:
        self.speak(text, emotion="sassy")

    def play_beep(self, freq: int = 880, duration_ms: int = 150) -> None:
        """Play a simple beep."""
        if self.mode == "stdout":
            print("[BEEP 🔊]")
            return
        try:
            import math
            import struct
            import tempfile
            sr = 22050
            t = int(sr * duration_ms / 1000)
            samples = bytes()
            for i in range(t):
                v = int(math.sin(freq * 2 * math.pi * i / sr) * 0.3 * 32767)
                samples += struct.pack('<h', v)
            
            # WAV header
            data_size = len(samples)
            wav = b'RIFF' + struct.pack('<I', 36 + data_size)
            wav += b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 1, sr, sr * 2, 2, 16)
            wav += b'data' + struct.pack('<I', data_size) + samples
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav)
                tmp = f.name
            if self.player:
                _play_wav(tmp, self.player)
            os.unlink(tmp)
        except Exception:
            pass

    # ── Edge TTS implementation (from tts_speaker.py) ─────────
    def _speak_edge_tts(self, text: str, emotion: Optional[str],
                       rate: str, pitch: str, volume: str) -> None:
        try:
            import edge_tts
            import asyncio
        except ImportError:
            print("[ChatterboxSpeaker] edge-tts not installed")
            return

        # Simple default (no SSML for now)
        async def _gen():
            communicate = edge_tts.Communicate(text, self.edge_tts_voice)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                tmp_path = f.name
            await communicate.save(tmp_path)
            
            if self.player:
                _play_wav(tmp_path, self.player)
            else:
                print(f"       (saved to {tmp_path})")

        asyncio.run(_gen())

    # ── Convenience ────────────────────────────────────────────
    def get_emotion_for_text(self, text: str) -> str:
        """Debug: show what emotion a text would trigger."""
        return _detect_emotion(text)

    def list_emotions(self) -> None:
        """Print all available emotions."""
        print("🎭 Teela's Emotion Voice Library:")
        print("=" * 50)
        for key, config in EMOTION_VOICE_MAP.items():
            if key == "general":
                continue
            print(f"  {config['emoji']} {key:15s} → {config['file']}")
        print("=" * 50)
