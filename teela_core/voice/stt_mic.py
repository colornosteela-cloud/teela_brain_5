"""Real microphone STT + Wake Word for Jetson.

Backends (in order of preference):
  1. sounddevice / RawInputStream   → best for desktop/laptop
  2. arecord subprocess (ALSA)        → Jetson/embedded (no PortAudio needed)
  3. keyboard input                 → headless dev / fallback

STT backends (in order of preference):
  1. whisper_local   → faster-whisper, runs on local GPU (Jetson Orin)
  2. cloud_endpoint  → external STT via REST API  
  3. keyboard        → fall back to typing

State machine:
    IDLE   → mic is hot, waiting for wake word
    WAKE   → wake word detected, buffering for STT
    ACTIVE → streaming to STT endpoint for N seconds after speech ends
"""

import json
import queue
import subprocess
import threading
import time
import urllib.request
from typing import Callable, List, Optional

import numpy as np


USE_ALSA = True  # 🔧 always try ALSA directly on Jetson first


class MicSTT:
    """Capture audio from mic, detect wake word, then stream STT."""

    def __init__(
        self,
        stt_endpoint: Optional[str] = None,
        stt_backend: str = "whisper",               # "whisper" | "endpoint" | "keyboard"
        whisper_model: str = "base",                # tiny / base / small / medium / large
        samplerate: int = 16000,
        block_duration_ms: int = 500,               # wake word processing block
        silence_duration_ms: int = 1500,             # end-of-utterance threshold
        max_active_duration_ms: int = 10000,       # timeout after wake word
        alsa_device: str = "plughw:0,0",                # ALSA capture device (plug = SW resampling)
    ):
        self.endpoint = stt_endpoint
        self.stt_backend = stt_backend
        self.whisper_model_name = whisper_model
        self.samplerate = samplerate
        self.block_duration_ms = block_duration_ms
        self.silence_duration_ms = silence_duration_ms
        self.max_active_duration_ms = max_active_duration_ms
        self.alsa_device = alsa_device

        # ---- Audio backend selection ----
        self._audio_impl = "keyboard"  # will upgrade below

        # Try ALSA (arecord) first — works on Jetson without PortAudio
        if USE_ALSA:
            if self._arecord_available():
                self._audio_impl = "alsa"
                print("[MicSTT] Using ALSA backend (arecord)")
            else:
                # Try sounddevice (PortAudio)
                try:
                    import sounddevice as sd
                    self.sd = sd
                    self._audio_impl = "sounddevice"
                    print("[MicSTT] Using sounddevice backend")
                except ImportError:
                    print("[MicSTT] sounddevice not installed. pip install sounddevice")

        if self._audio_impl == "keyboard":
            print("[MicSTT] No audio backend available — falling back to keyboard input.")

        self._audio_queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: threading.Thread | None = None
        self._callback: Optional[Callable[[str], None]] = None
        self._on_wake: Optional[Callable[[], None]] = None

        # State machine
        self._mode: str = "IDLE"
        self._last_speech_time = 0.0
        self._voice_active = False
        self._active_start_time = 0.0
        self._block_samples = int(samplerate * block_duration_ms / 1000)
        self._stt_buffer: List[float] = []

        self._wake_word_detector: Optional[object] = None
        self._whisper_model = None
        self._whisper_loaded = False

        # VAD
        self._vad_threshold = 0.004    # lowered for quiet lavalier mic
        self._vad_hang_frames = 0
        self._vad_max_hang = 3

        # ALSA subprocess
        self._arecord_proc: Optional[subprocess.Popen] = None
        self._alsa_thread: threading.Thread | None = None

    # ── ALSA helpers ────────────────────────────────────

    def _arecord_available(self) -> bool:
        return subprocess.run(["which", "arecord"], capture_output=True).returncode == 0

    def _start_arecord(self) -> None:
        """Spawn arecord subprocess and pipe raw S16_LE samples."""
        cmd = [
            "arecord",
            "-D", self.alsa_device,
            "-f", "S16_LE",           # 16-bit signed little-endian
            "-r", str(self.samplerate),
            "-c", "1",                 # mono
            "-t", "raw",               # raw PCM, no WAV header
            "--buffer-size=2048",      # small buffer for low latency
            "-",                       # output to stdout
        ]
        try:
            self._arecord_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=4096,
            )
            print(f"[MicSTT] arecord started: device={self.alsa_device} sr={self.samplerate}Hz")
        except Exception as e:
            print(f"[MicSTT] arecord failed: {e}")
            self._audio_impl = "keyboard"
            return

        self._alsa_thread = threading.Thread(target=self._alsa_reader_loop, daemon=True)
        self._alsa_thread.start()

    def _alsa_reader_loop(self) -> None:
        """Read raw S16_LE from arecord stdout, enqueue float32 blocks."""
        if self._arecord_proc is None or self._arecord_proc.stdout is None:
            return

        chunk_bytes = self._block_samples * 2   # 2 bytes per S16 sample
        while self._running:
            raw = self._arecord_proc.stdout.read(chunk_bytes)
            if not raw:
                break
            # Pad if short (end of stream)
            if len(raw) < chunk_bytes:
                raw += b"\x00" * (chunk_bytes - len(raw))
            # Convert S16_LE → float32 [-1.0, +1.0]
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            self._audio_queue.put(samples.tolist())

    def _stop_arecord(self) -> None:
        if self._arecord_proc:
            self._arecord_proc.terminate()
            self._arecord_proc.wait(timeout=1)
            self._arecord_proc = None
        if self._alsa_thread:
            self._alsa_thread.join(timeout=1)
            self._alsa_thread = None

    # ── Whisper local STT ───────────────────────────────

    def _load_whisper(self):
        if self._whisper_loaded:
            return
        self._whisper_loaded = True
        try:
            import faster_whisper  # type: ignore[import]
            print(f"[MicSTT] Loading Whisper '{self.whisper_model_name}' — this may take 20–60s...")
            model = None
            for device in ("cuda", "cpu"):
                try:
                    model = faster_whisper.WhisperModel(
                        self.whisper_model_name,
                        device=device,
                        compute_type="int8",  # works on both cpu and cuda
                    )
                    print(f"[MicSTT] Whisper ready on {device}.")
                    break
                except Exception:
                    if device == "cuda":
                        print("[MicSTT] CUDA not available for Whisper, trying CPU...")
                    else:
                        raise
            self._whisper_model = model
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

    # ── Sounddevice fallback ────────────────────────────

    def _audio_callback_sd(self, indata, frames, time_info, status):
        if status:
            print(f"[MicSTT] Audio status: {status}")
        self._audio_queue.put(indata.copy().flatten().tolist())

    # ── Public API ─────────────────────────────────────

    def set_wake_word_detector(self, detector: object) -> None:
        self._wake_word_detector = detector

    def set_wake_callback(self, fn: Callable[[], None]) -> None:
        self._on_wake = fn

    # ── Main loop ───────────────────────────────────────

    def _process_loop(self) -> None:
        while self._running:
            if self._audio_impl in ("alsa", "sounddevice"):
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
        # Only skip if we literally have no audio backend (pure keyboard fallback)
        if self._audio_impl == "keyboard":
            return

        if self._wake_word_detector is None:
            # No wake word configured → always active
            self._mode = "ACTIVE"
            self._active_start_time = now
            self._stt_buffer = audio.tolist().copy()
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

    def _process_active(self, audio: np.ndarray, now: float) -> None:
        """In WAKE/ACTIVE: buffer audio, detect silence, then flush to STT."""
        self._stt_buffer.extend(audio.tolist())

        # VAD
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))

        if rms > self._vad_threshold:
            self._voice_active = True
            self._last_speech_time = now
            self._vad_hang_frames = 0
        else:
            self._vad_hang_frames += 1

        hang_silence = self._vad_hang_frames * (self.block_duration_ms / 1000.0)
        active_duration = now - self._active_start_time

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
        """Transcribe buffered audio, return recognized text."""
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
            print("[MicSTT] No STT configured — text captured but not transcribed.")

        if text:
            print(f"[MicSTT] Recognized: \"{text}\"")

        self._stt_buffer.clear()
        return text

    def _transcribe_endpoint(self, audio_np: np.ndarray) -> str:
        if not self.endpoint:
            return ""
        import struct
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
        print("[MicSTT] Returned to idle — waiting for wake word.")

    # ── Control ───────────────────────────────────────

    def start(self, on_transcript: Callable[[str], None]) -> None:
        self._callback = on_transcript
        self._running = True
        self._mode = "IDLE"
        self._stt_buffer.clear()

        if self._audio_impl == "alsa":
            self._start_arecord()
        elif self._audio_impl == "sounddevice":
            self._sd_stream = self.sd.RawInputStream(
                samplerate=self.samplerate,
                blocksize=self._block_samples,
                dtype="float32",
                channels=1,
                callback=self._audio_callback_sd,
            )
            self._sd_stream.start()
        else:
            print("[MicSTT] Keyboard mode — type to talk to Teela.")

        if self._audio_impl in ("alsa", "sounddevice"):
            backend_msg = (
                "whisper (local)" if self.stt_backend == "whisper"
                else (f"endpoint: {self.endpoint}" if self.endpoint else "⚠️ none")
            )
            print(f"[MicSTT] Mic stream started at {self.samplerate} Hz ({self._audio_impl})")
            print(f"[MicSTT] STT: {backend_msg}")
            print(f"[MicSTT] Say 'Hey Teela' to wake me!")

        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def force_active(self, duration_ms: int = 10000) -> None:
        self._mode = "ACTIVE"
        self._active_start_time = time.time()
        self._stt_buffer.clear()
        print("[MicSTT] Manual activation — listening...")

    def stop(self) -> None:
        self._running = False
        self._mode = "IDLE"
        if self._audio_impl == "alsa":
            self._stop_arecord()
        elif self._audio_impl == "sounddevice":
            if hasattr(self, "_sd_stream"):
                self._sd_stream.stop()
                self._sd_stream.close()
        if self._thread:
            self._thread.join(timeout=1.0)
        print("[MicSTT] Stopped.")
