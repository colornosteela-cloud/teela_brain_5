#!/usr/bin/env python3
"""Teela Conversation Loop

The main cognitive-integration script. This ties together ALL modules:
    - Perception (camera) → scene_state
    - Pointing detection
    - STT (listening)
    - Emotion engine
    - Memory (people, episodes, facts)
    - Personality
    - Social awareness
    - Cloud reasoning (LLM)
    - TTS (speaking)
    - Non-verbal expression
    - Proactive behavior
    - Idle behavior
    - Reflex layer
    - Teensy serial control

Usage:
    python3 -m scripts.conversation_loop --config config.yaml
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import numpy as np

# Core systems
from teela_core.perception.scene_understanding import SceneUnderstanding
from teela_core.gestures.pointing_integration import PointingSceneIntegrator
from teela_core.reflex.reflex_layer import ReflexLayer
from teela_core.comms.serial_link import SerialLink
from teela_core.comms.cloud_bridge import CloudBridge

# Cognitive
from teela_core.cognitive.emotion import EmotionEngine, EmotionalEvent
from teela_core.cognitive.memory import MemoryStore, Episode
from teela_core.cognitive.personality import PersonalityEngine
from teela_core.cognitive.social import SocialAwareness
from teela_core.cognitive.identity import SelfModel

# Expression
from teela_core.expression.nonverbal import NonVerbalExpression
from teela_core.expression.prosody import ProsodyEngine

# Behavior
from teela_core.behavior.proactive import ProactiveBehavior
from teela_core.behavior.idle import IdleBehavior
from teela_core.behavior.curiosity import CuriosityDrive

# Voice
from teela_core.voice.stt import STTPipeline
from teela_core.voice.tts import TTSEngine


class TeelaMind:
    """Central integration: all cognitive subsystems wired together."""

    def __init__(self, config_path: str = "config.yaml"):
        # Config
        import yaml
        self.config = yaml.safe_load(Path(config_path).read_text()) if Path(config_path).exists() else {}

        # Systems
        self.scene = SceneUnderstanding()
        self.pointing = PointingSceneIntegrator()
        self.reflex = ReflexLayer()
        self.serial = SerialLink(port=self.config.get("hardware", {}).get("serial", {}).get("port", "/dev/ttyACM0"))
        self.cloud = CloudBridge(uri=self.config.get("cloud", {}).get("websocket_uri", "ws://localhost:8080/teela"))
        
        self.emotion = EmotionEngine()
        self.memory = MemoryStore()
        self.personality = PersonalityEngine()
        self.social = SocialAwareness()
        self.identity = SelfModel()
        
        self.expression = NonVerbalExpression()
        self.prosody = ProsodyEngine()
        
        self.proactive = ProactiveBehavior(self.personality.profile.to_dict(), {}, self.memory, self.social)
        self.idle = IdleBehavior()
        self.curiosity = CuriosityDrive()
        
        self.stt = STTPipeline()
        self.tts = TTSEngine()

        self._running = False
        self._last_tick = time.time()

    def tick(self) -> None:
        """Main cognitive loop — call at ~10 Hz."""
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now

        # 1. PERCEPTION
        frame = self.scene.capture()
        if frame is not None:
            scene_state = self.scene.process_frame(frame)
            scene_state = self.pointing.update_scene_state(frame, scene_state)

            # 2. REFLEX (safety)
            # sensor_readings = ...  # from Teensy or direct
            # reflex_cmd = self.reflex.evaluate(sensor_readings)
            # if reflex_cmd.cmd != "RESUME":
            #     self._handle_reflex(reflex_cmd)

            # 3. SOCIAL + MEMORY
            # Update who's present, conversation state
            self.social.update_presence([])  # TODO: person detections from scene
            social_events = self.social.get_social_events()
            for event in social_events:
                self._handle_social_event(event)

            # 4. EMOTION
            emotion_state = self.emotion.update()
            
            # Emotions colored by personality
            emotion_dict = emotion_state.to_dict()
            emotion_state_dict = self.personality.modulate_emotion(emotion_dict)

            # 5. PROACTIVE BEHAVIOR
            action = self.proactive.tick()
            if action:
                self._execute_action(action)

            # 6. IDLE (if truly idle)
            if self.social.interaction.mode == "idle" and frame is not None:
                idle_state = self.idle.tick(dt, emotion_dict)
                # Send idle expression commands to Teensy / face module

            # 7. EXPRESSION
            expression_state = self.expression.update(emotion_dict, {"mode": self.social.interaction.mode})

            # 8. CURIOSTY
            curiosity_state = self.curiosity.update(
                current_position=scene_state.self_pose[:3],
                detected_objects=[],  # from scene_state.objects
            )

            # 9. SCENE STATE enrichment
            scene_state.metadata.update({
                "emotional_state": emotion_dict,
                "personality_seed": self.personality.get_voice_persona(),
                "idle_state": vars(idle_state) if self.social.interaction.mode == "idle" else None,
                "proactive_action": None if not action else vars(action),
            })

            # Write enriched scene_state
            scene_state.to_json(Path(self.config.get("perception", {}).get("output_path", "/tmp/scene_state.json")))

    def _handle_social_event(self, event: dict) -> None:
        """React to social events with emotions and actions."""
        if event["type"] == "person_entered":
            self.emotion.update(EmotionalEvent.event_greet(event["name"]))
            self.memory.save()
        elif event["type"] == "person_pointing":
            self.emotion.update(EmotionalEvent(
                event_type="pointing",
                valence_impact=0.2,
                arousal_impact=0.1,
                dominance_impact=0.0,
                reason="Person is pointing at something",
            ))
        elif event["type"] == "turn_change":
            self.social.interaction.current_speaker = event["new_speaker"]

    def _execute_action(self, action) -> None:
        """Execute a proposed action."""
        if action.action_type == "speak":
            text = action.parameters.get("text", "")
            emotion_dict = self.emotion.state.to_dict()
            prosody_params = self.prosody.compute_speech_params(emotion_dict)
            marked_text = self.prosody.inject_prosody_markers(text, emotion_dict)
            audio = self.tts.speak(marked_text, prosody_params)
            # Play audio via ALSA / PyAudio
        elif action.action_type == "move":
            x = action.parameters.get("x", 0)
            y = action.parameters.get("y", 0)
            self.serial.send_target(x, y, 0, 0.3, "walk")

    def _handle_reflex(self, cmd) -> None:
        if cmd.cmd == "HALT":
            self.serial.send_halt()
        elif cmd.cmd == "EMERGENCY_PARK":
            self.serial.send_emergency_park()

    def run(self) -> None:
        self._running = True
        print("Teela mind is awake.")
        while self._running:
            try:
                self.tick()
                time.sleep(0.05)  # 20 Hz cognition
            except KeyboardInterrupt:
                self._running = False
                print("Teela is going to sleep...")
                self.memory.save()
                self.personality.save()


def main():
    parser = argparse.ArgumentParser(description="Teela Conversation Loop")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--once", action="store_true", help="Run one tick and exit")
    args = parser.parse_args()

    mind = TeelaMind(config_path=args.config)
    if args.once:
        mind.tick()
    else:
        mind.run()


if __name__ == "__main__":
    main()
