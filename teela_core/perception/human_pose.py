"""Human pose detection wrapper.

Abstracts MediaPipe / RTMPose / YOLOv8-pose behind a common interface.
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class PoseResult:
    keypoints: List[dict]  # [{"name": "NOSE", "x": 0.5, "y": 0.3, "visibility": 0.9}, ...]
    bbox: tuple[float, float, float, float]
    confidence: float


class HumanPoseDetector:
    """Unified pose detector."""

    def __init__(self, backend: str = "mediapipe"):
        self.backend = backend
        self._model = None

    def _lazy_init(self):
        if self._model is not None:
            return
        if self.backend == "mediapipe":
            import mediapipe as mp  # type: ignore[import]
            self._model = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=0,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        else:
            raise ValueError(f"Unsupported pose backend: {self.backend}")

    def detect(self, frame: np.ndarray) -> Optional[PoseResult]:
        """Detect single human pose in frame."""
        self._lazy_init()
        if frame.shape[2] == 3:
            rgb = frame[:, :, ::-1]
        else:
            rgb = frame
        results = self._model.process(rgb)
        if not results.pose_landmarks:
            return None

        kps = []
        for idx, lm in enumerate(results.pose_landmarks.landmark):
            name = list(self._mp.solutions.pose.PoseLandmark)[idx].name
            kps.append({
                "name": name,
                "x": lm.x,
                "y": lm.y,
                "z": lm.z,
                "visibility": lm.visibility,
            })
        # Rough bbox from landmarks
        xs = [lm["x"] for lm in kps]
        ys = [lm["y"] for lm in kps]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        return PoseResult(keypoints=kps, bbox=bbox, confidence=1.0)
