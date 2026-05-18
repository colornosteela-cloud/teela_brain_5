"""Real microphone STT + Wake Word for Jetson.

Continuously listens via ALSA/sounddevice.
Two modes:
    1. WAKE    → listening for "Hey Teela" (low power)
    2. ACTIVE  → full STT after wake word detected

STT backends (in order of preference):
    - whisper_local   → faster-whisper, runs on local GPU (Jetson Orin) — RECOMMENDED
    - cloud_endpoint  → external STT via REST API
    - keyboard        → fall back to typing (headless dev)

Falls back to keyboard input if sounddevice unavailable.
"""

import json
import queue
import threading
import time
import wave
from io import BytesIO
from typing import Callable, List, Optional

import numpy as np


class MicSTT:
    """Capture audio from mic, detect wake word, then stream STT.

    State machine:
        IDLE   → mic is hot, waiting for wake word
        WAKE   → wake word detected, buffering for STT
        ACTIVE → streaming to STT endpoint for N seconds after speech ends
    """

    def __init__(
        self,
        stt_endpoint: Optional[str] = None,
        stt_backend: str = "whisper",        # "whisper" | "endpoint" | "keyboard"
        whisper_model: str = "base",           # tiny / base / small / medium / large
        samplerate: int = 16000,
        block_duration_ms: int = 500,       # wake word processing block
        silence_duration_ms: int = 1500,     # end-of-utterance threshold
        max_active_duration_ms: int = 10000, # timeout after wake word
    ):
        self.endpoint = stt_endpoint
        self.stt_backend = stt_backend
        self.whisper_model_name = whisper_model
        self.samplerate = samplerate
        self.block_duration_ms = block_duration_ms
        self.silence_duration_ms = silence_duration_ms
        self.max_active_duration_ms = max_active_duration_ms

        self._has_sounddevice = False
        try:
            import sounddevice as sd
            self._has_sounddevice = True
            self.sd = sd
        except ImportError:
            print("[MicSTT] sounddevice not installed. pip install sounddevice")
            print("[MicSTT] Falling back to keyboard input.")

        self._audio_queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: threading.Thread | None = None
        self._callback: Optional[Callable[[str], None]] = None
        self._on_wake: Optional[Callable[[], None]] = None

        # State machine
        self._mode: str = "IDLE"  # IDLE | WAKE | ACTIVE
        self._last_speech_time = 0.0
        self._voice_active = False
        self._active_start_time = 0.0
        self._block_samples = int(samplerate * block_duration_ms / 1000)
        self._stt_buffer: List[float] = []  # audio for STT after wake

        self._wake_word_detector: Optional[object] = None

        # Whisper lazy load
        self._whisper_model = None
        self._whisper_loaded = False

        # VAD state
        self._vad_threshold = 0.008  # typical whisper is ~0.005–0.02
        self._vad_hang_frames = 0
        self._vad_max_hang = 3      # blocks of silence before end-of-utterance

    def set_wake_word_detector(self, detector: object) -> None:
        """Inject a WakeWordDetector instance."""
        self._wake_word_detector = detector

    def set_wake_callback(self, fn: Callable[[], None]) -> None:
        """Called when wake word is detected (for beep / LED)."""
        self._on_wake = fn

    # ── Whisper local STT ───────────────────────────────

    def _load_whisper(self):
        if self._whisper_loaded:
            return
        self._whisper_loaded = True
        try:
            import faster_whisper  # type: ignore[import]
            print(f"[MicSTT] Loading Whisper '{self.whisper_model_name}' — this may take 20–60s...")
            device = "cuda" if faster_whisper.utils._is_cuda_available() else "cpu"
            model = faster_whisper.WhisperModel(
                self.whisper_model_name,
                device=device,
                compute_type="float16" if device == "cuda" else "int8",
            )
            self._whisper_model = model
            print(f"[MicSTT] Whisper ready on {device}.")
        except ImportError:
            print("[MicSTT] faster-whisper not installed.")
        except Exception as e:
            print(f"[MicSTT] Whisper load failed: {e}")

    def _transcribe_whisper(self, audio_np: np.ndarray) -> str:
        if self._whisper_model is None:
            self._load_whisper()
        if self._whisper_model is None:
            return ""
        try:
            segments, _ = self._whisper_model.transcribe(audio_np, language="en")
            text = " ".join(s.text for s in segments).strip()
            return text
        except Exception as e:
            print(f"[MicSTT] Whisper transcription error: {e}")
            return ""

    # ── Audio Callback ───────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[MicSTT] Audio status: {status}")
        self._audio_queue.put(indata.copy().flatten().tolist())

    # ── Main Loop ────────────────────────────────────────

    def _process_loop(self) -> None:
        while self._running:
            if self._has_sounddevice:
                try:
                    block = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                self._handle_audio_block(block)
            else:
                # Keyboard fallback
                try:
                    line = input("[YOU] ")
                    if line.strip() and self._callback:
                        self._callback(line.strip())
                except EOFError:
                    time.sleep(0.5)

    def _handle_audio_block(self, samples: List[float]) -> None:
        now = time.time()
        audio_np = np.array(samples, dtype=np.float32)

        if self._mode == "IDLE":
            self._process_idle(audio_np, now)
        elif self._mode in ("WAKE", "ACTIVE"):
            self._process_active(audio_np, now)

    def _process_idle(self, audio: np.ndarray, now: float) -> None:
        """In IDLE: pass audio to wake word detector."""
        if self.stt_backend == "keyboard":
            # Always-on keyboard
            return

        if self._wake_word_detector is None:
            # No wake word configured → always active
            self._mode = "ACTIVE"
            self._active_start_time = now
            self._stt_buffer.extend(audio.tolist())
            print("[MicSTT] No wake word detector — always-on listening.")
            return

        event = self._wake_word_detector.detect(audio, now)
        if event is not None:
            self._mode = "WAKE"
            self._active_start_time = now
            self._voice_active = False
            self._last_speech_time = now
            self._vad_hang_frames = 0
            self._stt_buffer = audio.tolist().copy()
            if self._on_wake:
                self._on_wake()
            print(f"[MicSTT] Wake word detected! Listening... (confidence={event.confidence:.2f})")
        # else: discard audio silently (no print spam)

    def _process_active(self, audio: np.ndarray, now: float) -> None:
        """In WAKE/ACTIVE: buffer audio, detect silence, then flush to STT."""
        self._stt_buffer.extend(audio.tolist())

        # VAD: track energy over time
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))

        if rms > self._vad_threshold:
            self._voice_active = True
            self._last_speech_time = now
            self._vad_hang_frames = 0
        else:
            self._vad_hang_frames += 1

        silence_duration = now - self._last_speech_time
        active_duration = now - self._active_start_time
        hang_silence = self._vad_hang_frames * (self.block_duration_ms / 1000.0)

        # Flush conditions:
        # 1. Hangover silence after speech → end of utterance
        # 2. Max active duration exceeded → timeout
        should_flush = False
        if self._voice_active and hang_silence > (self.silence_duration_ms / 1000.0):
            should_flush = True
        elif active_duration > (self.max_active_duration_ms / 1000.0):
            print("[MicSTT] Active timeout — returning to idle.")
            should_flush = True

        if should_flush:
            text = self._flush_stt()
            if text and self._callback:
                self._callback(text)
            self._reset_to_idle()

    def _flush_stt(self) -> str:
        """Transcribe buffered audio, return recognized text (or empty string)."""
        if not self._stt_buffer:
            return ""

        audio_np = np.array(self._stt_buffer, dtype=np.float32)
        dur = len(audio_np) / self.samplerate

        if dur < 0.5:
            print(f"[MicSTT] Too short ({dur:.1f}s). Ignoring.")
            self._stt_buffer.clear()
            return ""

        print(f"[MicSTT] Transcribing {dur:.1f}s of audio...")

        text = ""
        if self.stt_backend == "whisper":
            text = self._transcribe_whisper(audio_np)
        elif self.endpoint:
            text = self._transcribe_endpoint(audio_np)
        else:
            # No STT configured
            print(f"[MicSTT] No STT backend configured.")
            print("         Options:")
            print("           1. Install faster-whisper:  pip install faster-whisper")
            print(f"           2. Set config: voice.stt_backend='whisper'")
            print(f"           3. Set config: hardware.microphone.stt_endpoint=\"http://...\"")
            print("         Audio captured but not transcribed.")

        if text:
            print(f"[MicSTT] Recognized: \"{text}\"")

        self._stt_buffer.clear()
        return text

    def _transcribe_endpoint(self, audio_np: np.ndarray) -> str:
        import struct, urllib.request
        if not self.endpoint:
            return ""
        try:
            pcm = struct.pack("f" * len(audio_np), *audio_np)
            req = urllib.request.Request(
                self.endpoint,
                data=pcm,
                headers={"Content-Type": "audio/raw", "X-SampleRate": str(self.samplerate)},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                return result.get("text", "").strip()
        except Exception as e:
            print(f"[MicSTT] STT endpoint error: {e}")
            return ""

    def _reset_to_idle(self) -> None:
        self._mode = "IDLE"
        self._voice_active = False
        self._vad_hang_frames = 0
        self._stt_buffer.clear()
        print("[MicSTT] Returned to idle — waiting for 'Teela'.")

    # ── Public API ─────────────────────────────────────

    def start(self, on_transcript: Callable[[str], None]) -> None:
        self._callback = on_transcript
        self._running = True
        self._mode = "IDLE"

        if self.stt_backend == "keyboard":
            print("[MicSTT] Keyboard mode — type to talk to Teela.")
        elif self._has_sounddevice:
            self._stream = self.sd.RawInputStream(
                samplerate=self.samplerate,
                blocksize=self._block_samples,
                dtype="float32",
                channels=1,
                callback=self._audio_callback,
            )
            self._stream.start()

            backend_msg = "whisper (local)" if self.stt_backend == "whisper" else (f"endpoint: {self.endpoint}" if self.endpoint else "⚠️ none (install faster-whisper)")
            print(f"[MicSTT] Mic stream started at {self.samplerate} Hz")
            print(f"[MicSTT] STT: {backend_msg}")
            print(f"[MicSTT] Say 'Hey Teela' to wake me!")
        else:
            print("[MicSTT] No mic backend — type your input below.")

        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def force_active(self, duration_ms: int = 10000) -> None:
        """Force mic into ACTIVE mode (e.g., button press instead of wake word)."""
        self._mode = "ACTIVE"
        self._active_start_time = time.time()
        self._stt_buffer.clear()
        print("[MicSTT] Manual activation — listening...")

    def stop(self) -> None:
        self._running = False
        self._mode = "IDLE"
        if self._has_sounddevice:
            if hasattr(self, "_stream"):
                self._stream.stop()
                self._stream.close()
        if self._thread:
            self._thread.join(timeout=1.0)
        print("[MicSTT] Stopped.")
