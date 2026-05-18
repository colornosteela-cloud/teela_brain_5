"""Integration: pointing detector wired into the scene understanding pipeline.

Usage:
    from teela_core.gestures.pointing_integration import PointingSceneIntegrator
    integrator = PointingSceneIntegrator()
    integrator.update_scene_state(frame, scene_state)

This module connects the PointingDetector with the SceneState so that
every scene_state.json emitted by the perception loop includes what
(if anything) the user is pointing at.
"""

from pathlib import Path
from typing import List, Optional

import numpy as np

from teela_core.gestures.pointing import PointingDetector, PointingResult
from teela_core.perception.scene_understanding import SceneState, DetectedObject
from teela_core.perception.object_tracker import ObjectTracker, TrackedObject


class PointingSceneIntegrator:
    """Wires pointing detection into scene state updates."""

    def __init__(
        self,
        image_width: int = 640,
        image_height: int = 480,
        confidence_threshold: float = 0.4,
    ):
        self.detector = PointingDetector(image_width=image_width, image_height=image_height)
        self.confidence_threshold = confidence_threshold

    def update_scene_state(
        self,
        frame: np.ndarray,
        scene_state: SceneState,
    ) -> SceneState:
        """Mutate scene_state in-place with pointed_at information."""
        pointing_result = self.detector.process_frame(frame, scene_state.objects)

        if pointing_result.is_pointing and pointing_result.confidence >= self.confidence_threshold:
            if pointing_result.pointed_object_id is not None:
                scene_state.pointed_at = {
                    "object_id": pointing_result.pointed_object_id,
                    "name": pointing_result.pointed_object_name,
                    "confidence": pointing_result.confidence,
                    "pixel_distance": pointing_result.pixel_distance,
                    "is_left_hand": pointing_result.ray.is_left_hand if pointing_result.ray else False,
                }
                scene_state.caption = f"Person pointing at {pointing_result.pointed_object_name}"
            else:
                # Pointing detected but no object matched — might be pointing at empty space
                scene_state.pointed_at = {
                    "object_id": None,
                    "name": None,
                    "confidence": pointing_result.confidence,
                    "pixel_distance": None,
                    "is_left_hand": pointing_result.ray.is_left_hand if pointing_result.ray else False,
                }
                scene_state.caption = "Person pointing"
        else:
            scene_state.pointed_at = None

        return scene_state
