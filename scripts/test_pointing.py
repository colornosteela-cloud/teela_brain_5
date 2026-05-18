#!/usr/bin/env python3
"""Quick test script for pointing detection.

Usage:
    python3 -m scripts.test_pointing --camera 0

Shows live camera feed with pointing ray and detected objects overlaid.
Requires MediaPipe: pip install mediapipe opencv-python
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from teela_core.gestures.pointing import PointingDetector, PointingResult


def draw_ray(frame, result: PointingResult):
    if not result.is_pointing or result.ray is None:
        return frame
    ox, oy = map(int, result.ray.origin_px)
    dx, dy = result.ray.direction
    ex, ey = int(ox + dx * 200), int(oy + dy * 200)
    cv2.line(frame, (ox, oy), (ex, ey), (0, 255, 0), 3)
    cv2.circle(frame, (ox, oy), 8, (0, 0, 255), -1)

    if result.pointed_object_name:
        label = f"{result.pointed_object_name} ({result.confidence:.0%})"
        cv2.putText(frame, label, (ex + 10, ey), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    return frame


def main():
    parser = argparse.ArgumentParser(description="Test pointing detection")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    detector = PointingDetector(image_width=args.width, image_height=args.height)

    print("=== Pointing Test ===")
    print("Point at objects in the camera view. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Placeholder: no real objects tracked yet, just test pose + ray
        result = detector.process_frame(frame, objects=[])
        frame = draw_ray(frame, result)

        status = (
            f"Pointing: {result.is_pointing} | "
            f"Conf: {result.confidence:.2f} | "
            f"Target: {result.pointed_object_name or 'none'}"
        )
        cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.imshow("Pointing Test", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
