"""Real hardware camera interface for Jetson.

Uses OpenCV to read from USB / CSI camera.
The SceneUnderstanding module consumes the frames.
"""

import threading
import time
from pathlib import Path

import cv2
import numpy as np


class RealCamera:
    """Thread-safe camera capture with auto-reopen on failure."""

    def __init__(
        self,
        device: str = "/dev/video0",
        width: int = 640,
        height: int = 480,
        fps: int = 15,
    ):
        self.device = int(device.replace("/dev/video", "")) if "/dev/video" in device else 0
        self.width = width
        self.height = height
        self.fps = fps

        self._cap = None
        self._frame: np.ndarray | None = None
        self._running = False
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

        self._open()

    def _open(self) -> bool:
        """Try to open the camera. Return True on success."""
        if self._cap is not None:
            self._cap.release()
        self._cap = cv2.VideoCapture(self.device)
        if not self._cap.isOpened():
            print(f"[Camera] FAILED to open /dev/video{self.device}")
            return False
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[Camera] Opened /dev/video{self.device} at {actual_w}x{actual_h}")
        return True

    def _capture_loop(self) -> None:
        """Background thread: keep reading frames."""
        consecutive_fails = 0
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                if not self._open():
                    time.sleep(1.0)
                    consecutive_fails += 1
                    if consecutive_fails > 10:
                        print("[Camera] Giving up after 10 failed reopens.")
                        break
                    continue
                else:
                    consecutive_fails = 0

            ret, frame = self._cap.read()
            if not ret or frame is None:
                consecutive_fails += 1
                if consecutive_fails > 5:
                    self._cap.release()
                    self._cap = None
                    time.sleep(0.5)
                continue
            consecutive_fails = 0
            with self._lock:
                self._frame = frame.copy()

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print("[Camera] Capture thread started.")

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._cap:
            self._cap.release()
        print("[Camera] Stopped.")


import time
