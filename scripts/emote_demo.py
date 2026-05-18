#!/usr/bin/env python3
"""Emotion & Expression Demo

Shows all of Teela's emotional states and non-verbal expressions in sequence.
Useful for calibration and testing the expression pipeline.

Usage:
    python3 -m scripts.emote_demo
"""

import time
import json

from teela_core.cognitive.emotion import EmotionEngine, EmotionalEvent
from teela_core.expression.nonverbal import NonVerbalExpression
from teela_core.expression.prosody import ProsodyEngine


def demo():
    emotion = EmotionEngine()
    expression = NonVerbalExpression()
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

    print("=== Teela Emotion & Expression Demo ===\\n")
    
    for label, event in scenarios:
        print(f"--- {label} ---")
        
        # Apply event
        if event:
            state = emotion.update(event)
        else:
            # Let it decay for 3 seconds
            for _ in range(30):
                state = emotion.update()
                time.sleep(0.1)

        # Get expressions
        expr = expression.update(state.to_dict())
        speech = prosody.compute_speech_params(state.to_dict())

        print(f"  PAD: P={state.pleasure:.2f} A={state.arousal:.2f} D={state.dominance:.2f}")
        dom, val = emotion.get_dominant_emotion()
        print(f"  Emotion: {dom} ({val:.2f})")
        print(f"  Mouth: {expr['face']['mouth']:.2f} | Lean: {expr['body']['lean']:.2f} | Gaze: {expr['gaze']['target']}")
        print(f"  Speech: {speech['wpm']} WPM, pitch +{speech['pitch_shift_hz']} Hz")
        print()
        time.sleep(1.5)

    print("Demo complete.")


def main():
    demo()


if __name__ == "__main__":
    main()
