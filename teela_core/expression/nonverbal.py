"""
Non-Verbal Expression System (Silicone-Skin Edition)

Teela does not have a face with LED expressions. Her entire body is wrapped
in soft silicone skin with embedded e-skin sensors. Expression is purely
physical — servo-driven body language + tactile awareness.

Physical expression channels:
    - Head movements (nodding, shaking, tilting, orienting toward speaker)
    - Body posture (leaning forward = interest, leaning back = surprise/fear)
    - Gaze (looking at speaker, looking at object, glancing away)
    - Breathing-like motion (subtle idle sway, faster when excited)
    - Hand/arm gestures (limited by servos, but head nod + body lean convey a lot)
    - Gait modulation (bouncy = happy, tentative = cautious)

E-skin integration:
    - If face is touched while tilting head → soften movement
    - If shoulder tapped → orient body toward that side
    - If unexpected back pressure → lean forward reflexively, then check

Design rule: Non-verbal expression should be SUBTLE.
Over-animated robots feel cartoonish, not humanistic.
"""

import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class SiliconeFaceExpressionState:
    """
    No LED screen. No glowing face.
    These are SERVO targets mapped to expressions:
    - eyebrow raise / furrow → eyebrows servo tilt
    - mouth curve             → jaw servo position
    - eye openness            → eyelid servos
    - blink                   → eyelid servo pulse

    The values here are normalized [-1, +1]. The gait/communication
    layer maps them to actual servo angles based on Teela's
    physical configuration.
    """
    eyebrow_position: float = 0.0   # -1 = furrowed (concern), +1 = raised (surprise)
    mouth_curve: float = 0.0        # -1 = frown, 0 = neutral, +1 = smile
    jaw_tension: float = 0.0       # 0 = relaxed, 1 = tight (fear/anger)
    eyelid_openness: float = 1.0   # 0 = closed, 1 = wide open
    blink_rate_hz: float = 0.2    # ~3-5 per min idle
    next_blink_time: float = field(default_factory=time.time)


@dataclass
class BodyExpressionState:
    """Torso, shoulders, base — all physical servo targets."""
    lean_forward: float = 0.0      # -1 = leaning back, +1 = leaning forward (interest)
    lean_tilt: float = 0.0         # left / right trunk tilt
    breathing_depth: float = 0.05  # idle sway amplitude
    breathing_rate_hz: float = 0.15  # ~9 breaths/min idle
    shoulder_tension: float = 0.0  # 0 = relaxed, 1 = raised/defensive


@dataclass
class GazeState:
    """Where Teela is looking and how."""
    target: Optional[Tuple[float, float, float]] = None  # world coordinates
    target_name: Optional[str] = None
    gaze_style: str = "direct"   # direct, avert, glance, sweep, unfocused
    gaze_duration_s: float = 0.0  # how long she's been looking
    # If the face sensors (e-skin) detect touch near the eye,
    # Teela may reflexively blink or look away
    eskin_face_touched: bool = False
    eskin_touch_zone: Optional[str] = None


