#!/usr/bin/env python3
"""Emotion & Expression Demo (Neck-Only Edition)

Shows Teela's emotional states mapped to neck pan/tilt motion.
Useful for calibration and testing the neck expression pipeline.

Usage:
    python3 -m scripts.emote_demo
"""

import time

from teela_core.cognitive.emotion import EmotionEngine, EmotionalEvent
from teela_core.expression.neck_expression import NeckExpression
from teela_core.expression.prosody import ProsodyEngine


def demo():
    emotion = EmotionEngine()
    neck = NeckExpression()
    prosody = ProsodyEngine()

    scenarios = [
        ("Neutral/default state", None),
        ("Happy (user praised)", EmotionalEvent.event_praised()),
        ("Surprised (sudden loud noise)", EmotionalEvent(
            event_type="loud_noise", valence_impact=-0.1, arousal_impact=0.7, dominance_impact=0.0, reason="Loud noise"
        )),
        ("Sad (user leaving)", EmotionalEvent.event_person_left("Roni")),
        ("Curious (novel object)", EmotionalEvent.event_novel_object("blue_ball")),
        ("Cautious (obstacle close)", EmotionalEvent.event_obstacle_close(0.3)),
        ("Scolded (user upset)", EmotionalEvent.event_scolded()),
        ("Returning to calm", None),
    ]

    print("=== Teela Emotion & Neck Expression Demo ===\n")
    print("With Teensy connected, run: python3 -m scripts.conversation_loop")
    print("This demo shows how emotions map to pan/tilt servo targets.\n")

    for label, event in scenarios:
        print(f"--- {label} ---")
        if event:
            emotion.update(event)
        else:
            emotion = EmotionEngine()  # reset to neutral

        state = emotion.state
        neck_cmd = neck.update(
            emotion=state.to_dict(),
            speaker_position=None,
            mode="idle",
        )
        prosody_params = prosody.compute_speech_params(state.to_dict())

        print(f"  Emotion:  {state.describe()}")
        print(f"  Neck:     pan={neck_cmd.pan_deg:+6.1f}° tilt={neck_cmd.tilt_deg:+6.1f}° speed={neck_cmd.speed_dps:.0f}°/s")
        print(f"  Prosody:  {prosody_params}")
        print()
        time.sleep(1.5)

    print("=== Demo complete ===")


if __name__ == "__main__":
    demo()
