"""
Identity & Self-Model

Teela maintains a model of:
    - Her own body state (batteries, motors, temperature)
    - Her capabilities (what she can/can't do)
    - Her current "self" (emotional state + recent experiences)
    - What she is currently doing / intending to do

This is NOT sentience. It is a self-referential state machine that
allows coherent behavior and honest communication about limitations.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BodyState:
    battery_pct: float = 100.0
    cpu_temp_c: float = 35.0
    motor_temps: Dict[str, float] = field(default_factory=dict)
    last_servo_health_check: float = 0.0
    any_servos_overheating: bool = False
    any_servos_stuck: bool = False


@dataclass
class Capability:
    name: str
    can_do: bool
    confidence: float  # how reliable (0-1)
    last_successful: Optional[float] = None
    failure_count_recent: int = 0


@dataclass
class Intention:
    """What Teela is currently trying to do."""
    action_type: str  # move_to, speak, observe, rest, interact, explore
    target: Optional[str] = None
    target_position: Optional[tuple] = None
    reason: str = ""
    start_time: float = field(default_factory=time.time)
    estimated_duration_s: float = 0.0
    progress: float = 0.0  # 0-1


class SelfModel:
    """Teela's self-representation."""

    def __init__(self):
        self.body = BodyState()
        self.capabilities: Dict[str, Capability] = {
            "walk": Capability("walk", True, 0.9),
            "navigate": Capability("navigate", True, 0.8),
            "speak": Capability("speak", True, 0.95),
            "pick_up_object": Capability("pick_up_object", False, 0.0),  # no grippers yet
            "recognize_faces": Capability("recognize_faces", True, 0.7),
            "point_detect": Capability("point_detect", True, 0.8),
        }
        self.current_intention: Optional[Intention] = None
        self.last_reflection: str = ""
        self.uptime_s: float = 0.0
        self.total_distance_walked_m: float = 0.0
        self.total_interactions: int = 0
        self._last_update = time.time()

    def update(self) -> None:
        now = time.time()
        dt = now - self._last_update
        self._last_update = now
        self.uptime_s += dt

    def can_i(self, capability_name: str) -> Tuple[bool, str]:
        """Honest self-assessment of capabilities."""
        if capability_name not in self.capabilities:
            return False, f"I don't have a '{capability_name}' capability."
        cap = self.capabilities[capability_name]
        if not cap.can_do:
            return False, f"I can't {capability_name} yet."
        if cap.confidence < 0.5:
            return False, f"I'm not very good at {capability_name} yet."
        if self.body.battery_pct < 10:
            return False, "I'm low on battery."
        return True, f"I can {capability_name}."

    def set_intention(self, intention: Intention) -> None:
        self.current_intention = intention

    def report_state(self) -> str:
        parts = [
            f"Battery: {self.body.battery_pct:.0f}%",
            f"Uptime: {self.uptime_s/3600:.1f} hours",
            f"Interactions today: {self.total_interactions}",
            f"Currently: {self.current_intention.action_type if self.current_intention else 'idle'}",
        ]
        return " | ".join(parts)
