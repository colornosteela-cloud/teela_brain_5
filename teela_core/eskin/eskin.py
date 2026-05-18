"""
E-Skin Core: Sensor Processing, Calibration, and Touch Event Pipeline

Reads raw ADC values from Velostat/FSR sensors, applies smoothing and
calibration, classifies pressure by body zone, and emits touch events.

Safety-first: this module runs at high frequency and its HALT/ FREEZE
commands are wired into the reflex layer as hard overrides.
"""

import json
import math
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from teela_core.eskin.body_map import (
    ALL_ZONES, ESkinZone, TOUCH_ADJACENCY_GROUPS, get_adjacent_zones
)


@dataclass
class TouchEvent:
    """A classified touch occurrence on one body zone."""
    event_type: str = "touch"
    zone: str = ""
    intensity: str = "none"
    raw_value: float = 0.0
    baseline: float = 0.0
    delta: float = 0.0
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    safety_level: str = "normal"
    adjacent_joints: List[str] = field(default_factory=list)
    suggested_response: str = "acknowledge"
    # Multi-zone fusion info
    multi_zone_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "event_type": self.event_type,
            "zone": self.zone,
            "intensity": self.intensity,
            "raw_value": round(self.raw_value, 1),
            "baseline": round(self.baseline, 1),
            "delta": round(self.delta, 1),
            "confidence": round(self.confidence, 3),
            "timestamp": self.timestamp,
            "safety_level": self.safety_level,
            "adjacent_joints": self.adjacent_joints,
            "suggested_response": self.suggested_response,
            "multi_zone_ids": self.multi_zone_ids,
        }


