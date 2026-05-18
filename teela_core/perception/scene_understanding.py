"""Scene Understanding: V-JEPA 2 + optional Moondream2 for scene_state.json generation."""

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any

import numpy as np


@dataclass
class DetectedObject:
    """A thing in the world."""
    class_name: str
    bbox_px: tuple[float, float, float, float]  # x1, y1, x2, y2
    depth_m: float = -1.0
    velocity_mps: tuple[float, float, float] = (0.0, 0.0, 0.0)
    confidence: float = 1.0
    track_id: Optional[int] = None


@dataclass
class SceneState:
    """Snapshot of what Teela perceives, written to scene_state.json."""
    timestamp: float = field(default_factory=time.time)
    frame_idx: int = 0
    objects: List[DetectedObject] = field(default_factory=list)
    obstacles: List[DetectedObject] = field(default_factory=list)
    navigable_path: Optional[List[tuple[float, float, float]]] = None
    self_pose: tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    caption: str = ""
    safety_status: str = "nominal"  # nominal | caution | emergency
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self, path: Path) -> None:
        """Serialize to scene_state.json consumable by cloud reasoning."""
        d = asdict(self)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, indent=2))

    @classmethod
    def from_json(cls, path: Path) -> "SceneState":
        return cls(**json.loads(path.read_text()))


class SceneUnderstanding:
    """High-level perception orchestrator.

    Architecture:
        Camera -> V-JEPA 2 feature extractor -> optional Moondream caption
        -> object tracking -> depth estimation -> SceneState json
    """

    def __init__(
        self,
        camera_index: int = 0,
        vjepa_model: Optional[str] = "facebook/v-jepa-2",
        moondream_model: Optional[str] = None,
        output_path: Path = Path("/tmp/scene_state.json"),
        target_fps: float = 10.0,
    ):
        self.camera_index = camera_index
        self.vjepa_model_name = vjepa_model
        self.moondream_model_name = moondream_model
        self.output_path = output_path
        self.target_fps = target_fps
        self.frame_period = 1.0 / target_fps

        # These are loaded lazily to avoid import-time side effects on laptop
        self._vjepa: Any = None
        self._moondream: Any = None
        self._camera: Any = None
        self._frame_idx = 0

    def load_models(self) -> None:
        """Load V-JEPA 2 (and optionally Moondream2). Call once after import."""
        import cv2  # type: ignore[import]
        from transformers import AutoModel, AutoProcessor  # type: ignore[import]

        self._camera = cv2.VideoCapture(self.camera_index)
        if not self._camera.isOpened():
            raise RuntimeError(f"Cannot open camera {self.camera_index}")

        if self.vjepa_model_name:
            # V-JEPA 2: video world model / feature backbone
            self._vjepa = AutoModel.from_pretrained(self.vjepa_model_name, trust_remote_code=True)
            # For full world model predictions, also:
            # self._vjepa_processor = AutoProcessor.from_pretrained(...)
            # Here we use V-JEPA features as a perception backbone.

        if self.moondream_model_name:
            self._moondream = AutoModel.from_pretrained(
                self.moondream_model_name, trust_remote_code=True
            )
            self._moondream_processor = AutoProcessor.from_pretrained(
                self.moondream_model_name, trust_remote_code=True
            )

    def capture(self) -> Optional[np.ndarray]:
        """Grab a single frame."""
        if self._camera is None:
            return None
        ret, frame = self._camera.read()
        return frame if ret else None

    def process_frame(self, frame: np.ndarray) -> SceneState:
        """Run V-JEPA + optional Moondream -> SceneState."""
        h, w = frame.shape[:2]
        now = time.time()
        self._frame_idx += 1

        # --- V-JEPA 2: spatiotemporal features, action anticipation ---
        # In a real deployment, you buffer N frames and run V-JEPA forward prediction.
        # Here we stub the object detection / segmentation pipeline.
        objects: List[DetectedObject] = []
        caption = ""

        if self._vjepa is not None:
            # TODO: implement actual V-JEPA prediction heads
            # For now, mark that the model is active.
            objects = self._dummy_detect(frame)

        # --- Moondream 2: captioning / spatial reasoning ---
        if self._moondream is not None:
            # caption = self._moondream.caption(...)   # stub
            caption = "scene_with_objects"  # placeholder

        # --- Spatial reasoning: classify objects into obstacles vs free ---
        obstacles = [o for o in objects if o.class_name in {"person", "wall", "chair", "table"}]
        navigable = self._estimate_navigable_path(frame, obstacles, w, h)

        state = SceneState(
            timestamp=now,
            frame_idx=self._frame_idx,
            objects=objects,
            obstacles=obstacles,
            navigable_path=navigable,
            self_pose=self._estimate_self_pose(),
            caption=caption,
            safety_status=self._safety_check(obstacles),
        )
        state.to_json(self.output_path)
        return state

    def loop(self) -> None:
        """Blocking perception loop. Runs until KeyboardInterrupt."""
        self.load_models()
        try:
            while True:
                t0 = time.time()
                frame = self.capture()
                if frame is not None:
                    self.process_frame(frame)
                sleep = self.frame_period - (time.time() - t0)
                if sleep > 0:
                    time.sleep(sleep)
        except KeyboardInterrupt:
            if self._camera:
                self._camera.release()

    # --- Helpers (stubs to be replaced with real CV) ---

    def _dummy_detect(self, frame: np.ndarray) -> List[DetectedObject]:
        """Replace with real V-JEPA detection / tracking heads."""
        return []

    def _estimate_navigable_path(
        self, frame: np.ndarray, obstacles: List[DetectedObject], w: int, h: int
    ) -> Optional[List[tuple[float, float, float]]]:
        """Replace with real A* / DWA path planning or depth-based free-space analysis."""
        # Forward heading, 1m ahead
        return [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]

    def _estimate_self_pose(self) -> tuple[float, float, float, float, float, float]:
        """Replace with odometry / IMU / SLAM fusion."""
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def _safety_check(self, obstacles: List[DetectedObject]) -> str:
        for o in obstacles:
            if o.depth_m > 0 and o.depth_m < 0.5:
                return "emergency"
            if o.depth_m > 0 and o.depth_m < 1.5:
                return "caution"
        return "nominal"
