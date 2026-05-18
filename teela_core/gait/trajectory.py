"""Trajectory planning: footsteps, CoM path, swing trajectories.

This runs on Jetson to compute target footsteps, which are sent
to Teensy as simple GaitTarget commands. The Teensy interpolates
between targets at 1kHz.
"""

import math
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


@dataclass
class Footstep:
    x_m: float
    y_m: float
    z_m: float  # lift height during swing
    yaw_rad: float
    is_left: bool
    swing_time_s: float


class TrajectoryPlanner:
    """Plan footstep sequences and CoM trajectories."""

    def __init__(
        self,
        step_length_m: float = 0.15,
        step_width_m: float = 0.12,
        step_height_m: float = 0.04,
        stance_height_m: float = 0.08,
        com_height_m: float = 0.25,
    ):
        self.step_length = step_length_m
        self.step_width = step_width_m
        self.step_height = step_height_m
        self.stance_height = stance_height_m
        self.com_height = com_height_m

    def plan_straight_steps(
        self,
        direction_m: float,
        start_left: bool = True,
    ) -> List[Footstep]:
        """Generate a straight line footstep sequence."""
        n_steps = max(1, int(abs(direction_m) / self.step_length))
        sign = math.copysign(1.0, direction_m)
        steps = []
        for i in range(n_steps):
            is_left = (i % 2 == 0) if start_left else (i % 2 == 1)
            y_offset = self.step_width / 2 * (1 if is_left else -1)
            steps.append(Footstep(
                x_m=(i + 1) * self.step_length * sign,
                y_m=y_offset,
                z_m=self.step_height,
                yaw_rad=0.0,
                is_left=is_left,
                swing_time_s=0.3,
            ))
        return steps

    def plan_turn_in_place(
        self,
        delta_yaw_rad: float,
        start_left: bool = True,
    ) -> List[Footstep]:
        """Yaw in place via small steering steps."""
        step_yaw = 0.15  # radians per step
        n_steps = int(abs(delta_yaw_rad) / step_yaw) + 1
        sign = math.copysign(1.0, delta_yaw_rad)
        steps = []
        for i in range(n_steps):
            is_left = (i % 2 == 0) if start_left else (i % 2 == 1)
            steps.append(Footstep(
                x_m=0.0,
                y_m=(self.step_width / 2) * (1 if is_left else -1),
                z_m=self.step_height,
                yaw_rad=step_yaw * sign,
                is_left=is_left,
                swing_time_s=0.3,
            ))
        return steps

    def compute_com_trajectory(
        self,
        footsteps: List[Footstep],
        dt: float = 0.01,
    ) -> np.ndarray:
        """3D CoM trajectory (x, y, z) over time. Linear interpolation between step midpoints."""
        points: List[Tuple[float, float, float]] = [(0.0, 0.0, self.com_height)]
        for step in footsteps:
            points.append((step.x_m, step.y_m, self.com_height))
        arr = np.array(points)
        t = np.linspace(0, 1, len(arr))
        t_fine = np.linspace(0, 1, int(len(arr) * 0.3 / dt))
        # Simple linear interpolation for CoM
        x = np.interp(t_fine, t, arr[:, 0])
        y = np.interp(t_fine, t, arr[:, 1])
        z = np.full_like(t_fine, self.com_height)
        return np.column_stack([x, y, z])
