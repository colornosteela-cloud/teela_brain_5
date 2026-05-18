"""
Emotion Engine: PAD Model + Basic Emotions + Affective Coloring

PAD = Pleasure (valence), Arousal, Dominance
Basic emotions computed from PAD + context.
Emotions color perception, action selection, and vocal expression.
"""

import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class EmotionalState:
    """Continuous emotional state in PAD space + discrete emotions."""
    pleasure: float = 0.0      # -1 (displeased) to +1 (pleased)
    arousal: float = 0.0       # -1 (sleepy/calm) to +1 (excited/agitated)
    dominance: float = 0.0     # -1 (submissive) to +1 (dominant)
    
    # Discrete basic emotions (0.0 - 1.0 intensity)
    joy: float = 0.0
    trust: float = 0.0
    fear: float = 0.0
    surprise: float = 0.0
    sadness: float = 0.0
    disgust: float = 0.0
    anger: float = 0.0
    anticipation: float = 0.0
    curiosity: float = 0.0     # key for robots
    boredom: float = 0.0
    
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "pleasure": round(self.pleasure, 3),
            "arousal": round(self.arousal, 3),
            "dominance": round(self.dominance, 3),
            "joy": round(self.joy, 3),
            "trust": round(self.trust, 3),
            "fear": round(self.fear, 3),
            "surprise": round(self.surprise, 3),
            "sadness": round(self.sadness, 3),
            "disgust": round(self.disgust, 3),
            "anger": round(self.anger, 3),
            "anticipation": round(self.anticipation, 3),
            "curiosity": round(self.curiosity, 3),
            "boredom": round(self.boredom, 3),
            "timestamp": self.timestamp,
        }

    def describe(self) -> str:
        """Human-readable emotional summary."""
        primary = sorted([
            ("joy", self.joy), ("trust", self.trust), ("fear", self.fear),
            ("surprise", self.surprise), ("sadness", self.sadness),
            ("disgust", self.disgust), ("anger", self.anger),
            ("anticipation", self.anticipation), ("curiosity", self.curiosity),
            ("boredom", self.boredom),
        ], key=lambda x: x[1], reverse=True)
        top = [f"{n}: {v:.2f}" for n, v in primary[:2] if v > 0.1]
        if not top:
            top = ["neutral"]
        return f"PAD({self.pleasure:.2f}, {self.arousal:.2f}, {self.dominance:.2f}), dominant: {', '.join(top)}"


@dataclass
class EmotionalEvent:
    """Something that happens in the world that affects emotion."""
    event_type: str
    valence_impact: float      # how positive/negative (-1 to +1)
    arousal_impact: float      # how activating (-1 to +1)
    dominance_impact: float
    target: Optional[str] = None  # e.g., person name or object class
    reason: str = ""
    timestamp: float = field(default_factory=time.time)


