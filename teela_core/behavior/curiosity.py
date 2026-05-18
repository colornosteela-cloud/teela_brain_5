"""
Curiosity Drive: Internal motivation to explore and learn

Teela gets "bored" when she encounters no novel stimuli for a while.
Boredom drives her to:
    - Look around (scan gaze)
    - Move to a different vantage point
    - Ask questions
    - Explore a region she hasn't mapped well

This is the intrinsic motivation engine — no external reward needed.
"""

import math
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class NoveltySignal:
    source: str  # "visual", "audio", "social", "spatial"
    intensity: float  # 0-1
    position: Optional[Tuple[float, float, float]] = None
    description: str = ""


class CuriosityDrive:
    """Generates exploratory behavior from novelty-seeking."""

    NOVELTY_DECAY = 0.95  # per minute
    BOREDOM_GROWTH_RATE = 0.02  # per minute when unstimulated
    
    def __init__(self, grid_size: Tuple[int, int] = (100, 100), grid_res_m: float = 0.1):
        self.exploration_map = {}  # (gx, gy) -> visit_count
        self.novelty_history: List[NoveltySignal] = []
        self.boredom = 0.0  # 0 = engaged, 1 = very bored
        self._last_update = time.time()

    def update(
        self,
        current_position: Tuple[float, float, float],
        detected_objects: List[Dict],
        pointed_at: Optional[Dict] = None,
    ) -> Dict:
        """Step curiosity forward. Returns internal state."""
        now = time.time()
        dt_min = (now - self._last_update) / 60.0
        self._last_update = now

        # 1. Mark current position as visited
        gx = int(current_position[0] / 0.1)
        gy = int(current_position[1] / 0.1)
        self.exploration_map[(gx, gy)] = self.exploration_map.get((gx, gy), 0) + 1

        # 2. Compute novelty from detected objects
        novelty = 0.0
        for obj in detected_objects:
            if obj.get("track_id") is not None:
                # New objects are more novel
                novelty += max(0, 1.0 - obj.get("age_frames", 0) / 30.0)

        # 3. Update boredom
        if novelty > 0.3:
            self.boredom = max(0.0, self.boredom - novelty * 0.5)
        else:
            self.boredom = min(1.0, self.boredom + self.BOREDOM_GROWTH_RATE * dt_min)

        # 4. If very bored, suggest exploration target
        exploration_target = None
        if self.boredom > 0.6:
            exploration_target = self._find_unexplored_target(current_position)

        return {
            "boredom": round(self.boredom, 3),
            "novelty": round(novelty, 3),
            "exploration_target": exploration_target,
            "map_coverage": self._compute_coverage(),
        }

    def _find_unexplored_target(
        self,
        current_pos: Tuple[float, float, float],
        search_radius_cells: int = 20,
    ) -> Optional[Tuple[float, float]]:
        """Find nearest unvisited or lightly visited cell."""
        cx = int(current_pos[0] / 0.1)
        cy = int(current_pos[1] / 0.1)
        
        best = None
        best_score = float("inf")
        
        for dx in range(-search_radius_cells, search_radius_cells + 1):
            for dy in range(-search_radius_cells, search_radius_cells + 1):
                gx, gy = cx + dx, cy + dy
                visits = self.exploration_map.get((gx, gy), 0)
                if visits < 2:  # unvisited or barely visited
                    dist = math.hypot(dx, dy)
                    # Prefer closer, less visited
                    score = dist + visits * 10
                    if score < best_score:
                        best_score = score
                        best = (gx * 0.1, gy * 0.1)
        
        return best

    def _compute_coverage(self) -> float:
        if not self.exploration_map:
            return 0.0
        visited = sum(1 for v in self.exploration_map.values() if v >= 1)
        total = len(self.exploration_map)
        return visited / max(total, 1)
