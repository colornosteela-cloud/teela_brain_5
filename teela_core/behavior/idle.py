"""
Idle Behavior: What Teela does when nothing is happening

A truly humanistic robot should NEVER be "waiting" in a frozen state.
Even in idle, she should:
    - Breathe (subtle body sway)
    - Glance around (scanning gaze)
    - Occasional idle vocalizations (hmm, small sighs)
    - Shift weight occasionally
    - React to ambient sounds with ear-like head movement

This makes her feel alive even when not engaged.
"""

import math
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class IdleSnapshot:
    head_yaw_deg: float
    head_pitch_deg: float
    body_sway: float
    gaze_target: Optional[str]
    vocalization: Optional[str]
    next_state_change_s: float


class IdleBehavior:
    """Continuous idle animation system."""

    def __init__(self):
        self._phase = random.random() * 100.0
        self._gaze_timer = 0.0
        self._vocalization_timer = random.uniform(10, 30)
        self._current_gaze = None
        self._next_change = time.time() + random.uniform(3, 6)

    def tick(
        self,
        delta_s: float,
        emotion: Dict,
    ) -> IdleSnapshot:
        """Generate next idle state. Call at ~30 Hz."""
        self._phase += delta_s

        # Breathing sway
        sway = math.sin(self._phase * 0.5) * 0.02 + math.sin(self._phase * 0.13) * 0.01

        # Head movement: slowly drift
        head_yaw = math.sin(self._phase * 0.2) * 15
        head_pitch = math.sin(self._phase * 0.15) * 5

        # Gaze shifts occasionally
        self._gaze_timer += delta_s
        if time.time() > self._next_change:
            self._current_gaze = random.choice(["left", "right", "up", "down", "forward", None])
            self._next_change = time.time() + random.uniform(3, 8)
            self._gaze_timer = 0.0

        # Occasional vocalization
        vocal = None
        self._vocalization_timer -= delta_s
        if self._vocalization_timer <= 0 and emotion.get("arousal", 0) > -0.3:
            if random.random() < 0.1:
                vocal = random.choice(["hmm", "uh-huh", "*soft hum*", None])
            self._vocalization_timer = random.uniform(15, 60)

        return IdleSnapshot(
            head_yaw_deg=round(head_yaw, 2),
            head_pitch_deg=round(head_pitch, 2),
            body_sway=round(sway, 4),
            gaze_target=self._current_gaze,
            vocalization=vocal,
            next_state_change_s=self._next_change - time.time(),
        )
