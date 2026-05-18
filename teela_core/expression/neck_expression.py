"""Neck Pan/Tilt Expression System

Teela currently only has a neck (2 servos: pan + tilt).
ALL emotion/expression/attention is encoded through neck motion.

This module converts cognitive state → {pan_deg, tilt_deg} commands
for the Teensy to execute.

Rules:
- Pan = where to look (left/right, toward person, toward object)
- Tilt = emotional signal (down = sad/submissive, up = surprise/alert,
  forward = interest, back = fear/caution)
- Speed = emotional arousal (fast = excited/startled, slow = calm)
- Smoothness = trust (jittery = nervous, smooth = confident)

In future, as more servos are added, this will expand into full-body.
"""

import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class NeckCommand:
    pan_deg: float = 0.0      # -90 (left) to +90 (right)
    tilt_deg: float = 0.0     # -60 (down) to +60 (up)
    speed_dps: float = 30.0    # degrees per second
    hold_s: float = 0.5       # how long to hold pose
    reason: str = ""

class NeckExpression:
    """Generate lifelike neck motion from cognitive state."""

    def __init__(self, pan_range=(-80, 80), tilt_range=(-45, 45)):
        self.pan_range = pan_range
        self.tilt_range = tilt_range

        self._default_pan = 0.0
        self._default_tilt = 5.0  # slight forward "ready" posture

        self._current_pan = self._default_pan
        self._current_tilt = self._default_tilt
        self._target_pan = self._default_pan
        self._target_tilt = self._default_tilt

        self._last_blink_time = 0.0
        self._blinking = False
        self._blink_duration_s = 0.15

        self._breath_phase = 0.0
        self._gaze_target_name: Optional[str] = None

    def update(
        self,
        emotion: dict,
        speaker_position: Optional[Tuple[float, float, float]] = None,
        pointed_position: Optional[Tuple[float, float, float]] = None,
        mode: str = "idle",       # idle | conversation | task
        eskin_face_touched: bool = False,
    ) -> NeckCommand:
        """Compute next neck pose.

        Args:
            emotion: dict from EmotionEngine (pleasure, arousal, fear, etc.)
            speaker_position: (x, y, z) in robot frame — look toward
            pointed_position: (x, y, z) — person is pointing here
            mode: current social mode
            eskin_face_touched: if True, reflexively look down/blink

        Returns:
            NeckCommand with pan, tilt, speed
        """
        now = time.time()
        pleasure = emotion.get("pleasure", 0)
        arousal = emotion.get("arousal", 0)
        fear = emotion.get("fear", 0)
        trust = emotion.get("trust", 0)

        # ── E-Skin face touch reflex ──────────────────────────────
        if eskin_face_touched:
            # Blink-fast downward look (surprise/protective)
            self._blinking = True
            self._last_blink_time = now
            return NeckCommand(
                pan_deg=self._current_pan,
                tilt_deg=-15.0,
                speed_dps=120.0,
                hold_s=0.3,
                reason="face_touch_reflex",
            )

        # ── GAZE: prioritize looking at what matters ──────────
        target_pan = self._default_pan
        target_tilt = self._default_tilt

        if pointed_position is not None:
            # Person is pointing! Look at what they're pointing at
            px, py, pz = pointed_position
            target_pan = math.degrees(math.atan2(py, px))
            target_tilt = math.degrees(math.atan2(pz, (px**2 + py**2)**0.5))
            reason = "looking_at_pointed_object"
        elif speaker_position is not None:
            # Look at the speaker
            sx, sy, sz = speaker_position
            target_pan = math.degrees(math.atan2(sy, sx))
            target_tilt = math.degrees(math.atan2(sz, (sx**2 + sy**2)**0.5))
            reason = f"looking_at_speaker"
        else:
            # No one to look at — scan slowly or idle
            reason = "idle_gaze"

        # ── EMOTION modulates target_tilt ────────────────────────
        # Sad / low trust → look down
        target_tilt += (pleasure - 0.3) * -15.0  # negative pleasure = down
        # Fear → look more level, cautious
        target_tilt += fear * -10.0
        # Surprise / high arousal → look up alert
        target_tilt += arousal * 12.0
        # Trust → slight forward lean (tilt down a bit, but engaged)
        target_tilt += (trust - 0.5) * -5.0

        # ── BREATHING (subtle idle sway) ────────────────────────
        if mode == "idle":
            self._breath_phase += 0.05
            target_tilt += math.sin(self._breath_phase) * 2.0
            # Slow drift pan to keep "alive"
            target_pan += math.sin(self._breath_phase * 0.3) * 8.0

        # ── AROUSAL modulates speed ────────────────────────────
        # High arousal = fast head movement (startled, excited)
        # Low arousal = slow, smooth (calm, tired)
        base_speed = 25.0 + arousal * 40.0 + fear * 30.0

        # Clamp
        target_pan = max(self.pan_range[0], min(self.pan_range[1], target_pan))
        target_tilt = max(self.tilt_range[0], min(self.tilt_range[1], target_tilt))

        self._target_pan = target_pan
        self._target_tilt = target_tilt

        return NeckCommand(
            pan_deg=round(target_pan, 1),
            tilt_deg=round(target_tilt, 1),
            speed_dps=round(base_speed, 1),
            hold_s=0.5,
            reason=reason,
        )

    def current_as_command(self) -> NeckCommand:
        return NeckCommand(
            pan_deg=self._current_pan,
            tilt_deg=self._current_tilt,
            speed_dps=30.0,
            hold_s=0.5,
            reason="current_pose",
        )
