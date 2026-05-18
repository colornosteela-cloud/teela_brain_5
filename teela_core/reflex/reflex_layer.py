"""Reflex Layer: hard real-time safety overrides.

Runs at the highest frequency (can be on Teensy directly, or on Jetson with <10ms latency).
Rules:
- NO reasoning overheads
- NO LLM calls
- No blocking I/O
- Pure geometry + sensor thresholds
- Can HALT all motion instantly
- Accepts emergency commands from e-skin (body touch → freeze)
"""

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np


@dataclass
class SensorReading:
    name: str
    value: float  # distance (meters), voltage, whatever
    timestamp: float = field(default_factory=time.time)


@dataclass
class ReflexCommand:
    cmd: str  # HALT | SLOW | RESUME | EMERGENCY_PARK | FREEZE
    reason: str
    timestamp: float = field(default_factory=time.time)
    source: str = "ultrasonic"  # ultrasonic | eskin | imu | user


class ReflexLayer:
    """Safety reflexes for Teela humanoid."""

    SAFETY_THRESHOLDS = {
        "ultrasonic_front_min": 0.4,  # meters: emergency if < this
        "ultrasonic_caution": 0.8,
        "cliff_drop_cm": 10.0,  # IMU pitch threshold for stairs/cliffs
        "tilt_max_deg": 25.0,
    }

    FREEZE_DURATION_S = 1.5

    def __init__(self, callback: Optional[Callable[[ReflexCommand], None]] = None):
        self.callback = callback
        self._last_state = "running"
        self._consecutive_breaches = 0
        self._frozen_until = 0.0

    def evaluate(self, sensor_readings: List[SensorReading]) -> ReflexCommand:
        """Evaluate all sensor readings and emit a reflex command."""
        now = time.time()

        # If e-skin has frozen us recently, stay frozen
        if now < self._frozen_until:
            cmd = ReflexCommand(cmd="FREEZE", reason="E-skin freeze active", source="eskin")
            if self.callback:
                self.callback(cmd)
            return cmd

        min_dist = float("inf")
        max_tilt = 0.0  # degrees from vertical
        cliff_detected = False

        for reading in sensor_readings:
            if "ultrasonic" in reading.name or "tof" in reading.name:
                min_dist = min(min_dist, reading.value)
            elif "tilt" in reading.name or "pitch" in reading.name:
                max_tilt = max(max_tilt, abs(reading.value))
            elif "cliff" in reading.name:
                if reading.value > self.SAFETY_THRESHOLDS["cliff_drop_cm"]:
                    cliff_detected = True

        # Decision tree
        if min_dist < self.SAFETY_THRESHOLDS["ultrasonic_front_min"] or cliff_detected:
            self._consecutive_breaches += 1
            if self._consecutive_breaches >= 2:
                cmd = ReflexCommand(cmd="EMERGENCY_PARK", reason=f"Emergency: obstacle {min_dist:.2f}m")
            else:
                cmd = ReflexCommand(cmd="HALT", reason=f"Obstacle at {min_dist:.2f}m")
        elif max_tilt > self.SAFETY_THRESHOLDS["tilt_max_deg"]:
            cmd = ReflexCommand(cmd="HALT", reason=f"Excessive tilt: {max_tilt:.1f}deg")
        elif min_dist < self.SAFETY_THRESHOLDS["ultrasonic_caution"]:
            cmd = ReflexCommand(cmd="SLOW", reason=f"Caution: object {min_dist:.2f}m")
        else:
            self._consecutive_breaches = 0
            cmd = ReflexCommand(cmd="RESUME", reason="Path clear")

        self._last_state = cmd.cmd
        if self.callback:
            self.callback(cmd)
        return cmd

    def handle_eskin_safety(self, safety_cmd: str, reason: str) -> None:
        """Called by ESkinProcessor when an unsafe touch is detected.

        Args:
            safety_cmd: "FREEZE" or "SLOW"
            reason: human-readable description
        """
        now = time.time()
        if safety_cmd == "FREEZE":
            self._frozen_until = now + self.FREEZE_DURATION_S
            self._consecutive_breaches = 2  # triggers emergency state
        # Also emit to immediate actuator control if callback present
        if self.callback:
            self.callback(ReflexCommand(cmd=safety_cmd, reason=reason, source="eskin"))
