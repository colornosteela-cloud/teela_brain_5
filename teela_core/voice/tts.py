"""
Text-to-Speech Pipeline — Chatterbox-Turbo + Emotion Brain Edition

Output: audio bytes sent to speaker.
Supports:
    - Chatterbox-Turbo (offline, emotion-aware, Jade's cloned voice)
    - Edge TTS (online fallback)
    - pyttsx3 (offline, robotic but instant)

Teela's voice:
    - Cloned from Jade (warm, slightly higher pitch)
    - 15 emotions auto-selected from text
    - Paralinguistic tags ([chuckle], [sigh], etc.) for realism
"""

import io
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SpeechParams:
    wpm: int = 140
    pitch: int = 0  # Hz shift
    volume_db: int = -10


class ChatterboxEmotionTTS:
    """TTS with emotion detection + Chatterbox-Turbo voice cloning.
    
    Auto-detects emotion → picks Jade's voice sample → injects paralinguistic tags.
    """
    
    def __init__(self, voices_dir: str = "voices/jade_cloned", device: str = "cpu"):
        self.voices_dir = Path(voices_dir)
        self.device = device
        self.model = None
        self._last_speech_time = 0.0
        
    def _load_model(self):
        """Lazy-load Chatterbox-Turbo (expensive, only do once)."""
        if self.model is not None:
            return self.model
        try:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            print("[TTS] Loading Chatterbox-Turbo model...")
            self.model = ChatterboxTurboTTS.from_pretrained(device=self.device)
            print("[TTS] Model loaded.")
            return self.model
        except ImportError:
            print("[TTS] chatterbox-tts not installed. Install: pip install chatterbox-tts")
            return None

    def _get_reference_voice(self, emotion: str) -> Optional[Path]:
        """Map emotion to Jade's voice file."""
        voice_map = {
            "happy": "teela_clone_01_happy.wav",
            "general": "teela_clone_01_happy.wav",
            "surprised": "teela_clone_02_surprised.wav",
            "angry": "teela_clone_03_angry.wav",
            "proud": "teela_clone_04_proud.wav",
            "whispering": "teela_clone_05_whispering.wav",
            "sad": "teela_clone_06_sad.wav",
            "curious": "teela_clone_07_curious_awed.wav",
            "sassy": "teela_clone_08_sassy.wav",
            "flirty": "teela_clone_09_flirty.wav",
            "sleepy": "teela_clone_10_sleepy.wav",
            "scared": "teela_clone_11_scared.wav",
            "loving": "teela_clone_12_loving.wav",
            "confused": "teela_clone_13_confused.wav",
            "excited": "teela_clone_14_excited.wav",
            "disappointed": "teela_clone_15_disappointed.wav",
        }
        voice_file = voice_map.get(emotion, "teela_clone_01_happy.wav")
        return self.voices_dir / voice_file
    
    def speak(self, text: str, emotion_override: Optional[str] = None, 
              params: Optional[SpeechParams] = None) -> Optional[bytes]:
        """
        Convert text to emotional audio using Chatterbox-Turbo.
        
        Steps:
          1. Detect emotion from text (or use override)
          2. Get reference voice file for that emotion
          3. Inject paralinguistic tags
          4. Generate with Chatterbox-Turbo
        
        Returns audio bytes or None on failure.
        """
        params = params or SpeechParams()
        self._last_speech_time = time.time()
        
        # Step 1: Detect emotion
        emotion = emotion_override or self._detect_emotion(text)
        
        # Step 2: Get reference voice
        ref_voice = self._get_reference_voice(emotion)
        if not ref_voice.exists():
            print(f"[TTS] Voice file not found: {ref_voice}, falling back to general")
            ref_voice = self.voices_dir / "teela_clone_01_happy.wav"
        
        # Step 3: Get model
        model = self._load_model()
        if model is None:
            print("[TTS] Chatterbox not available, using fallback")
            return None
        
        # Step 4: Generate audio
        try:
            import torchaudio
            wav = model.generate(text, audio_prompt_path=str(ref_voice))
            
            # Save to bytes
            tmp_path = "/tmp/teela_tts_output.wav"
            torchaudio.save(tmp_path, wav, model.sr)
            with open(tmp_path, "rb") as f:
                return f.read()
        except Exception as e:
            print(f"[TTS] Generation error: {e}")
            return None
    
    def _detect_emotion(self, text: str) -> str:
        """Simple emotion detection from text keywords."""
        text_lower = text.lower()
        
        # Score each emotion
        scores = {}
        patterns = {
            "sad": ["sad", "cry", "tear", "miss", "lonely", "hurt", "pain", "upset", "sorry"],
            "angry": ["angry", "mad", "furious", "hate", "stupid", "annoy", "frustrated", "unfair"],
            "happy": ["happy", "joy", "glad", "cheerful", "great", "wonderful", "love", "laugh"],
            "surprised": ["wow", "whoa", "omg", "unbelievable", "shocked", "amazed"],
            "curious": ["wonder", "curious", "how", "why", "what if", "mystery", "strange"],
            "confused": ["confused", "puzzled", "lost", "don't understand", "huh"],
            "scared": ["scared", "afraid", "fear", "terrified", "spooky", "scary", "panic"],
            "loving": ["love you", "care", "sweet", "dear", "honey", "darling", "adore"],
            "proud": ["proud", "achieve", "success", "win", "victory", "mastered"],
            "sassy": ["seriously", "as if", "whatever", "duh", "obvi", "slay"],
            "flirty": ["cute", "handsome", "pretty", "gorgeous", "hot", "flirt", "wink"],
            "disappointed": ["disappointed", "let down", "expected better", "failed", "sigh"],
            "excited": ["excited", "pumped", "hyped", "can't wait", "let's go", "yahoo"],
            "sleepy": ["tired", "sleepy", "exhausted", "yawn", "nap", "bed", "sleep"],
            "whispering": ["secret", "quiet", "shh", "whisper", "private"],
        }
        
        for emotion, keywords in patterns.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[emotion] = score
        
        if not scores:
            return "general"
        return max(scores, key=scores.get)


