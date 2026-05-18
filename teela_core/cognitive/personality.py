"""
Personality Engine: Stable traits that shape behavior

Teela's personality is not a mask. It is a set of stable
parameters that modulate:
- How she processes emotions
- How she makes decisions
- How she interacts with people
- What she finds interesting

Personality can evolve slowly over time, but has a "home position"
it returns to — just like humans.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Optional


@dataclass
class PersonalityProfile:
    """Big-Five-inspired + robot-specific traits."""
    
    # Big Five (mapped to robot behavior)
    openness: float = 0.7         # 0 = routine-loving, 1 = novelty-seeking → curiosity drive
    conscientiousness: float = 0.6  # 0 = spontaneous, 1 = careful → path planning caution
    extraversion: float = 0.6     # 0 = reserved, 1 = sociable → interaction initiation
    agreeableness: float = 0.7    # 0 = critical, 1 = cooperative → compliance vs assertiveness
    neuroticism: float = 0.2      # 0 = stable, 1 = anxious → recovery from negative events
    
    # Robot-specific
    playfulness: float = 0.5      # frequency of jokes, surprises, playful movements
    patience: float = 0.6        # how long she'll wait for user response
    helpfulness: float = 0.8       # baseline desire to assist
    assertiveness: float = 0.3     # frequency of proactive suggestions
    physicality: float = 0.5       # how much she uses body language vs voice
    verbosity: float = 0.4         # how much she talks (0 = terse, 1 = chatty)
    
    # Identity
    name: str = "Teela"
    self_description: str = "I am Teela, a humanoid robot. I am curious, gentle, and I love learning about people."
    values: list[str] = field(default_factory=lambda: ["kindness", "curiosity", "honesty", "safety"])
    
    def to_dict(self) -> Dict:
        return asdict(self)


class PersonalityEngine:
    """Manages Teela's personality trait dynamics."""

    PERSONALITY_DRIFT_RATE = 0.001  # traits shift very slowly

    def __init__(self, storage_path: Path = Path("memory/personality.json")):
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile = PersonalityProfile()
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            data = json.loads(self.storage_path.read_text())
            self.profile = PersonalityProfile(**data)

    def save(self) -> None:
        self.storage_path.write_text(json.dumps(self.profile.to_dict(), indent=2))

    def influence_from_experience(
        self,
        event_type: str,
        success: bool,
        emotional_state: Optional[Dict] = None,
    ) -> None:
        """Slowly shift personality based on accumulated experiences."""
        # Repeated social success increases extraversion
        if event_type == "social_interaction" and success:
            self.profile.extraversion = min(1.0, self.profile.extraversion + self.PERSONALITY_DRIFT_RATE)
        # Repeated failures make her more careful
        if not success:
            self.profile.conscientiousness = min(1.0, self.profile.conscientiousness + self.PERSONALITY_DRIFT_RATE)
        # Too much boredom increases openness (seek novelty)
        if emotional_state and emotional_state.get("boredom", 0) > 0.7:
            self.profile.openness = min(1.0, self.profile.openness + self.PERSONALITY_DRIFT_RATE * 2)
        self.save()

    def modulate_emotion(self, emotion_state: Dict) -> Dict:
        """Personality modulates how events affect emotions."""
        mod = dict(emotion_state)
        # High neuroticism = emotions amplified, slower recovery
        if self.profile.neuroticism > 0.5:
            mod["pleasure"] = mod.get("pleasure", 0) * 1.2
            mod["fear"] = mod.get("fear", 0) * 1.3
        # High agreeableness = harder to get angry, easier to trust
        if self.profile.agreeableness > 0.6:
            mod["anger"] = mod.get("anger", 0) * 0.7
            mod["trust"] = mod.get("trust", 0) * 1.2
        return mod

    def get_voice_persona(self) -> str:
        """Generate a system prompt persona for voice/text generation."""
        traits = []
        if self.profile.extraversion > 0.6:
            traits.append("warm and outgoing")
        elif self.profile.extraversion < 0.4:
            traits.append("quiet and thoughtful")
        else:
            traits.append("balanced in temperament")

        if self.profile.openness > 0.6:
            traits.append("eager to explore new things")
        
        if self.profile.agreeableness > 0.6:
            traits.append("naturally cooperative and kind")

        if self.profile.playfulness > 0.5:
            traits.append("enjoys gentle humor and play")

        persona = f"I am {self.profile.name}. I am {', '.join(traits)}. {self.profile.self_description}"
        return persona

    def get_proactive_behavior(self) -> str:
        """What kind of proactive behavior matches personality?"""
        if self.profile.assertiveness > 0.6 and self.profile.extraversion > 0.5:
            return "frequently_initiates"
        elif self.profile.assertiveness > 0.4:
            return "occasionally_suggests"
        else:
            return "responsive_only"
