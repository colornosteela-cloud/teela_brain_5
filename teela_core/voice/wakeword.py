"""
Wake Word Detection — "Hey Teela"

Supports multiple backends:
    - porcupine     → Picovoice, offline, fastest (default)
    - openwakeword  → ONNX, open source, slightly heavier
    - energy        → threshold-only fallback (always works)

When Teela hears her name, she emits a beep and transitions
from low-power idle to active listening.
"""

import time
from dataclasses import dataclass
from typing import Callable, Literal, Optional

import numpy as np


@dataclass
class WakeEvent:
    keyword: str
    confidence: float
    timestamp: float


class WakeWordDetector:
    """Listen for "Teela" or "Hey Teela" using configurable backend."""

    def __init__(
        self,
        backend: Literal["porcupine", "openwakeword", "energy"] = "porcupine",
        sensitivity: float = 0.7,
        access_key: Optional[str] = None,
    ):
        self.backend = backend
        self.sensitivity = sensitivity
        self.access_key = access_key or ""
        self._engine = None
        self._last_detection_time = 0.0
        self._cooldown_s = 2.0         # don't re-trigger immediately
        self._consecutive_loud = 0
        self._min_consecutive = 1      # how many loud blocks to trigger (500ms per block)

        # Energy gating — sounddevice returns float32 in [-1.0, +1.0]
        # 0.02 is a normal speaking voice at 50cm, 0.01 is quiet room
        # NOTE: this lavalier mic is quiet — threshold lowered
        self._energy_threshold = 0.006
        self._energy_bg = 0.0005
        self._energy_alpha = 0.98

        self._load_backend()

    # ── Backend Loading ──────────────────────────────────

    def _load_backend(self):
        if self.backend == "porcupine":
            self._load_porcupine()
        elif self.backend == "openwakeword":
            self._load_openwakeword()
        else:
            self._engine = None
            print("[WakeWord] Using energy-only fallback.")

    def _load_porcupine(self) -> bool:
        try:
            import pvporcupine  # type: ignore[import]
            kwargs: dict = {"keywords": ["teela"]}
            if self.access_key:
                kwargs["access_key"] = self.access_key
            self._engine = pvporcupine.create(**kwargs)
            print("[WakeWord] Porcupine loaded — listening for 'teela'.")
            return True
        except ImportError:
            print("[WakeWord] pvporcupine not installed. Using energy fallback.")
            self.backend = "energy"
            self._engine = None
            return False
        except Exception as e:
            print(f"[WakeWord] Porcupine init failed: {e}. Falling back to energy.")
            self.backend = "energy"
            self._engine = None
            return False

    def _load_openwakeword(self) -> bool:
        try:
            import openwakeword  # type: ignore[import]
            from pathlib import Path
            model_path = Path(__file__).parent / "models" / "teela.tflite"
            if not model_path.exists():
                generic = Path(__file__).parent / "models" / "hey_jarvis.tflite"
                if generic.exists():
                    model_path = generic
                else:
                    raise FileNotFoundError(
                        "No wake word model found. Run scripts/download_wake_models.py"
                    )
            self._engine = openwakeword.Model(str(model_path), inference_framework="tflite")
            self._oww_threshold = 0.5
            print(f"[WakeWord] OpenWakeWord loaded: {model_path.name}")
            return True
        except ImportError:
            print("[WakeWord] openwakeword not installed. Using energy fallback.")
            self.backend = "energy"
            self._engine = None
            return False
        except Exception as e:
            print(f"[WakeWord] OpenWakeWord init failed: {e}. Energy fallback.")
            self.backend = "energy"
            self._engine = None
            return False

    # ── Detection ───────────────────────────────────────

    def detect(self, audio_chunk: np.ndarray, timestamp: float) -> Optional[WakeEvent]:
        """Check if wake word is present in 16kHz mono float32 audio chunk.

        sounddevice returns float32 in [-1.0, +1.0] range.
        Normal speaking voice at 50cm:  RMS ≈ 0.015–0.04
        Quiet room noise:              RMS ≈ 0.001–0.003
        Loud shout/clap:               RMS ≈ 0.08–0.3
        """
        if timestamp - self._last_detection_time < self._cooldown_s:
            return None

        rms = float(np.sqrt(np.mean(audio_chunk.astype(np.float64) ** 2)))

        # Adaptive background: update during quiet periods only
        # This prevents the threshold from chasing speech energy upward
        if rms < self._energy_threshold:
            self._energy_bg = self._energy_alpha * self._energy_bg + (1 - self._energy_alpha) * rms
            self._consecutive_loud = 0
            return None

        # Above quiet floor — count consecutive loud blocks
        self._consecutive_loud += 1

        if self._consecutive_loud < self._min_consecutive:
            return None  # debounce single-block noise spikes

        if self.backend == "porcupine" and self._engine is not None:
            return self._detect_porcupine(audio_chunk, timestamp)
        elif self.backend == "openwakeword" and self._engine is not None:
            return self._detect_openwakeword(audio_chunk, timestamp)
        else:
            return self._detect_energy(audio_chunk, timestamp, rms)

    # ── Per-backend detection ────────────────────────────

    def _detect_porcupine(self, audio_chunk: np.ndarray, timestamp: float) -> Optional[WakeEvent]:
        # Porcupine expects int16 at 16kHz, frame-by-frame
        pcm_int16 = (audio_chunk * 32767).astype(np.int16)
        frame_len = self._engine.frame_length
        for i in range(0, len(pcm_int16) - frame_len + 1, frame_len):
            frame = pcm_int16[i : i + frame_len].tolist()
            keyword_index = self._engine.process(frame)
            if keyword_index >= 0:
                self._last_detection_time = timestamp
                return WakeEvent(keyword="teela", confidence=1.0, timestamp=timestamp)
        return None

    def _detect_openwakeword(self, audio_chunk: np.ndarray, timestamp: float) -> Optional[WakeEvent]:
        pcm_int16 = (audio_chunk * 32767).astype(np.int16)
        prediction = self._engine.predict(pcm_int16)
        if prediction >= self._oww_threshold:
            self._last_detection_time = timestamp
            return WakeEvent(keyword="teela", confidence=float(prediction), timestamp=timestamp)
        return None

    def _detect_energy(self, audio_chunk: np.ndarray, timestamp: float, rms: float) -> Optional[WakeEvent]:
        """Energy-only: loud enough = trigger wake.

        Thresholds for float32 audio [-1.0, +1.0]:
            ~0.01 = soft whisper
            ~0.02 = normal speaking voice
            ~0.05 = loud voice
            ~0.1  = shouting / clap
            ~0.3  = very loud / tapping mic
        """
        trigger_rms = 0.03  # reasonable speaking voice
        if rms > trigger_rms:
            self._last_detection_time = timestamp
            return WakeEvent(keyword="teela", confidence=0.3, timestamp=timestamp)
        return None

    # ── Utilities ─────────────────────────────────────

    def is_in_cooldown(self, now: float) -> bool:
        return (now - self._last_detection_time) < self._cooldown_s

    @property
    def is_listening(self) -> bool:
        return self._engine is not None or self.backend == "energy"

    def cleanup(self):
        if self.backend == "porcupine" and self._engine is not None:
            self._engine.delete()
            self._engine = None


