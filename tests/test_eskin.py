"""Tests for E-Skin system."""

import time
from pathlib import Path

import pytest

from teela_core.eskin.body_map import ALL_ZONES, get_adjacent_zones
from teela_core.eskin.eskin import ESkinProcessor, TouchEvent


class TestBodyMap:
    def test_all_zones_exist(self):
        assert "shoulder.left" in ALL_ZONES
        assert "face.left" in ALL_ZONES
        assert "hand.left.palm" in ALL_ZONES
        assert "foot.right" in ALL_ZONES

    def test_adjacency(self):
        adj = get_adjacent_zones("shoulder.left")
        assert "arm.left.upper" in adj

    def test_zone_classify(self):
        zone = ALL_ZONES["shoulder.left"]
        assert zone.classify(zone.threshold_light - 1) == "none"
        assert zone.classify(zone.threshold_light + 1) == "light_touch"
        assert zone.classify(zone.threshold_firm + 1) == "firm_pressure"
        assert zone.classify(zone.threshold_unsafe + 1) == "unsafe_pressure"


class TestESkinProcessor:
    def setup_method(self):
        self.calls = []
        self.safe_calls = []
        self.proc = ESkinProcessor(
            calibration_path=Path("/tmp/test_eskin_cal.json"),
            on_touch_event=lambda e: self.calls.append(e),
            on_safety_command=lambda c, r: self.safe_calls.append((c, r)),
        )
        # Set baseline so we don't need calibration
        for z in self.proc.zones.values():
            z.baseline_raw = 100.0
            z.baseline_std = 5.0

    def test_no_touch_no_event(self):
        readings = {zid: 100.0 for zid in ALL_ZONES}
        events = self.proc.update(readings)
        assert len(events) == 0

    def test_light_touch_generates_event(self):
        readings = {zid: 100.0 for zid in ALL_ZONES}
        # Touch shoulder.left
        readings["shoulder.left"] = 100.0 + self.proc.zones["shoulder.left"].threshold_light + 10
        events = self.proc.update(readings)
        assert len(events) >= 1
        assert events[0].intensity == "light_touch"
        assert events[0].zone == "shoulder.left"

    def test_unsafe_pressure_triggers_safety(self):
        readings = {zid: 100.0 for zid in ALL_ZONES}
        readings["shoulder.left"] = 100.0 + self.proc.zones["shoulder.left"].threshold_unsafe + 50
        events = self.proc.update(readings)
        unsafe_evts = [e for e in events if e.intensity == "unsafe_pressure"]
        assert len(unsafe_evts) >= 1
        # Safety callback should fire
        assert any(c == "FREEZE" for c, _ in self.safe_calls)

    def test_face_zone_gentle_response(self):
        readings = {zid: 100.0 for zid in ALL_ZONES}
        readings["face.left"] = 100.0 + self.proc.zones["face.left"].threshold_light + 5
        events = self.proc.update(readings)
        assert events[0].suggested_response == "slow_and_gentle"

    def test_multi_zone_fusion(self):
        readings = {zid: 100.0 for zid in ALL_ZONES}
        readings["shoulder.left"] = 100.0 + 50
        readings["arm.left.upper"] = 100.0 + 55
        events = self.proc.update(readings)
        # Adjacent zones should fuse; count unique event zones
        zones = [e.zone for e in events]
        assert "shoulder.left" in zones or "arm.left.upper" in zones
