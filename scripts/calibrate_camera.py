#!/usr/bin/env python3
"""Camera calibration utility."""

import argparse
from pathlib import Path

import cv2
import numpy as np


def collect_images(camera_index: int, output_dir: str, frames_to_capture: int = 20) -
    None:
    """Collect checkerboard images for calibration."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera {camera_index}")

    count = 0
    while count < frames_to_capture:
        ret, frame = cap.read()
        if not ret:
            continue
        cv2.imshow("Calibration", frame)
        key = cv2.waitKey(1)
        if key == ord(" "):
            path = out / f"calib_{count:03d}.png"
            cv2.imwrite(str(path), frame)
            print(f"Saved {path}")
            count += 1
        elif key == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()


def calibrate(pattern_size: tuple[int, int], image_dir: str, square_size_m: float = 0.025) -
    dict:
    """Run OpenCV calibration on collected images."""
    objp = np.zeros((pattern_size[0] * pattern_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern_size[0], 0:pattern_size[1]].T.reshape(-1, 2) * square_size_m

    objpoints, imgpoints = [], []
    for img_path in sorted(Path(image_dir).glob("*.png")):
        img = cv2.imread(str(img_path))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret, corners = cv2.findChessboardCorners(gray, pattern_size, None)
        if ret:
            objpoints.append(objp)
            imgpoints.append(corners)
            print(f"  Found corners in {img_path.name}")

    if len(objpoints) < 3:
        raise ValueError("Not enough valid calibration images")

    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None, None)
    print(f"Reprojection error: {ret:.4f}")
    return {"camera_matrix": mtx.tolist(), "dist_coeffs": dist.tolist(), "error": ret}


def main():
    parser = argparse.ArgumentParser(description="Camera calibration")
    parser.add_argument("--collect", action="store_true", help="Collect images")
    parser.add_argument("--calibrate", action="store_true", help="Run calibration")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--out-dir", default="calibration_data")
    parser.add_argument("--pattern", default="9x6", help="Checkerboard pattern WxH")
    parser.add_argument("--square-size", type=float, default=0.025)
    args = parser.parse_args()

    w, h = map(int, args.pattern.split("x"))
    if args.collect:
        collect_images(args.camera, args.out_dir)
    if args.calibrate:
        result = calibrate((w, h), args.out_dir, args.square_size)
        import json
        Path("camera_intrinsics.json").write_text(json.dumps(result, indent=2))
        print("Wrote camera_intrinsics.json")


if __name__ == "__main__":
    main()
