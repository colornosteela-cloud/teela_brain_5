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
        self._cooldown_s = 2.0  # don't re-trigger immediately

        # RMS energy parameters (used by energy backend AND as VAD gate)
        self._energy_threshold = 0.015
        self._energy_alpha = 0.95  # exponential moving average factor
        self._energy_bg = 0.0

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
            # Porcupine v3.x uses access_key; v2.x used keyword_paths
            # We support both.
            kwargs = {"keywords": ["teela"]}
            if self.access_key:
                kwargs["access_key"] = self.access_key
            else:
                # Without access_key, try keyword file path (v2 style)
                from pathlib import Path
                keyword_path = Path(__file__).parent / "models" / "teela_wake.ppn"
                if keyword_path.exists():
                    kwargs = {"keyword_paths": [str(keyword_path)]}
            self._engine = pvporcupine.create(**kwargs)
            print("[WakeWord] Porcupine loaded — listening for 'teela'.")
            return True
        except ImportError:
            print("[WakeWord] pvporcupine not installed. Trying openwakeword...")
            self.backend = "openwakeword"
            return self._load_openwakeword()
        except Exception as e:
            print(f"[WakeWord] Porcupine init failed: {e}. Falling back to energy.")
            self.backend = "energy"
            self._engine = None
            return False

    def _load_openwakeword(self) -> bool:
        try:
            import openwakeword  # type: ignore[import]
            # Pre-trained models (download from openwakeword repo)
            from pathlib import Path
            model_path = Path(__file__).parent / "models" / "teela.tflite"
            if not model_path.exists():
                # Use generic "hey jarvis" model as placeholder or energy
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
        """Check if wake word is present in 16kHz mono float32 audio chunk."""
        if timestamp - self._last_detection_time < self._cooldown_s:
            return None

        # Adaptive energy gate: ignore if too quiet (reduces false positives)
        self._update_energy_gate(audio_chunk)
        if self._energy_bg < self._energy_threshold:
            return None

        if self.backend == "porcupine" and self._engine is not None:
            return self._detect_porcupine(audio_chunk, timestamp)
        elif self.backend == "openwakeword" and self._engine is not None:
            return self._detect_openwakeword(audio_chunk, timestamp)
        else:
            return self._detect_energy(audio_chunk, timestamp)

    def _update_energy_gate(self, audio_chunk: np.ndarray):
        """Track background RMS to gate detections."""
        energy = np.sqrt(np.mean(audio_chunk.astype(np.float64) ** 2))
        if self._energy_bg == 0.0:
            self._energy_bg = energy
        else:
            self._energy_bg = self._energy_alpha * self._energy_bg + (1 - self._energy_alpha) * energy

    def _detect_porcupine(self, audio_chunk: np.ndarray, timestamp: float) -> Optional[WakeEvent]:
        import pvporcupine
        # Porcupine expects int16 at 16kHz
        pcm_int16 = (audio_chunk * 32767).astype(np.int16)
        # Process in Porcupine frame sizes (512 samples)
        frame_len = self._engine.frame_length
        for i in range(0, len(pcm_int16) - frame_len + 1, frame_len):
            frame = pcm_int16[i : i + frame_len].tolist()
            keyword_index = self._engine.process(frame)
            if keyword_index >= 0:
                self._last_detection_time = timestamp
                return WakeEvent(
                    keyword="teela",
                    confidence=1.0,
                    timestamp=timestamp,
                )
        return None

    def _detect_openwakeword(self, audio_chunk: np.ndarray, timestamp: float) -> Optional[WakeEvent]:
        # OpenWakeWord takes int16 at 16kHz
        pcm_int16 = (audio_chunk * 32767).astype(np.int16)
        prediction = self._engine.predict(pcm_int16)
        if prediction >= self._oww_threshold:
            self._last_detection_time = timestamp
            return WakeEvent(
                keyword="teela",
                confidence=float(prediction),
                timestamp=timestamp,
            )
        return None

    def _detect_energy(self, audio_chunk: np.ndarray, timestamp: float) -> Optional[WakeEvent]:
        """Energy-only: loud sound after quiet = possible wake."""
        energy = np.sqrt(np.mean(audio_chunk.astype(np.float64) ** 2))
        if energy > 0.1:  # loud threshold
            self._last_detection_time = timestamp
            return WakeEvent(
                keyword="teela",
                confidence=0.3,
                timestamp=timestamp,
            )
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test wake word detection")
    parser.add_argument("--backend", choices=["porcupine", "openwakeword", "energy"], default="energy")
    parser.add_argument("--duration", type=int, default=10, help="Seconds to listen")
    args = parser.parse_args()

    detector = WakeWordDetector(backend=args.backend)
    print(f"Listening for 'Teela' ({args.backend}) — speak now...")

    try:
        import sounddevice as sd
        samplerate = 16000
        duration = args.duration
        chunk_size = int(samplerate * 0.5)  # 500ms blocks

        for _ in range(int(duration / 0.5)):
            audio = sd.rec(chunk_size, samplerate=samplerate, channels=1, dtype="float32")
            sd.wait()
            event = detector.detect(audio.flatten(), time.time())
            if event:
                print(f"🔔 WAKE WORD DETECTED: {event.keyword} @ confidence={event.confidence:.2f}")
    except ImportError:
        print("sounddevice not installed. Run: pip install sounddevice")