class EmotionEngine:
    """Emotional dynamics for a humanoid robot.
    
    Design philosophy: emotions are not decorative.
    They modulate:
        - Attention (threats = high arousal = narrow focus)
        - Speech rate and pitch (excitement = faster, higher)
        - Movement energy (joy = bouncier gait)
        - Color temperature of "face"/LEDs
        - Curiosity / exploration drive
        - Risk tolerance
    """

    # Decay rates per second toward baseline
    VALENCE_DECAY = 0.15
    AROUSAL_DECAY = 0.20
    DOMINANCE_DECAY = 0.10

    def __init__(
        self,
        baseline_pleasure: float = 0.1,  # mildly positive (friendly robot)
        baseline_arousal: float = 0.2,   # mildly alert
        baseline_dominance: float = -0.1, # slightly deferential
    ):
        self.state = EmotionalState(
            pleasure=baseline_pleasure,
            arousal=baseline_arousal,
            dominance=baseline_dominance,
        )
        self.baseline = EmotionalState(
            pleasure=baseline_pleasure,
            arousal=baseline_arousal,
            dominance=baseline_dominance,
        )
        self.history: List[EmotionalState] = []
        self.max_history = 3600  # 1 hour at 1 Hz
        self._last_update = time.time()

    def update(self, event: Optional[EmotionalEvent] = None) -> EmotionalState:
        """Step emotional dynamics. Call at ~1-10 Hz."""
        now = time.time()
        dt = now - self._last_update
        self._last_update = now

        # 1. Apply event if present
        if event:
            self._apply_event(event)

        # 2. Decay toward baseline (emotional regulation)
        self._decay_toward_baseline(dt)

        # 3. Compute discrete emotions from PAD
        self._compute_discrete_emotions()

        # 4. Clamp
        self._clamp()

        # 5. Record history
        self.state.timestamp = now
        self.history.append(self.state)
        if len(self.history) > self.max_history:
            self.history.pop(0)

        return self.state

    def _apply_event(self, event: EmotionalEvent) -> None:
        """Events have immediate impact."""
        # Weight by recency is not needed since this is the immediate event
        self.state.pleasure += event.valence_impact
        self.state.arousal += event.arousal_impact
        self.state.dominance += event.dominance_impact

        # Surprise is special: triggered by ANY unexpected large change
        total_impact = abs(event.valence_impact) + abs(event.arousal_impact) + abs(event.dominance_impact)
        if total_impact > 0.5:
            self.state.surprise = min(1.0, self.state.surprise + total_impact * 0.5)

    def _decay_toward_baseline(self, dt: float) -> None:
        """Exponential decay toward personality baseline."""
        self.state.pleasure += (self.baseline.pleasure - self.state.pleasure) * self.VALENCE_DECAY * dt
        self.state.arousal += (self.baseline.arousal - self.state.arousal) * self.AROUSAL_DECAY * dt
        self.state.dominance += (self.baseline.dominance - self.state.dominance) * self.DOMINANCE_DECAY * dt

        # Discrete emotions decay on their own curves
        self.state.joy *= (1 - 0.3 * dt)
        self.state.trust *= (1 - 0.1 * dt)
        self.state.fear *= (1 - 0.4 * dt)
        self.state.surprise *= (1 - 0.8 * dt)
        self.state.sadness *= (1 - 0.2 * dt)
        self.state.disgust *= (1 - 0.5 * dt)
        self.state.anger *= (1 - 0.4 * dt)
        self.state.anticipation *= (1 - 0.2 * dt)
        self.state.curiosity *= (1 - 0.05 * dt)  # curiosity lingers
        self.state.boredom += (1.0 - self.state.arousal) * 0.05 * dt  # boredom grows when calm

    def _compute_discrete_emotions(self) -> None:
        """Map PAD to discrete emotions using Plutchik-inspired mappings."""
        p, a, d = self.state.pleasure, self.state.arousal, self.state.dominance
        
        # Joy = high pleasure + moderate arousal
        self.state.joy = max(self.state.joy, max(0.0, (p + 0.5) * (a + 0.5)))
        # Trust = high pleasure + low arousal + positive dominance
        self.state.trust = max(self.state.trust, max(0.0, (p + 0.5) * (1 - a) * (d + 0.5)))
        # Fear = negative pleasure + high arousal + low dominance
        self.state.fear = max(self.state.fear, max(0.0, (-p + 0.5) * (a + 0.5) * (-d + 0.5)))
        # Anticipation = positive pleasure + high arousal
        self.state.anticipation = max(self.state.anticipation, max(0.0, (p + 0.3) * (a + 0.3)))
        # Sadness = negative pleasure + low arousal
        self.state.sadness = max(self.state.sadness, max(0.0, (-p + 0.3) * (1 - a)))
        # Anger = negative pleasure + high arousal + high dominance
        self.state.anger = max(self.state.anger, max(0.0, (-p + 0.3) * (a + 0.3) * (d + 0.3)))

    def _clamp(self) -> None:
        for attr in ["pleasure", "arousal", "dominance"]:
            setattr(self.state, attr, max(-1.0, min(1.0, getattr(self.state, attr))))
        for attr in ["joy", "trust", "fear", "surprise", "sadness", "disgust", "anger", "anticipation", "curiosity", "boredom"]:
            setattr(self.state, attr, max(0.0, min(1.0, getattr(self.state, attr))))

    def get_dominant_emotion(self) -> Tuple[str, float]:
        """Return highest-intensity emotion."""
        emotions = {
            "joy": self.state.joy,
            "trust": self.state.trust,
            "fear": self.state.fear,
            "surprise": self.state.surprise,
            "sadness": self.state.sadness,
            "disgust": self.state.disgust,
            "anger": self.state.anger,
            "anticipation": self.state.anticipation,
            "curiosity": self.state.curiosity,
            "boredom": self.state.boredom,
        }
        name = max(emotions, key=emotions.get)
        return name, emotions[name]

    def get_valence_label(self) -> str:
        if self.state.pleasure > 0.3: return "happy"
        if self.state.pleasure < -0.3: return "unhappy"
        return "neutral"

    def get_arousal_label(self) -> str:
        if self.state.arousal > 0.4: return "energetic"
        if self.state.arousal < -0.2: return "sleepy"
        return "calm"

    # --- E-skin touch events ---
    @staticmethod
    def event_gentle_touch(zone_name: str, person_name: Optional[str] = None) -> EmotionalEvent:
        return EmotionalEvent(
            event_type="touch_gentle",
            valence_impact=0.2,
            arousal_impact=-0.1,
            dominance_impact=-0.1,
            target=person_name,
            reason=f"Gentle touch on {zone_name}",
        )

    @staticmethod
    def event_startling_touch(zone_name: str, intensity: str = "firm") -> EmotionalEvent:
        return EmotionalEvent(
            event_type="touch_startling",
            valence_impact=-0.2,
            arousal_impact=0.4,
            dominance_impact=-0.2,
            reason=f"Unexpected {intensity} pressure on {zone_name}",
        )

    @staticmethod
    def event_unsafe_touch(zone_name: str, reason: str = "") -> EmotionalEvent:
        return EmotionalEvent(
            event_type="touch_unsafe",
            valence_impact=-0.4,
            arousal_impact=0.5,
            dominance_impact=-0.3,
            reason=f"Unsafe pressure on {zone_name}: {reason}",
        )

    @staticmethod
    def event_pat_head(person_name: Optional[str] = None) -> EmotionalEvent:
        return EmotionalEvent(
            event_type="pat_head",
            valence_impact=0.3,
            arousal_impact=-0.2,
            dominance_impact=-0.1,
            target=person_name,
            reason="Pat / stroke on head—calming gesture",
        )

    @staticmethod
    def event_wave_tapped_shoulder(person_name: Optional[str] = None) -> EmotionalEvent:
        return EmotionalEvent(
            event_type="attention_tap",
            valence_impact=0.1,
            arousal_impact=0.2,
            dominance_impact=0.0,
            target=person_name,
            reason="Tapped on shoulder—attention seeking",
        )
    @staticmethod
    def event_greet(person_name: str) -> EmotionalEvent:
        return EmotionalEvent(
            event_type="greet",
            valence_impact=0.3,
            arousal_impact=0.2,
            dominance_impact=-0.1,
            target=person_name,
            reason=f"Saw {person_name}",
        )

    @staticmethod
    def event_obstacle_close(distance_m: float) -> EmotionalEvent:
        severity = max(0.0, 1.0 - distance_m / 0.5)  # 1.0 if very close
        return EmotionalEvent(
            event_type="obstacle",
            valence_impact=-0.4 * severity,
            arousal_impact=0.5 * severity,
            dominance_impact=-0.2 * severity,
            reason=f"Obstacle at {distance_m:.2f}m",
        )

    @staticmethod
    def event_novel_object(object_class: str) -> EmotionalEvent:
        return EmotionalEvent(
            event_type="novelty",
            valence_impact=0.1,
            arousal_impact=0.3,
            dominance_impact=0.0,
            target=object_class,
            reason=f"Saw new {object_class}",
        )

    @staticmethod
    def event_person_left(person_name: str) -> EmotionalEvent:
        return EmotionalEvent(
            event_type="departure",
            valence_impact=-0.2,
            arousal_impact=-0.1,
            dominance_impact=0.0,
            target=person_name,
            reason=f"{person_name} left",
        )

    @staticmethod
    def event_praised() -> EmotionalEvent:
        return EmotionalEvent(
            event_type="praise",
            valence_impact=0.5,
            arousal_impact=0.3,
            dominance_impact=0.1,
            reason="User praised Teela",
        )

    @staticmethod
    def event_scolded() -> EmotionalEvent:
        return EmotionalEvent(
            event_type="scold",
            valence_impact=-0.4,
            arousal_impact=0.2,
            dominance_impact=-0.3,
            reason="User scolded Teela",
        )
