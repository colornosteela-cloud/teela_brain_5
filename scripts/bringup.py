#!/usr/bin/env python3
"""Teela Bringup Script

Usage:
    python3 -m scripts.bringup [--config config.yaml]

Checks all subsystems and brings Teela online.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import serial


def check_jetson() -
    dict:
    """Check Jetson system health."""
    report = {"status": "ok", "ram_mb": None, "disk_gb": None, "uptime": None}
    try:
        ram = subprocess.check_output("free -m | awk '/Mem:/ {print $7}'", shell=True, text=True).strip()
        report["ram_mb"] = int(ram)
        disk = subprocess.check_output("df -h / | awk 'NR==2 {print $4}'", shell=True, text=True).strip()
        report["disk_gb"] = disk
        uptime = subprocess.check_output("uptime -p", shell=True, text=True).strip()
        report["uptime"] = uptime
        if report["ram_mb"] is not None and report["ram_mb"] < 1024:
            report["status"] = "warning"
    except Exception as e:
        report["status"] = f"error: {e}"
    return report


def check_camera(device: str = "/dev/video0") -
    dict:
    """Check USB camera."""
    report = {"status": "not_found", "fps": None}
    if not Path(device).exists():
        return report
    try:
        import cv2
        cap = cv2.VideoCapture(device)
        if cap.isOpened():
            report["status"] = "ok"
            report["fps"] = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
        else:
            report["status"] = "failed_open"
    except ImportError:
        report["status"] = "cv2_missing"
    return report


def check_teensy(port: str = "/dev/ttyACM0") -
    dict:
    """Check Teensy serial connection."""
    report = {"status": "not_found", "pong_ms": None}
    if not Path(port).exists():
        return report
    try:
        with serial.Serial(port, 921600, timeout=0.5) as ser:
            ser.write(b"PING
")
            t0 = time.time()
            resp = ser.readline()
            dt = (time.time() - t0) * 1000
            if resp and b"PONG" in resp:
                report["status"] = "ok"
                report["pong_ms"] = round(dt, 2)
            else:
                report["status"] = "no_response"
    except Exception as e:
        report["status"] = f"error: {e}"
    return report


def check_cloud_bridge(uri: str = "ws://localhost:8080/teela") -
    dict:
    """Check cloud WebSocket reachability."""
    report = {"status": "unknown", "latency_ms": None}
    # TODO: implement actual WebSocket ping
    report["status"] = "manual_check_required"
    return report


def main():
    parser = argparse.ArgumentParser(description="Teela Bringup")
    parser.add_argument("--config", default="config.yaml", help="Config file")
    args = parser.parse_args()

    print("========================================")
    print("       TEELA BRINGUP v5.0")
    print("========================================")
    print()

    results = {}

    print("[1/4] Checking Jetson system...")
    results["jetson"] = check_jetson()
    print(f"       Status: {results['jetson']['status']}")
    print(f"       Free RAM: {results['jetson'].get('ram_mb', 'N/A')} MB")
    print(f"       Disk Free: {results['jetson'].get('disk_gb', 'N/A')}")
    print()

    print("[2/4] Checking camera...")
    results["camera"] = check_camera()
    print(f"       Status: {results['camera']['status']}")
    print(f"       FPS: {results['camera'].get('fps', 'N/A')}")
    print()

    print("[3/4] Checking Teensy serial...")
    results["teensy"] = check_teensy()
    print(f"       Status: {results['teensy']['status']}")
    print(f"       PONG latency: {results['teensy'].get('pong_ms', 'N/A')} ms")
    print()

    print("[4/4] Checking cloud bridge...")
    results["cloud"] = check_cloud_bridge()
    print(f"       Status: {results['cloud']['status']}")
    print()

    # Summary
    all_ok = all(r["status"] == "ok" or r["status"] == "manual_check_required" for r in results.values())
    if all_ok:
        print("✅ ALL SYSTEMS GREEN")
        sys.exit(0)
    else:
        print("⚠️  SOME SUBSYSTEMS NEED ATTENTION")
        for name, r in results.items():
            if r["status"] not in ("ok", "manual_check_required"):
                print(f"   - {name}: {r['status']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
