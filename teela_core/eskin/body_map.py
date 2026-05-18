"""
E-Skin Body Map: Zone definitions, thresholds, calibration, and classification.
"""

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class ESkinZone:
    """A single tactile zone on Teela's body."""
    zone_id: str               # e.g. "shoulder.left"
    display_name: str          # e.g. "Left Shoulder"
    parent_region: str         # e.g. "upper_body"
    sensor_ids: List[str] = field(default_factory=list)  # ADC channel IDs
    
    # Baseline and calibration
    baseline_raw: float = 0.0
    baseline_std: float = 1.0
    last_calibrated: float = 0.0
    
    # Classification thresholds (delta from baseline)
    threshold_light: float = 30.0      # arbitrary ADC units; tune to hardware
    threshold_firm: float = 120.0
    threshold_unsafe: float = 300.0
    
    # Joint adjacency: if this zone is touched AND this joint is moving, STOP
    adjacent_joints: List[str] = field(default_factory=list)
    
    # Current reading
    current_raw: float = 0.0
    current_delta: float = 0.0
    current_smoothed: float = 0.0
    is_active: bool = False
    active_since: Optional[float] = None
    
    def classify(self, delta: float) -> str:
        """Classify a delta value into a pressure level."""
        if delta < self.threshold_light:
            return "none"
        elif delta < self.threshold_firm:
            return "light_touch"
        elif delta < self.threshold_unsafe:
            return "firm_pressure"
        else:
            return "unsafe_pressure"


