"""
Social Awareness & Theory of Mind

Teela tracks:
    - Who is present, where they are, what they're doing
    - Their emotional state (if inferable)
    - Joint attention (what are they looking at?)
    - Interaction state (greeting, conversation, task, idle, leaving)
    - Social norms (don't interrupt, wait your turn, personal space)
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class PersonPresence:
    person_id: str
    name: str
    position_m: Tuple[float, float, float]  # relative to Teela
    orientation_deg: float  # where they're facing (0 = facing Teela)
    activity: str  # standing, sitting, walking, pointing, waving
    attention_target: Optional[str] = None  # what they're looking at
    voice_active: bool = False  # are they currently speaking?
    last_speech_timestamp: Optional[float] = None
    emotional_expression: str = "neutral"  # happy, angry, surprised, etc.
    last_seen: float = field(default_factory=time.time)


@dataclass
class InteractionState:
    """The current social interaction frame."""
    mode: str = "idle"  # idle, greeting, conversation, task, conflict, leave
    initiator: Optional[str] = None  # who started this interaction
    current_speaker: Optional[str] = None
    silence_duration_s: float = 0.0
    topic: Optional[str] = None
    turn_count: int = 0
    start_time: float = field(default_factory=time.time)
    participants: List[str] = field(default_factory=list)
    joint_attention_target: Optional[str] = None  # "the red cup", "door", etc.


@dataclass
class SocialRules:
    """Configurable social norms Teela follows."""
    personal_space_m: float = 1.0       # don't approach closer than this
    greeting_distance_m: float = 2.0      # greet when someone enters this zone
    max_interruption_pause_s: float = 1.5  # wait this long before speaking
    conversation_timeout_s: float = 30.0   # go idle after this much silence
    gaze_duration_min_s: float = 0.5     # look at speaker at least this long
    gaze_duration_max_s: float = 5.0     # don't stare too long


class SocialAwareness:
    """Tracks people, social dynamics, and enforces social norms."""

    def __init__(self, rules: Optional[SocialRules] = None):
        self.rules = rules or SocialRules()
        self.present_people: Dict[str, PersonPresence] = {}
        self.interaction = InteractionState()
        self._last_loop_time = time.time()

    def update_presence(self, detections: List[PersonPresence]) -> None:
        """Update who's here. Called every perception frame."""
        now = time.time()
        
        # Mark current detections
        current_ids = set()
        for det in detections:
            self.present_people[det.person_id] = det
            current_ids.add(det.person_id)
        
        # Remove absent people (timeout: 5 seconds)
        stale = [pid for pid, p in self.present_people.items() if now - p.last_seen > 5.0]
        for pid in stale:
            del self.present_people[pid]

    def get_social_events(self) -> List[Dict]:
        """Detect social events (greeting, someone leaving, etc.)."""
        events = []
        for pid, person in self.present_people.items():
            dist = (person.position_m[0]**2 + person.position_m[1]**2)**0.5
            
            if dist < self.rules.greeting_distance_m and self.interaction.mode == "idle":
                events.append({
                    "type": "person_entered",
                    "person_id": pid,
                    "name": person.name,
                    "distance_m": dist,
                })
            
            if person.activity == "pointing":
                events.append({
                    "type": "person_pointing",
                    "person_id": pid,
                    "attention_target": person.attention_target,
                })
            
            if person.voice_active and self.interaction.current_speaker != pid:
                events.append({
                    "type": "turn_change",
                    "new_speaker": pid,
                })

        return events

    def should_speak(self) -> Tuple[bool, str]:
        """Decide if Teela should speak, and why."""
        now = time.time()
        
        # Don't interrupt
        if self.interaction.current_speaker is not None:
            if now - (self.present_people.get(self.interaction.current_speaker, 
                      PersonPresence("", "", (0,0,0), 0, "")).last_speech_timestamp or 0) < self.rules.max_interruption_pause_s:
                return False, "waiting_for_speaker"

        # Greeting opportunity
        if self.interaction.mode == "idle" and len(self.present_people) > 0:
            return True, "greeting"

        # Conversation has stalled
        if self.interaction.mode == "conversation":
            elapsed = now - self.interaction.start_time - (self.interaction.silence_duration_s)
            if elapsed > self.rules.conversation_timeout_s:
                return True, "conversation_timeout"

        # Proactive: if Teela is curious and idle
        if self.interaction.mode == "idle" and len(self.present_people) > 0:
            # Could be overridden by personality
            pass

        return False, "no_need"

    def transition_state(self, event_type: str, **kwargs) -> None:
        """Manage interaction state machine."""
        if event_type == "greeting_complete":
            self.interaction.mode = "conversation"
            self.interaction.initiator = kwargs.get("initiator")
        elif event_type == "person_left":
            if len(self.present_people) == 0:
                self.interaction.mode = "idle"
                self.interaction.participants = []
        elif event_type == "task_started":
            self.interaction.mode = "task"
        elif event_type == "task_complete":
            self.interaction.mode = "conversation"
        elif event_type == "conflict_detected":
            self.interaction.mode = "conflict"

    def get_attention_target(self) -> Optional[Tuple[float, float, float]]:
        """Where should Teela look? Returns (x, y, z) in world coords."""
        # Priority: current speaker's face > joint attention target > nearest person
        if self.interaction.current_speaker and self.interaction.current_speaker in self.present_people:
            return self.present_people[self.interaction.current_speaker].position_m
        
        if self.interaction.joint_attention_target:
            # TODO: resolve target name to spatial position
            pass

        if self.present_people:
            nearest = min(self.present_people.values(), 
                         key=lambda p: (p.position_m[0]**2 + p.position_m[1]**2)**0.5)
            return nearest.position_m

        return None

    def get_personal_space_violation(self) -> List[str]:
        """Who is inside Teela's personal space?"""
        violations = []
        for pid, person in self.present_people.items():
            dist = (person.position_m[0]**2 + person.position_m[1]**2)**0.5
            if dist < self.rules.personal_space_m:
                violations.append(pid)
        return violations