class ESkinProcessor:
    """
    High-frequency sensor processor for Teela's electronic skin.

    Call `update(raw_readings)` at ~50-100 Hz (or whenever ADC samples arrive).
    This outputs touch events and safety commands via callbacks.
    """

    SMOOTHING_ALPHA = 0.15   # exponential moving average for raw noise
    EVENT_DEBOUNCE_S = 0.3   # seconds before re-firing same zone
    CALIBRATION_SAMPLES = 200
    UNSAFE_COOLDOWN_S = 1.5  # don't re-fire unsafe after a freeze
    MAX_DELTA_HISTORY = 50

    def __init__(
        self,
        calibration_path: Path = Path("memory/eskin_calibration.json"),
        on_touch_event: Optional[Callable[[TouchEvent], None]] = None,
        on_safety_command: Optional[Callable[[str, str], None]] = None,
    ):
        self.zones = {zid: ESkinZone(
            zone_id=zid,
            display_name=z.display_name,
            parent_region=z.parent_region,
            sensor_ids=z.sensor_ids,
            adjacent_joints=z.adjacent_joints,
            threshold_light=z.threshold_light,
            threshold_firm=z.threshold_firm,
            threshold_unsafe=z.threshold_unsafe,
        ) for zid, z in ALL_ZONES.items()}

        self.calibration_path = calibration_path
        self._callbacks_touch: List[Callable[[TouchEvent], None]] = []
        self._callbacks_safety: List[Callable[[str, str], None]] = []

        if on_touch_event:
            self._callbacks_touch.append(on_touch_event)
        if on_safety_command:
            self._callbacks_safety.append(on_safety_command)

        # Per-zone tracking
        self._raw_history: Dict[str, List[float]] = {zid: [] for zid in self.zones}
        self._last_event_time: Dict[str, float] = {}
        self._pending_unsafe: Optional[str] = None
        self._pending_unsafe_since: float = 0.0

        self._calibrating = False
        self._calibration_buffer: Dict[str, List[float]] = {zid: [] for zid in self.zones}

        self._running = False
        self._load_calibration()

    # ─── Wiring ─────────────────────────────────────────────────────────────
    def register_touch_callback(self, cb: Callable[[TouchEvent], None]) -> None:
        self._callbacks_touch.append(cb)

    def register_safety_callback(self, cb: Callable[[str, str], None]) -> None:
        self._callbacks_safety.append(cb)

    # ─── Calibration ────────────────────────────────────────────────────────
    def _load_calibration(self) -> None:
        if not self.calibration_path.exists():
            return
        data = json.loads(self.calibration_path.read_text())
        for zid, zinfo in data.get("zones", {}).items():
            if zid in self.zones:
                self.zones[zid].baseline_raw = zinfo.get("baseline", 0.0)
                self.zones[zid].baseline_std = zinfo.get("std", 1.0)
                self.zones[zid].last_calibrated = zinfo.get("timestamp", 0.0)

    def save_calibration(self) -> None:
        data = {
            "timestamp": time.time(),
            "zones": {},
        }
        for zid, zone in self.zones.items():
            data["zones"][zid] = {
                "baseline": zone.baseline_raw,
                "std": zone.baseline_std,
                "timestamp": zone.last_calibrated,
            }
        self.calibration_path.parent.mkdir(parents=True, exist_ok=True)
        self.calibration_path.write_text(json.dumps(data, indent=2))

    def start_calibration(self) -> None:
        """Call this, then update() with no contact for ~2 seconds."""
        print("[E-Skin] Starting calibration... please do not touch the skin.")
        self._calibrating = True
        self._calibration_buffer = {zid: [] for zid in self.zones}

    def _finish_calibration(self) -> None:
        if not self._calibrating:
            return
        for zid, samples in self._calibration_buffer.items():
            if len(samples) >= 50:
                self.zones[zid].baseline_raw = statistics.mean(samples)
                self.zones[zid].baseline_std = statistics.stdev(samples) if len(samples) > 1 else 1.0
                self.zones[zid].last_calibrated = time.time()
        self._calibrating = False
        self.save_calibration()
        print(f"[E-Skin] Calibration complete. Baselines set for {len(self.zones)} zones.")

    # ─── Main Processing Loop ───────────────────────────────────────────────
    def update(self, raw_readings: Dict[str, float]) -> List[TouchEvent]:
        """
        Process one cycle of sensor readings.

        Args:
            raw_readings: dict mapping zone_id -> raw ADC value (e.g. from ADC multiplexer)

        Returns:
            List of TouchEvents generated this cycle.
        """
        if self._calibrating:
            return self._calibration_step(raw_readings)

        events: List[TouchEvent] = []
        active_zones: List[str] = []
        now = time.time()

        # Step 1: smooth and classify per zone
        for zid, raw in raw_readings.items():
            if zid not in self.zones:
                continue
            zone = self.zones[zid]

            # Exponential smoothing of raw value
            zone.current_smoothed = (
                self.SMOOTHING_ALPHA * raw +
                (1.0 - self.SMOOTHING_ALPHA) * zone.current_smoothed
            ) if zone.current_smoothed != 0.0 else raw

            zone.current_raw = raw
            zone.current_delta = zone.current_smoothed - zone.baseline_raw
            zone.is_active = zone.current_delta >= zone.threshold_light

            if zone.is_active:
                active_zones.append(zid)
                # Check if we should emit a new event
                last_evt = self._last_event_time.get(zid, 0)
                if (now - last_evt) > self.EVENT_DEBOUNCE_S:
                    evt = self._classify_zone(zone, now)
                    if evt:
                        events.append(evt)
                        self._last_event_time[zid] = now

        # Step 2: multi-zone fusion (merge adjacent simultaneous touches)
        fused_events = self._fuse_adjacent_events(events, active_zones)

        # Step 3: safety evaluation
        self._evaluate_safety(fused_events, now)

        return fused_events

    def _calibration_step(self, raw_readings: Dict[str, float]) -> List[TouchEvent]:
        for zid, raw in raw_readings.items():
            if zid not in self._calibration_buffer:
                continue
            self._calibration_buffer[zid].append(raw)
        total = sum(len(v) for v in self._calibration_buffer.values())
        if total >= self.CALIBRATION_SAMPLES * len(self.zones):
            self._finish_calibration()
        return []

    def _classify_zone(self, zone: ESkinZone, now: float) -> Optional[TouchEvent]:
        intensity = zone.classify(zone.current_delta)
        if intensity == "none":
            return None

        # Confidence: how far above threshold / relative to std
        margin = zone.current_delta / (zone.baseline_std * 3 + 1e-6)
        confidence = min(1.0, max(0.0, margin))

        # Safety override
        safety = "normal"
        response = "acknowledge"
        if intensity == "unsafe_pressure":
            safety = "unsafe"
            response = "freeze"
        elif intensity == "firm_pressure":
            safety = "caution"
            response = "slow_movement"

        # Special: face touched → always be gentle
        if zone.parent_region == "face" and intensity in ("light_touch", "firm_pressure"):
            response = "slow_and_gentle"

        evt = TouchEvent(
            event_type="touch",
            zone=zone.zone_id,
            intensity=intensity,
            raw_value=zone.current_smoothed,
            baseline=zone.baseline_raw,
            delta=zone.current_delta,
            confidence=confidence,
            timestamp=now,
            safety_level=safety,
            adjacent_joints=zone.adjacent_joints,
            suggested_response=response,
        )

        # Notify callbacks
        for cb in self._callbacks_touch:
            cb(evt)
        return evt

    def _fuse_adjacent_events(
        self,
        events: List[TouchEvent],
        active_zones: List[str],
    ) -> List[TouchEvent]:
        """If multiple adjacent zones fire at the same time, merge into one broad touch."""
        fused: List[TouchEvent] = []
        consumed: set = set()

        for evt in events:
            if evt.zone in consumed:
                continue

            # Find adjacents also firing
            adj_zones = get_adjacent_zones(evt.zone)
            adj_events = [e for e in events if e.zone in adj_zones and e.zone not in consumed]
            if adj_events:
                # Merge into broad touch
                merged_zones = [e.zone for e in adj_events]
                merged_zones.append(evt.zone)
                avg_delta = statistics.mean([e.delta for e in adj_events + [evt]])
                max_int = max(adj_events + [evt], key=lambda x: ["none","light_touch","firm_pressure","unsafe_pressure"].index(x.intensity))

                fused_evt = TouchEvent(
                    event_type="touch",
                    zone=evt.zone,  # primary zone
                    intensity=max_int.intensity,
                    raw_value=evt.raw_value,
                    baseline=evt.baseline,
                    delta=avg_delta,
                    confidence=max(e.confidence for e in adj_events + [evt]),
                    timestamp=evt.timestamp,
                    safety_level=max_int.safety_level,
                    adjacent_joints=list(set().union(*[set(e.adjacent_joints) for e in adj_events + [evt]])),
                    suggested_response=max_int.suggested_response,
                    multi_zone_ids=merged_zones,
                )
                fused.append(fused_evt)
                consumed.update(merged_zones)
            else:
                fused.append(evt)
                consumed.add(evt.zone)

        return fused

    def _evaluate_safety(self, events: List[TouchEvent], now: float) -> None:
        """Emit safety commands for joints that must stop."""
        for evt in events:
            if evt.intensity == "unsafe_pressure":
                for joint in evt.adjacent_joints:
                    for cb in self._callbacks_safety:
                        cb("FREEZE", f"joint={joint} zone={evt.zone} delta={evt.delta:.1f}")
            elif evt.intensity == "firm_pressure":
                for joint in evt.adjacent_joints:
                    for cb in self._callbacks_safety:
                        cb("SLOW", f"joint={joint} zone={evt.zone} delta={evt.delta:.1f}")

    def get_body_pressure_summary(self) -> Dict:
        """Snapshot of all zones' current state."""
        return {
            zid: {
                "raw": round(z.current_raw, 1),
                "delta": round(z.current_delta, 1),
                "intensity": z.classify(z.current_delta) if z.current_raw != 0.0 else "none",
                "is_active": z.is_active,
            }
            for zid, z in self.zones.items()
        }

    def shutdown(self) -> None:
        self._running = False
        self.save_calibration()
