#!/usr/bin/env python3
"""Teela Runtime Mind — Main Loop for Current Hardware

Works with ONLY these actuators:
    - Cameras    (eyes)
    - Microphone (ears)
    - Neck pan/tilt (head movement = all expression)

Everything else (legs, arms, e-skin) is gracefully stubbed until installed.

Usage:
    export KIMI_API_KEY="..."
    python3 -m scripts.conversation_loop --config config.yaml

Key bindings (from keyboard if no microphone):
    Ctrl+C → graceful shutdown
"""

import argparse
import base64
import io
import json
import math
import queue
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import yaml

from teela_core.perception.camera import StereoCamera
from teela_core.perception.scene_understanding import SceneUnderstanding
from teela_core.gestures.pointing_integration import PointingSceneIntegrator
from teela_core.comms.serial_link import SerialLink
from teela_core.comms.cloud_bridge import CloudBridge
from teela_core.voice.wakeword import WakeWordDetector
from teela_core.voice.stt_mic import MicSTT

# Try Chatterbox first, fallback to SpeakerTTS
try:
    from teela_core.voice.chatterbox_tts import ChatterboxSpeaker as SpeakerTTS
    _CHATTERBOX_AVAILABLE = True
    print("[Import] ChatterboxSpeaker loaded (emotional voice cloning)")
except ImportError:
    from teela_core.voice.tts_speaker import SpeakerTTS
    _CHATTERBOX_AVAILABLE = False
    print("[Import] Fallback to SpeakerTTS (cloud/robotic voices)")

from teela_core.expression.neck_expression import NeckExpression, NeckCommand

# Cognitive modules (available regardless of actuators)
from teela_core.cognitive.emotion import EmotionEngine, EmotionalEvent
from teela_core.cognitive.memory import MemoryStore
from teela_core.cognitive.personality import PersonalityEngine
from teela_core.cognitive.social import SocialAwareness
from teela_core.cognitive.identity import SelfModel, BodyState


def sigint_handler(signum, frame):
    print("\n[Runtime] Shutdown signal received. Stopping motors...")
    TeelaRuntimeMind._instance.shutdown()
    sys.exit(0)


signal.signal(signal.SIGINT, sigint_handler)


