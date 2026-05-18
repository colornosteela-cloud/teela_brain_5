#!/usr/bin/env python3
"""Teela Health Check (lightweight daemon).

Runs continuously. If any subsystem fails, emits alerts.
Can be run as systemd service or cronjob.
"""

import argparse
import json
import time
from pathlib import Path

import schedule

# Import internal modules
from teela_core.comms.serial_link import SerialLink
from teela_core.perception.scene_understanding import SceneState


class HealthMonitor:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.last_scene_time = 0.0
        self.last_telemetry_time = 0.0
        self.health_log_path = Path("logs/health.log")
        self.health_log_path.parent.mkdir(parents=True, exist_ok=True)

    def check_scene_freshness(self) -
        str:
        """Scene state should update every < 1s."""
        now = time.time()
        try:
            ss = SceneState.from_json(Path("/tmp/scene_state.json"))
            if now - ss.timestamp < 1.5:
                return "ok"
            return f"stale ({now - ss.timestamp:.1f}s old)"
        except Exception as e:
            return f"unavailable: {e}"

    def check_telemetry(self) -
        str:
        """Check if Teensy is sending status."""
        # In a real system, read from a shared queue or latest serial line
        return "manual"  # stub

    def log(self, level: str, msg: str) -
        None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}"
        print(line)
        with open(self.health_log_path, "a") as f:
            f.write(line + "
")

    def run_once(self) -
        None:
        scene = self.check_scene_freshness()
        telem = self.check_telemetry()

        if scene == "ok" and telem == "manual":
            self.log("INFO", f"scene={scene} telemetry={telem}")
        else:
            self.log("WARN", f"scene={scene} telemetry={telem}")

    def run_daemon(self, interval_s: float = 5.0) -
        None:
        schedule.every(interval_s).seconds.do(self.run_once)
        while True:
            schedule.run_pending()
            time.sleep(0.1)


def main():
    parser = argparse.ArgumentParser(description="Teela Health Check")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=float, default=5.0, help="Check interval (s)")
    args = parser.parse_args()

    monitor = HealthMonitor()
    if args.once:
        monitor.run_once()
    else:
        monitor.run_daemon(args.interval)


if __name__ == "__main__":
    main()
