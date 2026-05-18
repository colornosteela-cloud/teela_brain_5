"""Real hardware camera interface for Jetson.

Uses OpenCV to read from USB / CSI cameras.
Supports single camera or dual-camera (stereo eyes) configurations.

The SceneUnderstanding module consumes frames from the primary camera.
The secondary camera can support depth estimation or room awareness.
"""

import threading
import time

import cv2
import numpy as np


class RealCamera:
    """Thread-safe camera capture with auto-reopen on failure.

    This represents one physical camera — one of Teela's "eyes".
    Two RealCamera instances combined make StereoCamera (both eyes).
    """

    def __init__(
        self,
        device: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 15,
    ):
        self.device = device
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
        # Try GStreamer backend for Jetson CSI cameras
        # If V4L2 backend, this might silently fail; OpenCV will still read
        try:
            self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        except:
            pass
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
                        print(f"[Camera /dev/video{self.device}] Giving up after 10 failed reopens.")
                        break
                    continue
                else:
                    consecutive_fails = 0

            ret, frame = self._cap.read()
            if not ret or frame is None:
                consecutive_fails += 1
                if consecutive_fails > 5:
                    if self._cap:
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
        print(f"[Camera /dev/video{self.device}] Capture thread started.")

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._cap:
            self._cap.release()
        print(f"[Camera /dev/video{self.device}] Stopped.")


class StereoCamera:
    """Dual-camera (stereo) wrapper for Jetson CSI pair.

    Teela's left and right eyes. Used for:
    - Wider field of view (dual cameras, not necessarily stereo processing)
    - Stereo depth estimation (future)
    - Room awareness (one camera face-tracking, one room-wide)

    Only creates secondary camera if configured.
    """

    def __init__(
        self,
        primary_device: int = 0,
        secondary_device: int | None = None,
        width: int = 640,
        height: int = 480,
        fps: int = 15,
    ):
        self.primary = RealCamera(device=primary_device, width=width, height=height, fps=fps)
        self.left_eye = self.primary  # alias
        self.is_primary_running = False

        self.secondary = None
        self.right_eye = None  # alias
        self.is_secondary_running = False

        if secondary_device is not None:
            self.secondary = RealCamera(device=secondary_device, width=width, height=height, fps=fps)
            self.right_eye = self.secondary  # alias

    def start(self) -> None:
        self.primary.start()
        self.is_primary_running = True
        if self.secondary:
            self.secondary.start()
            self.is_secondary_running = True
            print("[StereoCamera] Both eyes open (dual camera).")
        else:
            print("[StereoCamera] One eye open (single camera).")

    def get_left_frame(self) -> np.ndarray | None:
        """Get frame from left eye (primary camera)."""
        return self.left_eye.get_frame()

    def get_right_frame(self) -> np.ndarray | None:
        """Get frame from right eye (secondary camera), or None if not configured."""
        if self.right_eye is None:
            return None
        return self.right_eye.get_frame()

    def get_stereo_frames(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Get both left and right frames simultaneously.
        Returns (left, right) — right is None if only one camera."""
        return self.get_left_frame(), self.get_right_frame()

    def stop(self) -> None:
        self.left_eye.stop()
        self.is_primary_running = False
        if self.right_eye:
            self.right_eye.stop()
            self.is_secondary_running = False
        print("[StereoCamera] Stopped.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test camera(s) on Jetson.")
    parser.add_argument("--primary", type=int, default=0, help="Primary camera /dev/video index (default 0)")
    parser.add_argument("--secondary", type=int, default=None, help="Secondary camera /dev/video index (omit for single)")
    args = parser.parse_args()

    cam = StereoCamera(primary_device=args.primary, secondary_device=args.secondary)
    cam.start()

    print("Press ESC in the window to quit.")
    cv2.namedWindow("Teela Eye Test", cv2.WINDOW_NORMAL)

    try:
        while True:
            left = cam.get_left_frame()
            right = cam.get_right_frame()

            if left is None and right is None:
                time.sleep(0.1)
                continue

            # Combine side-by-side if dual
            if right is not None:
                # Resize to same size before concatenation
                h1, w1 = left.shape[:2]
                h2, w2 = right.shape[:2]
                if (h1, w1) != (h2, w2):
                    right = cv2.resize(right, (w1, h1))
                combined = np.hstack([left, right])
                label = "Left Eye | Right Eye"
            else:
                combined = left if left is not None else np.zeros((480, 640, 3), dtype=np.uint8)
                label = "Single Eye"

            cv2.putText(combined, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow("Teela Eye Test", combined)

            if cv2.waitKey(1) == 27:  # ESC
                break
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()
        cv2.destroyAllWindows()