class TeelaRuntimeMind:
    """The brain as it exists TODAY — eyes (one or two cameras), ears, neck, cloud."""

    _instance: Optional["TeelaRuntimeMind"] = None

    def __init__(self, config_path: str = "config.yaml"):
        TeelaRuntimeMind._instance = self

        # ── Load config ──────────────────────────────────────
        config = {}
        p = Path(config_path)
        if p.exists():
            config = yaml.safe_load(p.read_text())
        self.config = config
        hw = config.get("hardware", {})
        self.cap = config.get("robot", {}).get("capabilities", {})

        # ── Hardware: Camera ─────────────────────────────────
        self.capabilities = {
            "eyes": self.cap.get("eyes", True),
            "ears": self.cap.get("ears", True),
            "neck": self.cap.get("neck", True),
            "walking": self.cap.get("walking", False),
            "e_skin": self.cap.get("e_skin", False),
        }

        self.camera: Optional[StereoCamera] = None
        if self.capabilities["eyes"]:
            cam_cfg = hw.get("camera", {})
            self.camera = StereoCamera(
                primary_device=cam_cfg.get("primary_index", 0),
                secondary_device=cam_cfg.get("secondary_index"),
                width=cam_cfg.get("width", 640),
                height=cam_cfg.get("height", 480),
                fps=cam_cfg.get("fps", 15),
            )

        self.scene = SceneUnderstanding()
        self.pointing = PointingSceneIntegrator()

        # ── Hardware: Serial / Neck ────────────────────────
        self.serial = SerialLink(
            port=hw.get("serial", {}).get("port", "/dev/ttyACM0"),
            baud=hw.get("serial", {}).get("baud", 921600),
            on_status=self._on_telemetry,
        )

        # ── Hardware: Microphone / STT ────────────────
        self.mic = None
        self.wake_detector = None
        if self.capabilities["ears"]:
            mic_cfg = hw.get("microphone", {})
            voice_cfg = config.get("voice", {})

            # Choose STT backend
            stt_endpoint = mic_cfg.get("stt_endpoint")
            if mic_cfg.get("stt_local", True) and not stt_endpoint:
                stt_backend = "whisper"  # local GPU STT
            else:
                stt_backend = "endpoint"

            self.mic = MicSTT(
                stt_endpoint=stt_endpoint,
                stt_backend=stt_backend,
                whisper_model=mic_cfg.get("stt_model", "base"),
                samplerate=mic_cfg.get("samplerate", 16000),
            )
            self._pending_transcript: Optional[str] = None

            # Wake word
            if voice_cfg.get("wakeword_enabled", True):
                from teela_core.voice.wakeword import WakeWordDetector
                self.wake_detector = WakeWordDetector(
                    backend=voice_cfg.get("wakeword_type", "energy"),
                    sensitivity=voice_cfg.get("wakeword_sensitivity", 0.7),
                )
                self.mic.set_wake_word_detector(self.wake_detector)
                self.mic.set_wake_callback(self._on_wake_word)

        # ── Hardware: Speaker / TTS ────────────────────
        speak_cfg = hw.get("speaker", {})
        voice_cfg = config.get("voice", {})
        tts_engine = voice_cfg.get("tts_engine", "auto")
        
        # Auto-detect best TTS engine
        if tts_engine == "auto":
            if _CHATTERBOX_AVAILABLE:
                tts_engine = "chatterbox"
                print("[TTS] Using Chatterbox-Turbo (Jade's cloned voice with 15 emotions)")
            else:
                tts_engine = "edge_tts"
                print("[TTS] Using Edge TTS fallback")
        
        # Configure SpeakerTTS
        if tts_engine == "chatterbox":
            self.speaker = SpeakerTTS(
                mode="chatterbox",
                voices_dir=voice_cfg.get("voices_dir", "voices/jade_cloned"),
                device="cpu",
                output_device=speak_cfg.get("output_device"),
            )
        else:
            self.speaker = SpeakerTTS(
                mode=speak_cfg.get("mode", "stdout"),
                edge_tts_voice=voice_cfg.get("tts_voice", speak_cfg.get("edge_tts_voice", "en-US-JennyNeural")),
                output_device=speak_cfg.get("output_device"),
            )
        if speak_cfg.get("play_beep", True):
            self.speaker.play_beep(880, 200)

        # ── Cloud LLM ────────────────────────────────────
        self.cloud = CloudBridge(config.get("cloud", {}))

        # ── Cognitive ────────────────────────────────────
        self.emotion = EmotionEngine()
        self.memory = MemoryStore()
        self.personality = PersonalityEngine()
        self.social = SocialAwareness()
        self.identity = SelfModel()
        self.identity.update_body_state(BodyState())

        # ── Expression ───────────────────────────────────
        self.neck = NeckExpression()
        self._current_neck_cmd: Optional[NeckCommand] = None

        # ── State ─────────────────────────────────────────
        self._running = False
        self._last_tick = time.time()
        self._last_cloud_reply = ""
        self._last_scene_time = 0.0
        self._scene_state = None

        self._tick_count = 0

    # ── Lifecycle ────────────────────────────────────────
    def startup(self) -> bool:
        print("=" * 50)
        print("Teela Runtime Mind — Starting...")
        print("=" * 50)

        # Camera
        if self.camera:
            self.camera.start()
            print("[Startup] Camera capture thread started.")

        # Serial
        if not self.serial.connect():
            print("[Startup] WARNING: Serial not connected. Neck will not move until Teensy is plugged in.")
            print("           You can still run the brain — just type 'connect' later.")
        else:
            time.sleep(0.5)
            self.serial.send_ping()
            print("[Startup] Serial connected. Teensy ping sent.")

        # Mic
        if self.mic:
            self.mic.start(on_transcript=self._on_transcript)
            print("[Startup] Microphone listening (or keyboard fallback).")

        # Identity
        self.identity.update_body_state(BodyState(name="Teela", feelings="ready and curious"))
        self.emotion.update(EmotionalEvent(
            event_type="startup", valence_impact=0.3, arousal_impact=0.2,
            dominance_impact=0.0, reason="I'm waking up."
        ))
        self.speaker.speak("Hello. I'm Teela. My eyes are open and I'm listening.")

        print("\n✅ Teela is LIVE.")
        print("   Eyes:    " + ("OK" if self.camera else "OFF"))
        print("   Ears:    " + ("OK" if self.mic else "OFF"))
        print("   Neck:    " + ("OK" if self.serial._connected else "OFF (Teensy not detected)"))
        print("   Cloud:   " + ("Kimi API" if self.cloud.api_key else "LOCAL / no key"))
        print()
        return True

    def shutdown(self) -> None:
        self._running = False
        if self.camera:
            self.camera.stop()
        if self.mic:
            self.mic.stop()
        self.serial.disconnect()
        print("[Shutdown] Teela is asleep.")

    # ── Main Loop ────────────────────────────────────────
    def run(self) -> None:
        self._running = True
        tick_hz = 10.0  # 10 Hz main cognition

        # Start keyboard listener thread (so you can type even when mic is active)
        self._keyboard_queue: queue.Queue = queue.Queue()
        def _keyboard_reader():
            while self._running:
                try:
                    line = input("[TYPE] ")
                    if line.strip():
                        self._keyboard_queue.put(line.strip())
                except (EOFError, KeyboardInterrupt):
                    time.sleep(0.3)
        _kbd_thread = threading.Thread(target=_keyboard_reader, daemon=True)
        _kbd_thread.start()

        while self._running:
            try:
                self.tick()
                self._tick_count += 1
                time.sleep(1.0 / tick_hz)
            except KeyboardInterrupt:
                break

    def tick(self) -> None:
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now

        # ── 1. PERCEPTION (eyes) ───────────────────────────
        frame = None
        if self.camera:
            frame = self.camera.get_left_frame()  # primary (left) eye — face tracking / pointing

        scene_description = "I see nothing."
        pointed_object = None
        person_positions = []

        if frame is not None:
            self._scene_state = self.scene.process_frame(frame)
            self._scene_state = self.pointing.update_scene_state(frame, self._scene_state)
            scene_description = self._scene_state.json_description or "unknown scene"

            # Extract pointing
            if self._scene_state.pointed_object:
                pointed_object = self._scene_state.pointed_object
            # Extract person positions
            for det in getattr(self._scene_state, "humans", {}).get("detections", []):
                if "position" in det:
                    person_positions.append(det["position"])

            self._last_scene_time = now
            # save
            self._scene_state.to_json(Path(self.config.get("perception", {}).get("output_path", "/tmp/scene_state.json")))

        # ── 2. COGNITION ─────────────────────────────────
        emotion_state = self.emotion.update()
        emotion_dict = emotion_state.to_dict()

        # Pull from keyboard thread if there's typed input
        if hasattr(self, "_keyboard_queue"):
            while not self._keyboard_queue.empty():
                typed = self._keyboard_queue.get_nowait()
                if typed:
                    print(f"\n[You ⌨️ ]  {typed}")
                    self._pending_transcript = typed

        # Decide if we should speak this tick
        should_speak = bool(self._pending_transcript)
        user_text = self._pending_transcript or ""

        # ── 3. CLOUD REASONING (if user spoke or new scene data) ──
        cloud_reply = ""
        if should_speak or self._tick_count % 30 == 0:  # idle check every ~3s
            # Compose context for the LLM
            context_parts = []
            context_parts.append(f"Current emotion: {emotion_state.describe()}")
            context_parts.append(f"Scene: {scene_description}")
            if pointed_object:
                context_parts.append(f"Person is pointing at: {pointed_object}")
            context_parts.append(f"My neck posture (pan, tilt): {self._current_neck_cmd or 'neutral'}")
            context_parts.append(f"My identity: {self.identity.body.name}. {self.identity.body.feelings}")

            extra_system = "\n".join(context_parts)

            # Encode last frame as base64 for vision if we have camera
            images = []
            if frame is not None and self.capabilities["eyes"]:
                _, buf = cv2.imencode(".jpg", frame)
                images.append([base64.b64encode(buf).decode()])

            if should_speak:
                prompt = f"The person just said: '{user_text}'. What do you say or do?"
            else:
                prompt = "Take in the scene and your emotions. Do you want to say anything or look at something?"

            resp = self.cloud.chat(
                prompt,
                extra_system=extra_system,
                images=images[0] if images else None,
            )
            cloud_reply = resp.text
            self._last_cloud_reply = cloud_reply
            self._pending_transcript = None

        # ── 4. SPEAK ──────────────────────────────────────
        if cloud_reply and cloud_reply.strip():
            # Parse emotional voice tags: [EMOTION: happy] (etc.)
            emotion = None
            speak_text = cloud_reply.strip()
            import re
            emo_match = re.match(r'\[\s*EMOTION\s*:\s*(\w+)\s*\]\s*(.*)', speak_text, re.IGNORECASE)
            if emo_match:
                emotion = emo_match.group(1).lower().strip()
                speak_text = emo_match.group(2).strip()
                print(f"\n[Teela 🗣️ 💝 {emotion}]  {speak_text}")
            else:
                print(f"\n[Teela 🗣️ ]  {speak_text}")
            self.speaker.speak(speak_text, emotion=emotion)

        # ── 5. EXPRESSION (neck) ──────────────────────────
        # Determine target person to look at
        speaker_position = person_positions[0] if person_positions else None
        # If user just spoke, look toward first detected person
        eskin_face_touched = False  # will be wired when e-skin is installed

        neck_cmd = self.neck.update(
            emotion=emotion_dict,
            speaker_position=speaker_position,
            pointed_position=(pointed_object.get("position") if pointed_object else None),
            mode="conversation" if should_speak else "idle",
            eskin_face_touched=eskin_face_touched,
        )
        self._current_neck_cmd = neck_cmd

        # Send to Teensy
        if self.serial._connected:
            self.serial.send_neck(
                neck_cmd.pan_deg,
                neck_cmd.tilt_deg,
                speed_dps=neck_cmd.speed_dps,
            )

        # ── 6. MEMORY SAVE (periodically) ─────────────────
        if self._tick_count % 100 == 0:  # every 10s
            self.memory.save()
            if self.mic:
                print("[Mic] Type 'bye' to exit, or anything else to talk to Teela.")

    # ── Event Callbacks ──────────────────────────────────
    def _on_wake_word(self) -> None:
        """Called by MicSTT when 'Hey Teela' is detected."""
        print("\n🔔 Wake word detected! Teela is now listening...")
        self.speaker.play_beep(880, 200)
        # Alert expression: look forward, slight tilt up
        self._current_neck_cmd = NeckCommand(
            pan_deg=0.0, tilt_deg=5.0, speed_dps=80.0,
            hold_s=0.5, reason="wake_word_alert"
        )
        if self.serial._connected:
            self.serial.send_neck(
                self._current_neck_cmd.pan_deg,
                self._current_neck_cmd.tilt_deg,
                speed_dps=self._current_neck_cmd.speed_dps,
            )

    def _on_transcript(self, text: str) -> None:
        """Called by MicSTT when speech is recognized."""
        print(f"\n[You 🎤]  {text}")
        self._pending_transcript = text

        # Emotion: hearing a voice
        self.emotion.update(EmotionalEvent(
            event_type="hear_speech", valence_impact=0.1, arousal_impact=0.2,
            dominance_impact=0.0, reason=f"Person said: {text}"
        ))

    def _on_telemetry(self, status: dict) -> None:
        """Called by SerialLink when STATUS arrives from Teensy."""
        # In future, parse IMU data, servo temps, etc.
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Teela Runtime Mind")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    mind = TeelaRuntimeMind(config_path=args.config)
    if mind.startup():
        mind.run()
    else:
        print("Startup failed.")
