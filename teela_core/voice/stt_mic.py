"""Real microphone STT for Jetson.

Opens an ALSA mic stream using sounddevice, sends chunks to a Whisper server
or cloud API. Falls back to keyboard input for testing.
"""

import json
import queue
import threading
import time
from typing import Callable, List, Optional


class MicSTT:
    """Capture audio from mic, send to STT endpoint, receive transcripts.

    If `sounddevice` or speech backends are not installed, falls back
    to keyboard input (so Teela is still usable).
    """

    def __init__(
        self,
        stt_endpoint: Optional[str] = None,  # e.g. "http://jetson:8000/transcribe"
        samplerate: int = 16000,
        block_duration_ms: int = 1000,
        silence_duration_ms: int = 1500,
    ):
        self.endpoint = stt_endpoint
        self.samplerate = samplerate
        self.block_duration_ms = block_duration_ms
        self.silence_duration_ms = silence_duration_ms

        self._has_sounddevice = False
        try:
            import sounddevice as sd
            self._has_sounddevice = True
            self.sd = sd
            self._audio_queue: queue.Queue = queue.Queue()
        except ImportError:
            print("[MicSTT] sounddevice not installed. Install with: pip install sounddevice")
            print("[MicSTT] Falling back to keyboard input.")

        self._running = False
        self._thread: threading.Thread | None = None
        self._callback: Optional[Callable[[str], None]] = None

        self._accumulated_audio: List[float] = []
        self._last_speech_time = 0.0
        self._voice_active = False

    def _audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice stream every block."""
        if status:
            print(f"[MicSTT] Audio status: {status}")
        self._audio_queue.put(indata.copy().flatten().tolist())

    def _process_loop(self) -> None:
        import struct, urllib.request
        while self._running:
            if self._has_sounddevice:
                try:
                    block = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                self._handle_audio_block(block)
            else:
                # Fallback: read from stdin for testing
                try:
                    line = input("[YOU] ")
                    if line.strip() and self._callback:
                        self._callback(line.strip())
                except EOFError:
                    time.sleep(0.5)

    def _handle_audio_block(self, samples: List[float]) -> None:
        """VAD + STT logic."""
        self._accumulated_audio.extend(samples)

        # RMS energy check for voice activity
        if len(samples) == 0:
            return
        rms = (sum(x * x for x in samples) / len(samples)) ** 0.5
        threshold = 0.01  # adjust for environment
        now = time.time()

        if rms > threshold:
            self._voice_active = True
            self._last_speech_time = now

        silence_duration = now - self._last_speech_time

        # If silence after speech, flush accumulated audio to STT
        if self._voice_active and silence_duration > self.silence_duration_ms / 1000.0:
            self._flush_stt()

    def _flush_stt(self) -> None:
        if not self._accumulated_audio:
            return

        # Send to endpoint (stub: local Whisper server)
        if self.endpoint:
            import struct, urllib.request
            try:
                pcm = struct.pack("f" * len(self._accumulated_audio), *self._accumulated_audio)
                req = urllib.request.Request(
                    self.endpoint,
                    data=pcm,
                    headers={"Content-Type": "audio/raw", "X-SampleRate": str(self.samplerate)},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    result = json.loads(resp.read().decode())
                    text = result.get("text", "").strip()
                    if text and self._callback:
                        self._callback(text)
            except Exception as e:
                print(f"[MicSTT] STT error: {e}")
        else:
            # No endpoint: just report length for debugging
            dur = len(self._accumulated_audio) / self.samplerate
            print(f"[MicSTT] Captured {dur:.1f}s of speech (no endpoint configured)")

        self._accumulated_audio.clear()
        self._voice_active = False

    def start(self, on_transcript: Callable[[str], None]) -> None:
        self._callback = on_transcript
        self._running = True

        if self._has_sounddevice:
            # Start sounddevice input stream
            self._stream = self.sd.RawInputStream(
                samplerate=self.samplerate,
                blocksize=int(self.samplerate * self.block_duration_ms / 1000),
                dtype="float32",
                channels=1,
                callback=self._audio_callback,
            )
            self._stream.start()
            print(f"[MicSTT] Mic stream started at {self.samplerate} Hz")
        else:
            print("[MicSTT] No mic backend — type your input below.")

        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._has_sounddevice:
            if hasattr(self, "_stream"):
                self._stream.stop()
                self._stream.close()
        if self._thread:
            self._thread.join(timeout=1.0)

    def get_voice_active(self) -> bool:
        return self._voice_active
