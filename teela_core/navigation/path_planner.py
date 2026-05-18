"""Path planner: A* on occupancy grid, DWA for dynamic collision avoidance."""

import heapq
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class GaitTarget:
    """Target pose for the Teensy gait controller."""
    x_m: float  # forward
    y_m: float  # lateral
    yaw_rad: float  # heading
    max_speed_mps: float = 0.5
    gait_style: str = "walk"  # walk | shuffle | step_in_place | halt
    priority: int = 0  # higher = more urgent


class PathPlanner:
    """Hybrid planner:
    1. A* on static occupancy grid for long-range goals.
    2. DWA (Dynamic Window Approach) for local obstacle avoidance.

    Target consumer: Teensy gait controller (via serial).
    Frequency: 10 Hz on Jetson.
    """

    def __init__(
        self,
        grid_resolution_m: float = 0.05,
        grid_size_m: Tuple[float, float] = (10.0, 10.0),
        robot_radius_m: float = 0.25,
        max_speed_mps: float = 0.8,
        max_yaw_rate_radps: float = 1.0,
    ):
        self.grid_res = grid_resolution_m
        self.grid_size = grid_size_m
        self.robot_radius = robot_radius_m
        self.max_speed = max_speed_mps
        self.max_yaw_rate = max_yaw_rate_radps
        # Occupancy grid: 0 = free, 1 = occupied
        self.grid = np.zeros(
            (
                int(grid_size_m[1] / grid_resolution_m),
                int(grid_size_m[0] / grid_resolution_m),
            ),
            dtype=np.uint8,
        )
        self.origin = (grid_size_m[0] / 2, grid_size_m[1] / 2)  # robot starts centered

    def world_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        """Convert world coordinates to grid indices."""
        gx = int((x + self.origin[0]) / self.grid_res)
        gy = int((y + self.origin[1]) / self.grid_res)
        return (
            max(0, min(self.grid.shape[1] - 1, gx)),
            max(0, min(self.grid.shape[0] - 1, gy)),
        )

    def grid_to_world(self, gx: int, gy: int) -> Tuple[float, float]:
        """Convert grid indices to world coordinates."""
        x = gx * self.grid_res - self.origin[0]
        y = gy * self.grid_res - self.origin[1]
        return (x, y)

    def update_occupancy(self, obstacles: List[Tuple[float, float, float]]) -> None:
        """Mark obstacles in the grid. Clears previous obstacles if full update."""
        # Naive: clear and re-mark for simplicity. Production uses probabilistic update.
        self.grid.fill(0)
        for ox, oy, radius in obstacles:
            gx, gy = self.world_to_grid(ox, oy)
            rr = max(1, int((radius + self.robot_radius) / self.grid_res))
            y0 = max(0, gy - rr)
            y1 = min(self.grid.shape[0], gy + rr + 1)
            x0 = max(0, gx - rr)
            x1 = min(self.grid.shape[1], gx + rr + 1)
            for yy in range(y0, y1):
                for xx in range(x0, x1):
                    dx = (xx - gx) * self.grid_res
                    dy = (yy - gy) * self.grid_res
                    if math.hypot(dx, dy) <= radius + self.robot_radius:
                        self.grid[yy, xx] = 1

    def astar(
        self, start_m: Tuple[float, float], goal_m: Tuple[float, float]
    ) -> Optional[List[Tuple[float, float, float]]]:
        """A* in grid world. Returns path as list of (x, y, yaw)."""
        s_gx, s_gy = self.world_to_grid(*start_m)
        g_gx, g_gy = self.world_to_grid(*goal_m)

        if self.grid[s_gy, s_gx] == 1 or self.grid[g_gy, g_gx] == 1:
            return None  # Start or goal in obstacle

        def heuristic(a: Tuple[int, int], b: Tuple[int, int]) -> float:
            return math.hypot(a[0] - b[0], a[1] - b[1])

        open_set = []
        heapq.heappush(open_set, (0, s_gx, s_gy))
        came_from: dict = {}
        g_score = {(s_gx, s_gy): 0.0}

        while open_set:
            _, cx, cy = heapq.heappop(open_set)
            if (cx, cy) == (g_gx, g_gy):
                # Reconstruct
                path = []
                node = (cx, cy)
                while node in came_from:
                    path.append(node)
                    node = came_from[node]
                path.append((s_gx, s_gy))
                path.reverse()
                # Convert to world + compute yaws
                world_path = []
                for gx, gy in path:
                    world_path.append(self.grid_to_world(gx, gy))
                # Add yaw: tangent between consecutive points
                result = []
                for i in range(len(world_path)):
                    if i + 1 < len(world_path):
                        dx = world_path[i + 1][0] - world_path[i][0]
                        dy = world_path[i + 1][1] - world_path[i][1]
                        yaw = math.atan2(dy, dx)
                    else:
                        yaw = result[-1][2] if result else 0.0
                    result.append((world_path[i][0], world_path[i][1], yaw))
                return result

            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.grid.shape[1] and 0 <= ny < self.grid.shape[0]:
                    if self.grid[ny, nx] == 1:
                        continue
                    step_cost = math.hypot(dx, dy)
                    tentative = g_score.get((cx, cy), float("inf")) + step_cost
                    if tentative < g_score.get((nx, ny), float("inf")):
                        came_from[(nx, ny)] = (cx, cy)
                        g_score[(nx, ny)] = tentative
                        f = tentative + heuristic((nx, ny), (g_gx, g_gy))
                        heapq.heappush(open_set, (f, nx, ny))

        return None  # No path

    def dwa_next_target(
        self,
        current_pose: Tuple[float, float, float],
        path: List[Tuple[float, float, float]],
        dynamic_obstacles: List[Tuple[float, float, float]],
        sample_count: int = 20,
    ) -> GaitTarget:
        """Dynamic Window Approach: pick best (v, w) given current pose and obstacles."""
        cx, cy, c_yaw = current_pose

        # Candidate velocities
        v_samples = np.linspace(0, self.max_speed, sample_count)
        w_samples = np.linspace(-self.max_yaw_rate, self.max_yaw_rate, sample_count)

        best_score = -float("inf")
        best_target = GaitTarget(x_m=cx, y_m=cy, yaw_rad=c_yaw, max_speed_mps=0.0, gait_style="halt")

        # Look ahead on global path
        goal_idx = min(5, len(path) - 1)
        goal_x, goal_y, _ = path[goal_idx] if goal_idx < len(path) else path[-1]

        for v in v_samples:
            for w in w_samples:
                # Predict pose after dt=0.5s
                dt = 0.5
                nx = cx + v * math.cos(c_yaw + w * dt) * dt
                ny = cy + v * math.sin(c_yaw + w * dt) * dt
                n_yaw = c_yaw + w * dt

                # 1. Heading alignment
                angle_to_goal = math.atan2(goal_y - ny, goal_x - nx)
                heading_error = abs(math.atan2(
                    math.sin(angle_to_goal - n_yaw),
                    math.cos(angle_to_goal - n_yaw)
                ))
                heading_score = 1.0 - heading_error / math.pi

                # 2. Obstacle clearance
                min_dist = float("inf")
                for ox, oy, rad in dynamic_obstacles:
                    dist = math.hypot(nx - ox, ny - oy) - rad - self.robot_radius
                    min_dist = min(min_dist, dist)
                clearance_score = min(min_dist, 2.0) / 2.0  # cap at 2m

                # 3. Velocity preference (encourage moving)
                vel_score = v / self.max_speed

                if min_dist <= 0:
                    continue  # Collision

                score = 3.0 * heading_score + 2.0 * clearance_score + 1.0 * vel_score

                if score > best_score:
                    best_score = score
                    best_target = GaitTarget(
                        x_m=nx,
                        y_m=ny,
                        yaw_rad=n_yaw,
                        max_speed_mps=v,
                        gait_style="walk",
                    )

        return best_target