# ── Self-test ───────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test wake word detection")
    parser.add_argument(
        "--backend", choices=["porcupine", "openwakeword", "energy"], default="energy"
    )
    parser.add_argument("--duration", type=int, default=10, help="Seconds to listen")
    parser.add_argument(
        "--rms", action="store_true", help="Print live RMS values for calibration"
    )
    args = parser.parse_args()

    detector = WakeWordDetector(backend=args.backend)
    print(f"Listening for 'Teela' ({args.backend}) — speak now...")

    try:
        import sounddevice as sd

        samplerate = 16000
        block_ms = 500
        chunk_size = int(samplerate * block_ms / 1000)
        blocks = int(args.duration * 1000 / block_ms)

        detected_count = 0
        for i in range(blocks):
            audio = sd.rec(chunk_size, samplerate=samplerate, channels=1, dtype="float32")
            sd.wait()
            flat = audio.flatten()
            now = time.time()
            event = detector.detect(flat, now)

            if args.rms:
                rms = float(np.sqrt(np.mean(flat.astype(np.float64) ** 2)))
                bars = min(40, int(rms * 400))
                bar = "█" * bars
                print(f"  [{i:02d}] RMS {rms:.4f} {bar}", flush=True)

            if event:
                detected_count += 1
                print(f"🔔 WAKE WORD DETECTED: '{event.keyword}' confidence={event.confidence:.2f}")

        print(f"\nDone. Detected {detected_count} wake word(s) in {args.duration}s.")
        if detected_count == 0:
            print("\n💡 Debugging tips:")
            print("  1. Check mic is working:  arecord -d 3 test.wav && aplay test.wav")
            print("  2. Run with --rms to see live levels:  python3 -m teela_core.voice.wakeword --rms")
            print("  3. Speak closer to the mic, or raise your voice.")
            print("  4. If RMS values are all < 0.005, your mic may not be capturing audio.")
    except ImportError:
        print("sounddevice not installed. Run: pip install sounddevice")