class SiliconeBasedNonVerbalExpression:
    """Generates continuous, lifelike non-verbal expression signals.

    No LEDs. No screens. Pure physical body language + servo targets.
    """

    def __init__(self):
        self.face = SiliconeFaceExpressionState()
        self.body = BodyExpressionState()
        self.gaze = GazeState()
        self._last_update = time.time()
        self._phase = 0.0  # for breathing animation

        # E-skin integration state
        self._face_touch_active = False
        self._face_touch_since = 0.0
        self._shoulder_touched_side: Optional[str] = None

    def update(
        self,
        emotional_state: Dict,
        social_state: Optional[Dict] = None,
        intention: Optional[str] = None,
        eskin_touch_events: Optional[List[Dict]] = None,
    ) -> Dict:
        """Step expression forward by one tick (call at ~30 Hz for smooth).

        Args:
            eskin_touch_events: list of touch_event dicts from ESkinProcessor
        """
        now = time.time()
        dt = now - self._last_update
        self._last_update = now
        self._phase += dt

        # E-skin may temporarily override expression (reflexive response)
        face_override = False
        if eskin_touch_events:
            face_override = self._process_eskin_events(eskin_touch_events, now)

        if not face_override:
            # 1. Emotion-driven facial expression (servo targets)
            self._update_face_servos_from_emotion(emotional_state, dt)

        # 2. Breathing/idle body motion
        self._update_breathing(dt)

        # 3. Gaze + blink behavior
        self._update_gaze_and_blink(now, social_state)

        # 4. Modulate gait from emotion (if moving)
        gait_modulation = self._compute_gait_modulation(emotional_state)

        return {
            "face_servos": {
                "eyebrow": round(self.face.eyebrow_position, 3),
                "mouth": round(self.face.mouth_curve, 3),
                "jaw_tension": round(self.face.jaw_tension, 3),
                "eyelids": round(self.face.eyelid_openness, 3),
                "blink_rate_hz": round(self.face.blink_rate_hz, 3),
            },
            "body_servos": {
                "lean_forward": round(self.body.lean_forward, 3),
                "lean_tilt": round(self.body.lean_tilt, 3),
                "sway": round(math.sin(self._phase * self.body.breathing_rate_hz * 2 * math.pi) * self.body.breathing_depth, 4),
                "breathing_depth": round(self.body.breathing_depth, 3),
                "breathing_rate_hz": round(self.body.breathing_rate_hz, 3),
                "shoulder_tension": round(self.body.shoulder_tension, 3),
            },
            "gaze": {
                "target": self.gaze.target_name,
                "style": self.gaze.gaze_style,
                "duration": round(self.gaze.gaze_duration_s, 1),
                "is_blinking": now < self.face.next_blink_time + 0.15,
            },
            "gait_modulation": gait_modulation,
            "eskin_override_active": face_override,
        }

    # ──────────────────────────────────────────────────────────
    # E-Skin → Expression Reflexes
    # ──────────────────────────────────────────────────────────
    def _process_eskin_events(self, events: List[Dict], now: float) -> bool:
        """Process touch events and possibly trigger reflexive expression.

        Returns True if an override is active (suppressing normal expression).
        """
        override = False
        for evt in events:
            zone = evt.get("zone", "")
            intensity = evt.get("intensity", "none")

            # Face touched → reflexive blink + soften expression
            if zone in ("face.left", "face.right", "forehead", "cheek.left", "cheek.right"):
                self.face.eyelid_openness = 0.1  # blink closed
                self.face.next_blink_time = now + 0.2
                self._face_touch_active = True
                self._face_touch_since = now
                override = True

            # Shoulder tap → orient body toward the touched side
            if "shoulder" in zone and intensity in ("light_touch", "touch"):
                side = 1.0 if ".right" in zone else -1.0
                self.body.lean_tilt = side * 0.15  # slight lean toward
                self._shoulder_touched_side = zone

            # Neck touched + firm → slight forward lean (submissive/defensive)
            if "neck" in zone and intensity in ("firm_pressure", "unsafe_pressure"):
                self.body.lean_forward = 0.2
                self.body.shoulder_tension = 0.3
                override = True

        return override

    # ──────────────────────────────────────────────────────────
    # Expression from Emotion
    # ──────────────────────────────────────────────────────────
    def _update_face_servos_from_emotion(self, emotion: Dict, dt: float) -> None:
        valence = emotion.get("pleasure", 0)
        arousal = emotion.get("arousal", 0)
        dominant_emotion = emotion.get("dominant_emotion", "neutral")

        # Mouth smile/frown → jaw servo target
        target_mouth = max(-0.8, min(0.8, valence * 0.7))
        self.face.mouth_curve += (target_mouth - self.face.mouth_curve) * 3.0 * dt

        # Eyebrows: surprise raises, anger furrows
        if dominant_emotion == "surprise":
            target_brow = 0.6
        elif dominant_emotion == "anger":
            target_brow = -0.6
        else:
            target_brow = valence * 0.3
        self.face.eyebrow_position += (target_brow - self.face.eyebrow_position) * 2.0 * dt

        # Jaw tension: fear/anger tight, calm/sad relaxed
        tension = max(0.0, emotion.get("fear", 0) + emotion.get("anger", 0))
        self.face.jaw_tension += (tension - self.face.jaw_tension) * 2.0 * dt

        # Blink rate: arousal elevates blink, calm deepens slow
        target_blink = 0.2 + arousal * 0.15
        self.face.blink_rate_hz += (target_blink - self.face.blink_rate_hz) * 0.5 * dt

    def _update_breathing(self, dt: float) -> None:
        base_rate = 0.15
        # Smiling people breathe slightly deeper
        target_depth = 0.05 + abs(self.face.mouth_curve) * 0.02
        self.body.breathing_depth += (target_depth - self.body.breathing_depth) * 1.0 * dt

    def _update_gaze_and_blink(self, now: float, social_state: Optional[Dict]) -> None:
        # Natural blink cycle
        if self._face_touch_active and now - self._face_touch_since > 1.0:
            self._face_touch_active = False  # allow normal blinking again

        if not self._face_touch_active:
            if now >= self.face.next_blink_time:
                # Trigger a blink: eyelids close for ~100-200ms
                self.face.eyelid_openness = 0.0
                self.face.next_blink_time = now + random.expovariate(self.face.blink_rate_hz)
            else:
                # Recover open (fast muscle)
                self.face.eyelid_openness += (1.0 - self.face.eyelid_openness) * 10.0

        # Social gaze:
        # - Look at speaker when they speak
        # - Occasional glances away so as not to stare
        if social_state:
            speaker = social_state.get("current_speaker")
            if speaker:
                self.gaze.target_name = speaker
                self.gaze.gaze_style = "direct"
                self.gaze.gaze_duration_s += 0.033  # assuming 30 Hz
            else:
                self.gaze.gaze_duration_s = 0.0
                # If no speaker, unfocused is fine
                self.gaze.gaze_style = "unfocused"
        else:
            self.gaze.gaze_duration_s = 0.0
            self.gaze.gaze_style = "unfocused"

    def _compute_gait_modulation(self, emotion: Dict) -> Dict:
        valence = emotion.get("pleasure", 0)
        arousal = emotion.get("arousal", 0)
        return {
            "step_height_multiplier": 1.0 + valence * 0.3 + arousal * 0.1,
            "speed_multiplier": 1.0 + arousal * 0.3,
            "caution": max(0.0, emotion.get("fear", 0) + emotion.get("disgust", 0)),
            "hesitation": emotion.get("surprise", 0) * 0.5,
        }
