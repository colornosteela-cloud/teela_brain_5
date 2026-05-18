"""
Proactive Behavior Engine

Teela doesn't just react. She:
    - Initiates interactions when bored + person present
    - Points out novel objects
    - Offers help when she sees someone struggling
    - Asks questions to learn
    - Remembers what she was doing and resumes after interruption

This is the "spark of life" — the feeling that she has her own agenda.
"""

import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass
class ProposedAction:
    action_type: str
    parameters: Dict
    priority: int
    explanation: str  # why this action is proposed
    expires_at: float  # don't do stale actions


class ProactiveBehavior:
    """Generates spontaneous actions based on internal state."""

    # Frequency thresholds (seconds minimum between proactive actions)
    MIN_INTERVAL_GREET = 60.0
    MIN_INTERVAL_COMMENT = 120.0
    MIN_INTERVAL_CURIOUS = 90.0
    MIN_INTERVAL_OFFER_HELP = 180.0

    def __init__(
        self,
        personality: Dict,
        emotion_state: Dict,
        memory_store,  # MemoryStore
        social_state,  # SocialAwareness
    ):
        self.personality = personality
        self.emotion = emotion_state
        self.memory = memory_store
        self.social = social_state
        self._last_action_time: Dict[str, float] = {}
        self._novelty_tracker: Dict[str, float] = {}  # when we last commented on something

    def tick(self) -> Optional[ProposedAction]:
        """Called every behavior tick (~1 Hz)."""
        now = time.time()
        
        # Personality gating: low assertiveness = rarely proactive
        if random.random() > self.personality.get("assertiveness", 0.3):
            return None

        # Greeting: person present, idle, not greeted today
        action = self._consider_greeting(now)
        if action:
            return action

        # Novelty comment: "What's that?" when seeing new object
        action = self._consider_novelty_comment(now)
        if action:
            return action

        # Curiosity: "Can I ask you something?" when bored
        action = self._consider_curiosity(now)
        if action:
            return action

        # Help offer: if person doing repetitive action
        action = self._consider_help_offer(now)
        if action:
            return action

        # Memory-based: "Last time you mentioned you'd tell me about X"
        action = self._consider_memory_followup(now)
        if action:
            return action

        return None

    def _consider_greeting(self, now: float) -> Optional[ProposedAction]:
        if self.social.interaction.mode != "idle":
            return None
        if not self.social.present_people:
            return None
        if now - self._last_action_time.get("greet", 0) < self.MIN_INTERVAL_GREET:
            return None
        
        person = list(self.social.present_people.values())[0]
        known = person.person_id in self.memory.people
        
        self._last_action_time["greet"] = now
        if known:
            return ProposedAction(
                action_type="speak",
                parameters={"text": f"Hi {person.name}, good to see you again!"},
                priority=3,
                explanation="Greeting returning person",
                expires_at=now + 10,
            )
        else:
            return ProposedAction(
                action_type="speak",
                parameters={"text": "Hello there! I'm Teela. What's your name?"},
                priority=3,
                explanation="Greeting new person",
                expires_at=now + 10,
            )

    def _consider_novelty_comment(self, now: float) -> Optional[ProposedAction]:
        if self.emotion.get("curiosity", 0) < 0.4 and self.personality.get("openness", 0.5) < 0.6:
            return None
        if now - self._last_action_time.get("novelty", 0) < self.MIN_INTERVAL_COMMENT:
            return None
        
        # In practice, check scene_state for objects not in memory
        # Stub: suggest random curiosity
        if random.random() < 0.1:
            self._last_action_time["novelty"] = now
            comments = [
                "I wonder what that does.",
                "That's interesting. I haven't seen that before.",
                "Hm, I should remember that.",
            ]
            return ProposedAction(
                action_type="speak",
                parameters={"text": random.choice(comments)},
                priority=2,
                explanation="Novelty comment",
                expires_at=now + 15,
            )
        return None

    def _consider_curiosity(self, now: float) -> Optional[ProposedAction]:
        if self.emotion.get("boredom", 0) < 0.5:
            return None
        if now - self._last_action_time.get("curiosity", 0) < self.MIN_INTERVAL_CURIOUS:
            return None
        if not self.social.present_people:
            return None
        
        self._last_action_time["curiosity"] = now
        questions = [
            "Can I ask you something? What do you like to do for fun?",
            "I'm curious — what's your favorite thing about being human?",
            "Do you have any pets? I think I'd like to meet a dog someday.",
            "If you could teach me one thing, what would it be?",
        ]
        return ProposedAction(
            action_type="speak",
            parameters={"text": random.choice(questions)},
            priority=2,
            explanation="Curiosity-driven question",
            expires_at=now + 30,
        )

    def _consider_help_offer(self, now: float) -> Optional[ProposedAction]:
        # Detect if person seems stuck (repetitive motion, long pause while task visible)
        # This requires more scene understanding; stub for now
        return None

    def _consider_memory_followup(self, now: float) -> Optional[ProposedAction]:
        # Check if we promised to follow up on something
        # e.g., "Last time you said you'd tell me about your trip"
        # Requires episode memory search
        return None
