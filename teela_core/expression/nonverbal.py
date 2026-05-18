"""
Non-Verbal Expression System

Teela communicates through:
    - Head movements (nodding, shaking, tilting, orienting toward speaker)
    - Body posture (leaning forward = interest, leaning back = surprise/fear)
    - Gaze (looking at speaker, looking at object, glancing away)
    - Breathing-like motion (subtle idle sway, faster when excited)
    - Hand/arm gestures (limited by servos, but head nod + body lean convey a lot)
    - LED face (if available): color temperature, brightness, pattern
    - Gait modulation (bouncy = happy, tentative = cautious)

Design rule: Non-verbal expression should be SUBTLE.
Over-animated robots feel cartoonish, not humanistic.
"""

import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class FacialExpressionState:
    """For LED face, screen face, or abstract representation."""
    emotion: str = "neutral"
    eye_openness: float = 1.0  # 0 = closed, 1 = wide open
    eyebrow_position: float = 0.0  # -1 = furrowed (concern), +1 = raised (surprise)
    mouth_curve: float = 0.0  # -1 = frown, 0 = neutral, +1 = smile
    blink_rate_hz: float = 0.2  # normal ~3-5 blinks/min = ~0.05-0.08 Hz
    pupil_dilation: float = 0.5  # 0 = constricted, 1 = dilated (arousal)
    color_temp: Tuple[int, int, int] = (255, 255, 255)  # RGB for "face" light
    brightness: float = 0.8  # 0-1


@dataclass
class BodyExpressionState:
    """Torso, shoulders, base."""
    lean_forward: float = 0.0  # -1 = leaning back, +1 = leaning forward (interest)
    tilt_right: float = 0.0    # head/body tilt
    breathing_depth: float = 0.05  # idle sway amplitude
    breathing_rate_hz: float = 0.15  # ~9 breaths/min idle


@dataclass
class GazeState:
    """Where Teela is looking and how."""
    target: Optional[Tuple[float, float, float]] = None  # world coordinates
    target_name: Optional[str] = None
    gaze_style: str = "direct"  # direct, avert, glance, sweep, unfocused
    gaze_duration_s: float = 0.0  # how long she's been looking
    next_blink_time: float = field(default_factory=time.time)


class NonVerbalExpression:
    """Generates continuous, lifelike non-verbal expression signals."""

    def __init__(self):
        self.face = FacialExpressionState()
        self.body = BodyExpressionState()
        self.gaze = GazeState()
        self._last_update = time.time()
        self._phase = 0.0  # for breathing animation

    def update(
        self,
        emotional_state: Dict,
        social_state: Optional[Dict] = None,
        intention: Optional[str] = None,
    ) -> Dict:
        """Step expression forward by one tick (call at ~30 Hz for smooth)."""
        now = time.time()
        dt = now - self._last_update
        self._last_update = now
        self._phase += dt

        # 1. Emotion-driven facial expression
        self._update_face_from_emotion(emotional_state, dt)

        # 2. Breathing/idle body motion
        self._update_breathing(dt)

        # 3. Gaze behavior
        self._update_gaze(now, social_state)

        # 4. Modulate gait from emotion (if moving)
        gait_modulation = self._compute_gait_modulation(emotional_state)

        return {
            "face": {
                "eyebrow": round(self.face.eyebrow_position, 3),
                "mouth": round(self.face.mouth_curve, 3),
                "blink_rate": round(self.face.blink_rate_hz, 3),
                "color": self.face.color_temp,
                "brightness": round(self.face.brightness, 3),
            },
            "body": {
                "lean": round(self.body.lean_forward, 3),
                "tilt": round(self.body.tilt_right, 3),
                "sway": round(math.sin(self._phase * self.body.breathing_rate_hz * 2 * math.pi) * self.body.breathing_depth, 4),
                "breathing_depth": round(self.body.breathing_depth, 3),
            },
            "gaze": {
                "target": self.gaze.target_name,
                "style": self.gaze.gaze_style,
                "duration": round(self.gaze.gaze_duration_s, 1),
                "is_blinking": now >= self.gaze.next_blink_time,
            },
            "gait_modulation": gait_modulation,
        }

    def _update_face_from_emotion(self, emotion: Dict, dt: float) -> None:
        """Map emotions to facial parameters."""
        valence = emotion.get("pleasure", 0)
        arousal = emotion.get("arousal", 0)
        dominant_emotion = emotion.get("dominant_emotion", "neutral")

        # Mouth: valence drives smile/frown
        target_mouth = max(-0.8, min(0.8, valence * 0.7))
        self.face.mouth_curve += (target_mouth - self.face.mouth_curve) * 3.0 * dt

        # Eyebrows: surprise raises brows, anger furrows
        if dominant_emotion == "surprise":
            target_brow = 0.6
        elif dominant_emotion == "anger":
            target_brow = -0.6
        else:
            target_brow = valence * 0.3
        self.face.eyebrow_position += (target_brow - self.face.eyebrow_position) * 2.0 * dt

        # Pupil: arousal dilates (excitement/fear), relaxation constricts
        target_pupil = 0.3 + arousal * 0.35
        self.face.pupil_dilation += (target_pupil - self.face.pupil_dilation) * 1.0 * dt

        # Blink rate: excitement increases blink, deep thought decreases
        target_blink = 0.2 + arousal * 0.15
        self.face.blink_rate_hz += (target_blink - self.face.blink_rate_hz) * 0.5 * dt

        # Color temp: valence shifts warm/cool
        if valence > 0.3:
            self.face.color_temp = (255, 220, 180)  # warm
        elif valence < -0.3:
            self.face.color_temp = (180, 200, 255)  # cool
        else:
            self.face.color_temp = (255, 255, 255)  # neutral

        # Brightness: arousal brightens
        self.face.brightness = 0.6 + arousal * 0.2
        self.face.brightness = max(0.3, min(1.0, self.face.brightness))

    def _update_breathing(self, dt: float) -> None:
        # Breathing rate increases with arousal
        base_rate = 0.15
        target_depth = 0.05 + abs(self.face.mouth_curve) * 0.02  # smile = slightly bigger breaths
        self.body.breathing_depth += (target_depth - self.body.breathing_depth) * 1.0 * dt

    def _update_gaze(self, now: float, social_state: Optional[Dict]) -> None:
        # Blink management
        if now >= self.gaze.next_blink_time:
            # Blink duration ~100-200ms
            self.gaze.next_blink_time = now + random.expovariate(self.face.blink_rate_hz)
            self.face.eye_openness = 0.1
        else:
            # Recover open
            self.face.eye_openness += (1.0 - self.face.eye_openness) * 10.0

        # Social gaze rules
        if social_state:
            speaker = social_state.get("current_speaker")
            if speaker:
                self.gaze.target_name = speaker
                self.gaze.gaze_style = "direct"
                self.gaze.gaze_duration_s += 1.0 / 30.0  # assuming 30 Hz

    def _compute_gait_modulation(self, emotion: Dict) -> Dict:
        """Modulate gait parameters based on emotional state."""
        valence = emotion.get("pleasure", 0)
        arousal = emotion.get("arousal", 0)
        return {
            "step_height_multiplier": 1.0 + valence * 0.3 + arousal * 0.1,  # bouncier when happy
            "speed_multiplier": 1.0 + arousal * 0.3,
            "caution": max(0.0, emotion.get("fear", 0) + emotion.get("disgust", 0)),
            "hesitation": emotion.get("surprise", 0) * 0.5,
        }
