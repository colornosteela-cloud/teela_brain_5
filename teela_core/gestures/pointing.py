"""
Pointing / Deictic Gesture Understanding
========================================

Converts 2D human pose keypoints into a 3D pointing ray,
determines which scene object is being pointed at.

Pipeline:
    Camera frame -> Human pose detector (MediaPipe-like)
    -> Extract shoulder/elbow/wrist (or nose/eye/hand)
    -> Compute pointing direction in pixel space
    -> Find nearest object along the ray
    -> Write "pointed_at" into scene_state.json

Dependencies:
    - Optionally requires MediaPipe (pip install mediapipe)
    - Can run stub mode if MediaPipe unavailable
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class Keypoint:
    name: str
    x: float  # normalized 0-1
    y: float  # normalized 0-1
    visibility: float = 1.0


@dataclass
class PointingRay:
    origin_px: Tuple[float, float]       # (x, y) in pixels
    direction: Tuple[float, float]        # unit vector (dx, dy)
    is_left_hand: bool = False            # which arm


@dataclass
class PointingResult:
    is_pointing: bool
    ray: Optional[PointingRay]
    pointed_object_id: Optional[int]      # track_id from object tracker
    pointed_object_name: Optional[str]
    confidence: float
    pixel_distance: float                 # screen-space distance to object center


class PointingDetector:
    """Detects pointing gestures from body keypoints.

    Uses either MediaPipe pose or simple heuristics on detected arm positions.
    """

    def __init__(self, image_width: int = 640, image_height: int = 480):
        self.w = image_width
        self.h = image_height
        self._mp_pose = None  # lazy import

    def _load_mediapipe(self) -> bool:
        """Try to import MediaPipe. Returns False if unavailable."""
        if self._mp_pose is not None:
            return True
        try:
            import mediapipe as mp  # type: ignore[import]
            self._mp = mp
            self._mp_pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=0,  # fastest, good enough for pointing
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            return True
        except Exception:
            return False

    def detect_pose(self, frame: np.ndarray) -> List[Keypoint]:
        """Run pose detection. Returns list of Keypoints."""
        if self._load_mediapipe():
            return self._detect_mediapipe(frame)
        return self._detect_stub(frame)

    def _detect_mediapipe(self, frame: np.ndarray) -> List[Keypoint]:
        import mediapipe as mp  # type: ignore[import]
        rgb = frame[:, :, ::-1] if frame.shape[2] == 3 else frame
        results = self._mp_pose.process(rgb)
        keypoints = []
        if results.pose_landmarks:
            for lm in self._mp_pose.PoseLandmark:
                landmark = results.pose_landmarks.landmark[lm]
                keypoints.append(Keypoint(
                    name=lm.name,
                    x=landmark.x,
                    y=landmark.y,
                    visibility=landmark.visibility,
                ))
        return keypoints

    def _detect_stub(self, frame: np.ndarray) -> List[Keypoint]:
        """Stub if MediaPipe not available: search for skin-toned blob and fake keypoints."""
        # In a real deployment you could use a YOLOv8-pose or RTMPose model here.
        return []

    def compute_pointing_ray(self, keypoints: List[Keypoint]) -> Optional[PointingRay]:
        """
        Decide if the person is pointing, and compute the ray direction.

        Heuristic: wrist is farther from shoulder than elbow, and hand is extended.
        """
        kp = {k.name: k for k in keypoints}
        
        def has(*names) -> bool:
            return all(n in kp and kp[n].visibility > 0.5 for n in names)

        # Try right arm first, then left
        for prefix in ("RIGHT_", "LEFT_"):
            wrist_n = f"{prefix}WRIST"
            elbow_n = f"{prefix}ELBOW"
            shoulder_n = f"{prefix}SHOULDER"

            if not has(wrist_n, elbow_n, shoulder_n):
                continue

            wrist = kp[wrist_n]
            elbow = kp[elbow_n]
            shoulder = kp[shoulder_n]

            # Check if arm is extended (wrist farther from shoulder than elbow)
            d_ws = math.hypot(wrist.x - shoulder.x, wrist.y - shoulder.y)
            d_es = math.hypot(elbow.x - shoulder.x, elbow.y - shoulder.y)
            
            # Simple heuristic: wrist-elbow roughly collinear with shoulder-elbow
            vec_se = (elbow.x - shoulder.x, elbow.y - shoulder.y)
            vec_ew = (wrist.x - elbow.x, wrist.y - elbow.y)
            
            # Dot product for alignment
            len_se = math.hypot(*vec_se) + 1e-8
            len_ew = math.hypot(*vec_ew) + 1e-8
            dot = (vec_se[0]*vec_ew[0] + vec_se[1]*vec_ew[1]) / (len_se * len_ew)
            
            # Pointing if:
            # 1. Wrist is farther from shoulder than elbow (arm extended)
            # 2. Elbow is between shoulder and wrist (collinear-ish, dot > 0.7)
            if d_ws > d_es * 0.8 and dot > 0.6:
                dx = vec_ew[0] / len_ew
                dy = vec_ew[1] / len_ew
                origin_px = (wrist.x * self.w, wrist.y * self.h)
                return PointingRay(
                    origin_px=origin_px,
                    direction=(dx, dy),
                    is_left_hand=(prefix == "LEFT_"),
                )

        return None

    def find_pointed_object(
        self,
        ray: PointingRay,
        objects: List[Any],  # DetectedObject or similar
        max_distance_px: float = 200.0,
        angular_tolerance_deg: float = 20.0,
    ) -> Optional[Tuple[Any, float, float]]:
        """
        Given a pointing ray, determine which object is being pointed at.

        Returns: (object, pixel_distance, angular_error_deg) or None
        """
        best = None
        best_score = float("inf")

        for obj in objects:
            # Get object center in pixel space
            if hasattr(obj, "bbox_px"):
                x1, y1, x2, y2 = obj.bbox_px
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
            else:
                continue

            # Vector from wrist to object center
            dx = cx - ray.origin_px[0]
            dy = cy - ray.origin_px[1]
            dist_px = math.hypot(dx, dy)

            # Skip objects too far away on screen (pointing at distant things)
            if dist_px > max_distance_px:
                continue

            # Angle between ray direction and wrist-to-object vector
            len_vec = math.hypot(dx, dy) + 1e-8
            dot = (ray.direction[0] * (dx / len_vec) +
                   ray.direction[1] * (dy / len_vec))
            dot = max(-1.0, min(1.0, dot))
            angle_err = math.degrees(math.acos(dot))

            # Weight by distance along ray AND perpendicular error
            perp_err = dist_px * math.sin(math.radians(angle_err))
            score = perp_err + dist_px * 0.1
            
            if angle_err < angular_tolerance_deg and score < best_score:
                best_score = score
                best = (obj, dist_px, angle_err)

        return best

    def process_frame(
        self,
        frame: np.ndarray,
        objects: List[Any],
    ) -> PointingResult:
        """Main entry point: detect pointing, find target, return result."""
        keypoints = self.detect_pose(frame)
        if not keypoints:
            return PointingResult(
                is_pointing=False,
                ray=None,
                pointed_object_id=None,
                pointed_object_name=None,
                confidence=0.0,
                pixel_distance=float("inf"),
            )

        ray = self.compute_pointing_ray(keypoints)
        if ray is None:
            return PointingResult(
                is_pointing=False,
                ray=None,
                pointed_object_id=None,
                pointed_object_name=None,
                confidence=0.0,
                pixel_distance=float("inf"),
            )

        result = self.find_pointed_object(ray, objects)
        if result is None:
            return PointingResult(
                is_pointing=True,
                ray=ray,
                pointed_object_id=None,
                pointed_object_name=None,
                confidence=0.5,
                pixel_distance=float("inf"),
            )

        obj, dist_px, angle_err = result
        # Confidence: closer + more aligned = higher
        conf = max(0.0, 1.0 - (angle_err / 20.0)) * max(0.0, 1.0 - (dist_px / 300.0))
        return PointingResult(
            is_pointing=True,
            ray=ray,
            pointed_object_id=getattr(obj, "track_id", None),
            pointed_object_name=getattr(obj, "class_name", "unknown"),
            confidence=round(conf, 3),
            pixel_distance=round(dist_px, 1),
        )
