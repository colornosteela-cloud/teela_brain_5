"""Simple object tracker using IoU-based matching."""

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass
class TrackedObject:
    track_id: int
    class_name: str
    bbox: tuple[float, float, float, float]
    depth: float
    confidence: float
    age: int = 0  # frames since last update


class ObjectTracker:
    """Very simple tracker: nearest-neighbour + IoU gating.
    Replace with DeepSORT / ByteTrack / Bot-SORT for production."""

    _next_id = 1

    def __init__(self, iou_threshold: float = 0.3, max_age: int = 5):
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.tracks: Dict[int, TrackedObject] = {}

    @staticmethod
    def _iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        x1a, y1a, x2a, y2a = a
        x1b, y1b, x2b, y2b = b
        xi1, yi1 = max(x1a, x1b), max(y1a, y1b)
        xi2, yi2 = min(x2a, x2b), min(y2a, y2b)
        inter_w = max(0.0, xi2 - xi1)
        inter_h = max(0.0, yi2 - yi1)
        inter = inter_w * inter_h
        area_a = (x2a - x1a) * (y2a - y1a)
        area_b = (x2b - x1b) * (y2b - y1b)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def update(self, detections: List[TrackedObject]) -> List[TrackedObject]:
        """Match detections to existing tracks, create new tracks, age out dead ones."""
        matched: Dict[int, int] = {}
        unmatched_dets = list(range(len(detections)))

        if self.tracks:
            track_ids = list(self.tracks.keys())
            iou_mat = np.zeros((len(detections), len(track_ids)))
            for i, det in enumerate(detections):
                for j, tid in enumerate(track_ids):
                    iou_mat[i, j] = self._iou(det.bbox, self.tracks[tid].bbox)
            while iou_mat.size > 0:
                i, j = np.unravel_index(np.argmax(iou_mat), iou_mat.shape)
                if iou_mat[i, j] < self.iou_threshold:
                    break
                tid = track_ids[j]
                matched[tid] = i
                iou_mat[i, :] = -1
                iou_mat[:, j] = -1
                unmatched_dets.remove(i)

        # Update matched tracks
        for tid, det_i in matched.items():
            self.tracks[tid] = TrackedObject(
                track_id=tid,
                class_name=detections[det_i].class_name,
                bbox=detections[det_i].bbox,
                depth=detections[det_i].depth,
                confidence=detections[det_i].confidence,
                age=0,
            )

        # Age unmatched tracks
        for tid in list(self.tracks.keys()):
            if tid not in matched:
                self.tracks[tid].age += 1
                if self.tracks[tid].age > self.max_age:
                    del self.tracks[tid]

        # Create new tracks for unmatched detections
        for i in unmatched_dets:
            det = detections[i]
            nid = ObjectTracker._next_id
            ObjectTracker._next_id += 1
            self.tracks[nid] = TrackedObject(
                track_id=nid,
                class_name=det.class_name,
                bbox=det.bbox,
                depth=det.depth,
                confidence=det.confidence,
                age=0,
            )

        return list(self.tracks.values())