class LegacyTTSEngine:
    """Fallback TTS using Edge TTS or pyttsx3 (for when Chatterbox is unavailable)."""

    def __init__(self, engine: str = "edge-tts"):
        self.engine = engine
        self._last_speech_time = 0.0

    def speak(self, text: str, params: Optional[SpeechParams] = None) -> Optional[bytes]:
        """Convert text to audio bytes. Returns None if engine unavailable."""
        params = params or SpeechParams()
        self._last_speech_time = time.time()

        if self.engine == "edge-tts":
            return self._edge_tts(text, params)
        elif self.engine == "pyttsx3":
            return self._pyttsx3_tts(text, params)
        return None

    def _edge_tts(self, text: str, params: SpeechParams) -> Optional[bytes]:
        try:
            import edge_tts  # type: ignore[import]
            communicate = edge_tts.Communicate(text, voice="en-US-JennyNeural")
            output = io.BytesIO()
            for chunk in communicate.stream_sync():
                if chunk["type"] == "audio":
                    output.write(chunk["data"])
            return output.getvalue()
        except Exception:
            return None

    def _pyttsx3_tts(self, text: str, params: SpeechParams) -> Optional[bytes]:
        try:
            import pyttsx3  # type: ignore[import]
            import tempfile
            engine = pyttsx3.init()
            engine.setProperty("rate", params.wpm)
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            engine.save_to_file(text, tmp.name)
            engine.runAndWait()
            with open(tmp.name, "rb") as f:
                return f.read()
        except Exception:
            return None


class TTSEngine:
    """Unified TTS: Chatterbox-Turbo + Emotional Intelligence + Fallbacks."""
    
    def __init__(self, voices_dir: str = "voices/jade_cloned", device: str = "cpu"):
        self.chatterbox = ChatterboxEmotionTTS(voices_dir=voices_dir, device=device)
        self.fallback = LegacyTTSEngine(engine="edge-tts")
    
    def speak(self, text: str, emotion_override: Optional[str] = None,
              params: Optional[SpeechParams] = None) -> Optional[bytes]:
        """
        Generate audio with emotion detection.
        
        Priority:
          1. Chatterbox-Turbo with Jade's cloned voice + emotion
          2. Edge TTS fallback
        """
        # Try Chatterbox first
        audio = self.chatterbox.speak(text, emotion_override=emotion_override, params=params)
        if audio is not None:
            return audio
        
        # Fallback to cloud TTS
        print("[TTS] Falling back to Edge TTS")
        return self.fallback.speak(text, params)
    
    def get_emotion_for_text(self, text: str) -> str:
        """Return the detected emotion for debugging."""
        return self.chatterbox._detect_emotion(text)
    
    def get_voice_file(self, emotion: str) -> Optional[Path]:
        """Return the voice file path for an emotion."""
        return self.chatterbox._get_reference_voice(emotion)
