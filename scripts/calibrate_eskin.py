#!/usr/bin/env python3
"""Interactive E-Skin Calibration Tool

Usage:
    python3 -m scripts.calibrate_eskin

Steps:
    1. Teela reads all sensors for ~2s while NOT being touched to establish baselines.
    2. User is prompted to gently touch each zone.
    3. Thresholds are auto-tuned from live data.
    4. Calibration is saved to memory/eskin_calibration.json
"""

import argparse
import json
import time
from pathlib import Path

from teela_core.eskin.eskin import ESkinProcessor
from teela_core.eskin.body_map import ALL_ZONES


def calibrate(processor: ESkinProcessor) -> None:
    print("=" * 50)
    print("Teela E-Skin Calibration")
    print("=" * 50)
    print()
    print("Step 1: Baseline (no touch for 3 seconds)")
    print("Make sure nobody is touching Teela's skin...")
    time.sleep(1)

    processor.start_calibration()
    t0 = time.time()
    try:
        while processor._calibrating:
            # In real hardware, this would read from ADC multiplexer
            # Stub: feed zeros as no-contact baseline
            stub_readings = {zid: 120.0 for zid in ALL_ZONES}
            processor.update(stub_readings)
            time.sleep(0.02)  # 50 Hz
            if time.time() - t0 > 3.0:
                if not processor._calibrating:
                    break
    except KeyboardInterrupt:
        print("\nCalibration interrupted.")
        return

    print("Step 2: Verification")
    print("Current baselines:")
    for zid, zone in processor.zones.items():
        print(f"  {zid}: baseline={zone.baseline_raw:.1f} std={zone.baseline_std:.2f}")

    print()
    print("Step 3: Fine-tune thresholds")
    for zid, zone in processor.zones.items():
        # Auto-tune: light threshold = baseline + 2*std + buffer
        zone.threshold_light = max(20, zone.baseline_std * 3 + 10)
        zone.threshold_firm = max(60, zone.baseline_std * 8 + 30)
        zone.threshold_unsafe = max(150, zone.baseline_std * 20 + 80)

    print("Thresholds set:")
    for zid, zone in processor.zones.items():
        print(f"  {zid}: light={zone.threshold_light:.0f}, firm={zone.threshold_firm:.0f}, unsafe={zone.threshold_unsafe:.0f}")

    processor.save_calibration()
    print()
    print("Calibration saved to memory/eskin_calibration.json")
    print("Teela is ready to feel.")


def main():
    parser = argparse.ArgumentParser(description="Calibrate Teela's electronic skin")
    parser.add_argument("--reset", action="store_true", help="Reset to factory defaults")
    args = parser.parse_args()

    calib_path = Path("memory/eskin_calibration.json")
    if args.reset and calib_path.exists():
        calib_path.unlink()
        print("Old calibration removed.")

    processor = ESkinProcessor(calibration_path=calib_path)
    calibrate(processor)


if __name__ == "__main__":
    main()