# Predefined body zones with safety-relevant joint adjacencies
ALL_ZONES: Dict[str, ESkinZone] = {
    # --- Face (very sensitive → treat carefully) ---
    "face.left": ESkinZone(
        zone_id="face.left", display_name="Left Side of Face",
        parent_region="face", adjacent_joints=["neck_tilt"], threshold_light=20, threshold_firm=80, threshold_unsafe=200
    ),
    "face.right": ESkinZone(
        zone_id="face.right", display_name="Right Side of Face",
        parent_region="face", adjacent_joints=["neck_tilt"], threshold_light=20, threshold_firm=80, threshold_unsafe=200
    ),
    "forehead": ESkinZone(
        zone_id="forehead", display_name="Forehead",
        parent_region="face", adjacent_joints=["neck_tilt"], threshold_light=20, threshold_firm=80, threshold_unsafe=200
    ),
    "cheek.left": ESkinZone(
        zone_id="cheek.left", display_name="Left Cheek",
        parent_region="face", adjacent_joints=["neck_tilt", "jaw"], threshold_light=20, threshold_firm=80, threshold_unsafe=200
    ),
    "cheek.right": ESkinZone(
        zone_id="cheek.right", display_name="Right Cheek",
        parent_region="face", adjacent_joints=["neck_tilt", "jaw"], threshold_light=20, threshold_firm=80, threshold_unsafe=200
    ),
    
    # --- Neck ---
    "neck.front": ESkinZone(
        zone_id="neck.front", display_name="Front of Neck",
        parent_region="neck", adjacent_joints=["neck_tilt", "neck_pan"], threshold_light=25, threshold_firm=100, threshold_unsafe=250
    ),
    "neck.back": ESkinZone(
        zone_id="neck.back", display_name="Back of Neck",
        parent_region="neck", adjacent_joints=["neck_tilt", "neck_pan"], threshold_light=25, threshold_firm=100, threshold_unsafe=250
    ),
    
    # --- Shoulders ---
    "shoulder.left": ESkinZone(
        zone_id="shoulder.left", display_name="Left Shoulder",
        parent_region="upper_body", adjacent_joints=["shoulder_left_pitch", "shoulder_left_roll"], threshold_light=30, threshold_firm=120, threshold_unsafe=300
    ),
    "shoulder.right": ESkinZone(
        zone_id="shoulder.right", display_name="Right Shoulder",
        parent_region="upper_body", adjacent_joints=["shoulder_right_pitch", "shoulder_right_roll"], threshold_light=30, threshold_firm=120, threshold_unsafe=300
    ),
    
    # --- Arms ---
    "arm.left.upper": ESkinZone(
        zone_id="arm.left.upper", display_name="Left Upper Arm",
        parent_region="upper_body", adjacent_joints=["shoulder_left_pitch", "elbow_left"], threshold_light=30, threshold_firm=120, threshold_unsafe=300
    ),
    "arm.left.lower": ESkinZone(
        zone_id="arm.left.lower", display_name="Left Lower Arm",
        parent_region="upper_body", adjacent_joints=["elbow_left", "wrist_left"], threshold_light=30, threshold_firm=120, threshold_unsafe=300
    ),
    "arm.right.upper": ESkinZone(
        zone_id="arm.right.upper", display_name="Right Upper Arm",
        parent_region="upper_body", adjacent_joints=["shoulder_right_pitch", "elbow_right"], threshold_light=30, threshold_firm=120, threshold_unsafe=300
    ),
    "arm.right.lower": ESkinZone(
        zone_id="arm.right.lower", display_name="Right Lower Arm",
        parent_region="upper_body", adjacent_joints=["elbow_right", "wrist_right"], threshold_light=30, threshold_firm=120, threshold_unsafe=300
    ),
    
    # --- Hands ---
    "hand.left.palm": ESkinZone(
        zone_id="hand.left.palm", display_name="Left Palm",
        parent_region="hands", adjacent_joints=["wrist_left"], threshold_light=25, threshold_firm=100, threshold_unsafe=250
    ),
    "hand.left.back": ESkinZone(
        zone_id="hand.left.back", display_name="Left Back of Hand",
        parent_region="hands", adjacent_joints=["wrist_left"], threshold_light=25, threshold_firm=100, threshold_unsafe=250
    ),
    "hand.right.palm": ESkinZone(
        zone_id="hand.right.palm", display_name="Right Palm",
        parent_region="hands", adjacent_joints=["wrist_right"], threshold_light=25, threshold_firm=100, threshold_unsafe=250
    ),
    "hand.right.back": ESkinZone(
        zone_id="hand.right.back", display_name="Right Back of Hand",
        parent_region="hands", adjacent_joints=["wrist_right"], threshold_light=25, threshold_firm=100, threshold_unsafe=250
    ),
    
    # --- Torso ---
    "torso.front.upper": ESkinZone(
        zone_id="torso.front.upper", display_name="Upper Chest",
        parent_region="torso", adjacent_joints=["spine_pitch"], threshold_light=35, threshold_firm=130, threshold_unsafe=320
    ),
    "torso.front.lower": ESkinZone(
        zone_id="torso.front.lower", display_name="Lower Chest / Abdomen",
        parent_region="torso", adjacent_joints=["spine_pitch"], threshold_light=35, threshold_firm=130, threshold_unsafe=320
    ),
    "torso.back.upper": ESkinZone(
        zone_id="torso.back.upper", display_name="Upper Back",
        parent_region="torso", adjacent_joints=["spine_pitch", "spine_roll"], threshold_light=35, threshold_firm=130, threshold_unsafe=320
    ),
    "torso.back.lower": ESkinZone(
        zone_id="torso.back.lower", display_name="Lower Back",
        parent_region="torso", adjacent_joints=["hip_pitch"], threshold_light=35, threshold_firm=130, threshold_unsafe=320
    ),
    
    # --- Hips ---
    "hip.left": ESkinZone(
        zone_id="hip.left", display_name="Left Hip",
        parent_region="lower_body", adjacent_joints=["hip_pitch", "hip_yaw"], threshold_light=40, threshold_firm=140, threshold_unsafe=350
    ),
    "hip.right": ESkinZone(
        zone_id="hip.right", display_name="Right Hip",
        parent_region="lower_body", adjacent_joints=["hip_pitch", "hip_yaw"], threshold_light=40, threshold_firm=140, threshold_unsafe=350
    ),
    
    # --- Legs ---
    "leg.left.upper": ESkinZone(
        zone_id="leg.left.upper", display_name="Left Upper Leg",
        parent_region="lower_body", adjacent_joints=["hip_yaw", "knee_left"], threshold_light=40, threshold_firm=140, threshold_unsafe=350
    ),
    "leg.left.lower": ESkinZone(
        zone_id="leg.left.lower", display_name="Left Lower Leg",
        parent_region="lower_body", adjacent_joints=["knee_left", "ankle_left"], threshold_light=40, threshold_firm=140, threshold_unsafe=350
    ),
    "leg.right.upper": ESkinZone(
        zone_id="leg.right.upper", display_name="Right Upper Leg",
        parent_region="lower_body", adjacent_joints=["hip_yaw", "knee_right"], threshold_light=40, threshold_firm=140, threshold_unsafe=350
    ),
    "leg.right.lower": ESkinZone(
        zone_id="leg.right.lower", display_name="Right Lower Leg",
        parent_region="lower_body", adjacent_joints=["knee_right", "ankle_right"], threshold_light=40, threshold_firm=140, threshold_unsafe=350
    ),
    
    # --- Feet / Base ---
    "foot.left": ESkinZone(
        zone_id="foot.left", display_name="Left Foot",
        parent_region="lower_body", adjacent_joints=["ankle_left"], threshold_light=50, threshold_firm=150, threshold_unsafe=400
    ),
    "foot.right": ESkinZone(
        zone_id="foot.right", display_name="Right Foot",
        parent_region="lower_body", adjacent_joints=["ankle_right"], threshold_light=50, threshold_firm=150, threshold_unsafe=400
    ),
}

# Adjacency groups for multi-zone touch fusion
TOUCH_ADJACENCY_GROUPS: List[List[str]] = [
    ["face.left", "cheek.left"],
    ["face.right", "cheek.right"],
    ["shoulder.left", "arm.left.upper"],
    ["shoulder.right", "arm.right.upper"],
    ["arm.left.lower", "hand.left.palm", "hand.left.back"],
    ["arm.right.lower", "hand.right.palm", "hand.right.back"],
    ["torso.front.upper", "torso.front.lower"],
    ["torso.back.upper", "torso.back.lower"],
    ["hip.left", "leg.left.upper"],
    ["hip.right", "leg.right.upper"],
    ["leg.left.lower", "foot.left"],
    ["leg.right.lower", "foot.right"],
    ["neck.front", "neck.back"],
]


def get_zone_by_id(zone_id: str) -> Optional[ESkinZone]:
    return ALL_ZONES.get(zone_id)


def get_adjacent_zones(zone_id: str) -> List[str]:
    """Return all zones that are adjacent in the body map."""
    adjacent = []
    for group in TOUCH_ADJACENCY_GROUPS:
        if zone_id in group:
            adjacent.extend([z for z in group if z != zone_id])
    return list(set(adjacent))
