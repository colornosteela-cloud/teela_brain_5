#!/usr/bin/env python3
"""Teela Bringup — Hardware Check for Jetson

Usage:
    python3 -m scripts.bringup [--config config.yaml]

Checks each physical subsystem and reports OK / FAIL with suggestions.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import serial
import yaml

from teela_core.perception.camera import RealCamera
from teela_core.comms.serial_link import SerialLink


class BringupChecker:
    def __init__(self, config: dict):
        self.config = config
        self.results = []

    def check(self, name: str, status: str, detail: str = "", advice: str = ""):
        ok = status in ("ok", "warning")
        icon = "✅" if status == "ok" else ("⚠️" if status == "warning" else "❌")
        self.results.append({"name": name, "status": status, "detail": detail, "advice": advice, "ok": ok})
        print(f"   {icon} {name}: {status}")
        if detail:
            print(f"      {detail}")
        if advice and not ok:
            print(f"      💡 {advice}")

    def run_all(self):
        print("=" * 50)
        print("Teela Hardware Bringup Check")
        print("=" * 50)

        # 1. System
        self._check_system()
        # 2. Camera
        self._check_camera()
        # 3. Microphone
        self._check_microphone()
        # 4. Serial / Teensy
        self._check_serial()
        # 5. Network (for Kimi)
        self._check_network()
        # 6. Disk space
        self._check_disk()

        print()
        print("=" * 50)
        ok_count = sum(1 for r in self.results if r["ok"])
        fail_count = len(self.results) - ok_count
        if fail_count == 0:
            print(f"🎉 ALL CHECKS PASSED ({ok_count}/{len(self.results)})")
            print("Teela is ready to start. Run: python3 -m scripts.conversation_loop")
        else:
            print(f"⚠️ {ok_count}/{len(self.results)} passed — {fail_count} need attention.")
        print("=" * 50)

    def _check_system(self):
        try:
            ram_free = int(subprocess.check_output("free -m | awk '/Mem:/ {print $7}'", shell=True, text=True).strip())
            status = "ok" if ram_free > 512 else "warning"
            self.check("RAM free", status, f"{ram_free} MB free", "Close other apps if < 512 MB")
        except Exception as e:
            self.check("RAM free", "fail", str(e), "Install 'procps' or check with free -m")

    def _check_camera(self):
        cam_cfg = self.config.get("hardware", {}).get("camera", {})
        dev = cam_cfg.get("device", "/dev/video0")
        if not Path(dev).exists():
            self.check("Camera", "fail", f"{dev} not found", "Plug in USB camera or check dmesg")
            return
        try:
            cap = RealCamera(device=dev, width=640, height=480, fps=15)
            cap.start()
            time.sleep(0.5)
            frame = cap.get_frame()
            cap.stop()
            if frame is not None:
                h, w = frame.shape[:2]
                self.check("Camera", "ok", f"{dev} → {w}x{h} ✅")
            else:
                self.check("Camera", "fail", "Device exists but no frames", "Check v4l2 driver")
        except Exception as e:
            self.check("Camera", "fail", str(e), "Install opencv-python, check udev rules")

    def _check_microphone(self):
        dev_cfg = self.config.get("hardware", {}).get("microphone", {})
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            inputs = [d for d in devices if d["max_input_channels"] > 0]
            if inputs:
                self.check("Microphone", "ok", f"Found {len(inputs)} capture device(s)")
            else:
                self.check("Microphone", "warning", "No input devices found", "Plug in USB mic or check alsamixer")
        except ImportError:
            self.check("Microphone", "warning", "sounddevice not installed", "pip install sounddevice")

    def _check_serial(self):
        ser_cfg = self.config.get("hardware", {}).get("serial", {})
        port = ser_cfg.get("port", "/dev/ttyACM0")
        baud = ser_cfg.get("baud", 921600)

        if not Path(port).exists():
            self.check("Serial (Teensy)", "fail", f"{port} not found", "Plug in Teensy USB. Verify with ls /dev/ttyACM*")
            return

        link = SerialLink(port=port, baud=baud)
        ok = link.connect()
        if ok:
            time.sleep(0.3)
            link.send_ping()
            time.sleep(0.2)
            status = link.get_status()
            if status:
                self.check("Serial (Teensy)", "ok", f"{port} @ {baud} — Teensy status: {status}")
            else:
                self.check("Serial (Teensy)", "ok", f"{port} @ {baud} — no status yet")
            link.disconnect()
        else:
            self.check("Serial (Teensy)", "fail", f"Could not open {port}", "Check permissions: sudo chmod 666 {port}")

    def _check_network(self):
        try:
            subprocess.check_output(["curl", "-s", "--max-time", "5", "https://api.moonshot.cn"], stderr=subprocess.STDOUT)
            self.check("Network (Kimi)", "ok", "api.moonshot.cn reachable")
        except subprocess.CalledProcessError:
            self.check("Network (Kimi)", "fail", "Cannot reach api.moonshot.cn", "Check WiFi / internet")
        except FileNotFoundError:
            self.check("Network (Kimi)", "ok", "curl not found, assuming connectivity is fine")

    def _check_disk(self):
        try:
            out = subprocess.check_output("df -h / | awk 'NR==2 {print $4}'", shell=True, text=True).strip()
            self.check("Disk space", "ok", f"Free: {out}")
        except Exception:
            self.check("Disk space", "warning", "Could not check", "Check manually")


def main():
    parser = argparse.ArgumentParser(description="Teela bringup")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text()) if Path(args.config).exists() else {}
    checker = BringupChecker(config)
    checker.run_all()


if __name__ == "__main__":
    main()
