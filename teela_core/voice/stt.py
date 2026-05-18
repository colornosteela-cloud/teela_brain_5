"""
Speech-to-Text Pipeline

Requirements:
    - OpenAI Whisper (run locally on Jetson with whisper.cpp or faster-whisper)
    - Or cloud API (Google, Azure, etc.)
    - VAD (Voice Activity Detection) for wake-word and silence detection

Architecture:
    Audio stream -> VAD -> Speech segments -> Whisper -> Text utterances
"""

import io
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

import numpy as np


@dataclass
class Utterance:
    text: str
    confidence: float
    speaker: Optional[str] = None  # if speaker ID known
    start_time: float = 0.0
    duration_s: float = 0.0
    is_complete: bool = True


class VoiceActivityDetector:
    """Simple energy-based VAD. Replace with Silero VAD for production."""

    def __init__(self, energy_threshold: float = 0.02, min_speech_sec: float = 0.3, min_silence_sec: float = 0.5):
        self.energy_threshold = energy_threshold
        self.min_speech_sec = min_speech_sec
        self.min_silence_sec = min_silence_sec
        self.sample_rate = 16000
        
        self._buffer: list[np.ndarray] = []
        self._speech_started = False
        self._silence_start: Optional[float] = None
        self._speech_start: Optional[float] = None

    def process_chunk(self, chunk: np.ndarray, timestamp: float) -> Optional[np.ndarray]:
        """Returns speech chunk when a complete utterance is detected."""
        energy = np.sqrt(np.mean(chunk**2))
        
        if energy > self.energy_threshold and not self._speech_started:
            self._speech_started = True
            self._speech_start = timestamp
            self._silence_start = None
            self._buffer = [chunk]
        elif energy > self.energy_threshold and self._speech_started:
            self._buffer.append(chunk)
            self._silence_start = None
        elif energy <= self.energy_threshold and self._speech_started:
            if self._silence_start is None:
                self._silence_start = timestamp
            self._buffer.append(chunk)
            
            # Check if silence is long enough
            if self._silence_start and (timestamp - self._silence_start) > self.min_silence_sec:
                # Check minimum speech duration
                speech_duration = self._silence_start - self._speech_start
                if speech_duration >= self.min_speech_sec:
                    result = np.concatenate(self._buffer)
                    self._reset()
                    return result
                else:
                    self._reset()  # too short, discard
        return None

    def _reset(self) -> None:
        self._speech_started = False
        self._silence_start = None
        self._speech_start = None
        self._buffer = []


class STTPipeline:
    """Full STT: audio capture -> VAD -> transcribe."""

    def __init__(
        self,
        whisper_model_size: str = "base",
        language: str = "en",
        device: str = "cuda",  # or "cpu" on Jetson
    ):
        self.vad = VoiceActivityDetector()
        self.language = language
        self.device = device
        self._whisper = None  # lazy load
        self._model_size = whisper_model_size

    def _load_whisper(self):
        if self._whisper is not None:
            return
        try:
            import whisper  # type: ignore[import]
            self._whisper = whisper.load_model(self._model_size).to(self.device)
        except Exception:
            # fallback: use faster-whisper or API
            self._whisper = None

    def transcribe_audio(self, audio: np.ndarray) -> Optional[Utterance]:
        """Transcribe a single utterance buffer."""
        self._load_whisper()
        if self._whisper is None:
            return Utterance(text="[STT unavailable]", confidence=0.0, is_complete=False)
        
        # Whisper expects float32 normalized to [-1, 1]
        audio = audio.astype(np.float32)
        if audio.max() > 1.0:
            audio = audio / 32768.0
        
        result = self._whisper.transcribe(audio, language=self.language)
        text = result.get("text", "").strip()
        confidence = 0.9  # approximate
        return Utterance(text=text, confidence=confidence)

    def stream_audio(self, audio_generator: Iterator[np.ndarray]) -> Iterator[Utterance]:
        """Process streaming audio, yield transcribed utterances."""
        for i, chunk in enumerate(audio_generator):
            t = time.time()
            speech = self.vad.process_chunk(chunk, t)
            if speech is not None:
                yield self.transcribe_audio(speech)
