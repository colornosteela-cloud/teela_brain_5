"""Real microphone STT + Wake Word for Jetson.

Continuously listens via ALSA/sounddevice.
Two modes:
    1. WAKE    → listening for "Hey Teela" (low power)
    2. ACTIVE  → full STT after wake word detected

Falls back to keyboard input for testing.
"""

import json
import queue
import threading
import time
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
        samplerate: int = 16000,
        block_duration_ms: int = 500,       # wake word processing block
        silence_duration_ms: int = 1500,     # end-of-utterance threshold
        max_active_duration_ms: int = 10000, # timeout after wake word
    ):
        self.endpoint = stt_endpoint
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
        self._on_wake: Optional[Callable[[], None]] = None  # called when wake word fires

        # State machine
        self._mode: str = "IDLE"  # IDLE | WAKE | ACTIVE
        self._accumulated_audio: List[float] = []
        self._last_speech_time = 0.0
        self._voice_active = False
        self._active_start_time = 0.0
        self._block_samples = int(samplerate * block_duration_ms / 1000)
        self._stt_buffer: List[float] = []  # audio for STT after wake

        self._wake_word_detector: Optional[object] = None

    def set_wake_word_detector(self, detector: object) -> None:
        """Inject a WakeWordDetector instance."""
        self._wake_word_detector = detector

    def set_wake_callback(self, fn: Callable[[], None]) -> None:
        """Called when wake word is detected (for beep / LED)."""
        self._on_wake = fn

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
        if self._wake_word_detector is None:
            # No wake word configured → always active (always-on listening)
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
            self._stt_buffer = audio.tolist().copy()  # keep the wake-word audio + start buffering
            if self._on_wake:
                self._on_wake()
            print(f"[MicSTT] Wake word detected! Listening... (confidence={event.confidence:.2f})")
        else:
            # Still idle — just discard audio
            pass

    def _process_active(self, audio: np.ndarray, now: float) -> None:
        """In WAKE/ACTIVE: buffer audio, detect silence, then flush to STT."""
        self._stt_buffer.extend(audio.tolist())

        # RMS energy check for VAD
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        threshold = 0.01  # above this = speech

        if rms > threshold:
            self._voice_active = True
            self._last_speech_time = now

        silence_duration = now - self._last_speech_time
        active_duration = now - self._active_start_time

        # Flush conditions:
        # 1. Silence after speech → end of utterance
        # 2. Max active duration exceeded → timeout
        if (self._voice_active and silence_duration > self.silence_duration_ms / 1000.0):
            self._flush_stt()
            self._reset_to_idle()
        elif active_duration > self.max_active_duration_ms / 1000.0:
            print("[MicSTT] Active timeout — returning to idle.")
            self._flush_stt()
            self._reset_to_idle()

    def _flush_stt(self) -> None:
        if not self._stt_buffer:
            return

        # Send to STT endpoint
        if self.endpoint and self._callback:
            import struct, urllib.request
            try:
                pcm = struct.pack("f" * len(self._stt_buffer), *self._stt_buffer)
                req = urllib.request.Request(
                    self.endpoint,
                    data=pcm,
                    headers={"Content-Type": "audio/raw", "X-SampleRate": str(self.samplerate)},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    result = json.loads(resp.read().decode())
                    text = result.get("text", "").strip()
                    if text:
                        self._callback(text)
            except Exception as e:
                print(f"[MicSTT] STT error: {e}")
        else:
            # For testing without endpoint: just print what we captured
            dur = len(self._stt_buffer) / self.samplerate
            print(f"[MicSTT] Captured {dur:.1f}s of audio (no STT endpoint)")

        self._stt_buffer.clear()

    def _reset_to_idle(self) -> None:
        self._mode = "IDLE"
        self._voice_active = False
        self._stt_buffer.clear()
        print("[MicSTT] Returned to idle — waiting for wake word.")

    # ── Public API ─────────────────────────────────────

    def start(self, on_transcript: Callable[[str], None]) -> None:
        self._callback = on_transcript
        self._running = True
        self._mode = "IDLE"

        if self._has_sounddevice:
            self._stream = self.sd.RawInputStream(
                samplerate=self.samplerate,
                blocksize=self._block_samples,
                dtype="float32",
                channels=1,
                callback=self._audio_callback,
            )
            self._stream.start()
            print(f"[MicSTT] Mic stream started at {self.samplerate} Hz — waiting for 'Hey Teela'")
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
