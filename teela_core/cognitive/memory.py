"""
Memory System: Episodic, Semantic, and Spatial Memory

Teela remembers:
    - Every person she meets (face, name, preferences, relationship depth)
    - Conversations and events (what, when, where, with whom, how she felt)
    - Spatial map (where objects usually are, room layout)
    - Things she learned (facts, skills, corrections)
"""

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np


@dataclass
class PersonProfile:
    """What Teela knows about a person."""
    person_id: str
    name: str
    face_embedding: Optional[List[float]] = None
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    total_interactions: int = 0
    total_minutes_together: float = 0.0
    
    # Preferences (learnt over time)
    likes: List[str] = field(default_factory=list)
    dislikes: List[str] = field(default_factory=list)
    topics_of_interest: List[str] = field(default_factory=list)
    voice_tone_preference: str = "neutral"  # playful, formal, gentle, etc.
    
    # Relationship
    relationship_depth: float = 0.0  # 0 = stranger, 1 = close friend
    trust_level: float = 0.5
    how_they_treat_teela: str = "neutral"  # kind, dismissive, playful, etc.
    
    # Episodes involving this person
    episode_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Episode:
    """A remembered event."""
    episode_id: str
    timestamp: float
    duration_s: float
    event_type: str  # conversation, exploration, task, incident
    description: str
    location: Optional[str] = None
    people_present: List[str] = field(default_factory=list)
    objects_involved: List[str] = field(default_factory=list)
    teela_emotion_snapshot: Optional[Dict] = None
    what_user_said: List[str] = field(default_factory=list)
    what_teela_did: List[str] = field(default_factory=list)
    outcome: str = "neutral"  # success, failure, neutral, funny, sad
    learned: List[str] = field(default_factory=list)  # what Teela learned

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SpatialMemory:
    """Where things are in the world."""
    object_class: str
    position_m: Tuple[float, float, float]
    room: str
    last_observed: float
    confidence: float  # 0-1, degrades with time
    frequency_observed: int = 1  # how often seen here


class MemoryStore:
    """Persistent memory store for Teela."""

    def __init__(self, storage_dir: Path = Path("memory")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.people: Dict[str, PersonProfile] = {}
        self.episodes: Dict[str, Episode] = {}
        self.spatial: Dict[str, List[SpatialMemory]] = {}
        self.facts: Dict[str, str] = {}  # semantic memory
        
        self._load()

    # --- Persistence ---
    def _load(self) -> None:
        people_file = self.storage_dir / "people.json"
        if people_file.exists():
            data = json.loads(people_file.read_text())
            for pid, pdict in data.items():
                self.people[pid] = PersonProfile(**pdict)
        
        episodes_file = self.storage_dir / "episodes.json"
        if episodes_file.exists():
            data = json.loads(episodes_file.read_text())
            for eid, edict in data.items():
                self.episodes[eid] = Episode(**edict)
        
        facts_file = self.storage_dir / "facts.json"
        if facts_file.exists():
            self.facts = json.loads(facts_file.read_text())

    def save(self) -> None:
        (self.storage_dir / "people.json").write_text(
            json.dumps({pid: p.to_dict() for pid, p in self.people.items()}, indent=2)
        )
        (self.storage_dir / "episodes.json").write_text(
            json.dumps({eid: e.to_dict() for eid, e in self.episodes.items()}, indent=2)
        )
        (self.storage_dir / "facts.json").write_text(json.dumps(self.facts, indent=2))

    # --- People ---
    def recognize_or_create_person(
        self,
        face_embedding: Optional[List[float]] = None,
        detected_name: Optional[str] = None,
    ) -> PersonProfile:
        """Recognize person by face embedding, or create new profile."""
        if face_embedding is not None and self.people:
            # Find nearest by cosine similarity
            best_id = None
            best_sim = -1.0
            for pid, profile in self.people.items():
                if profile.face_embedding is None:
                    continue
                sim = self._cosine_similarity(face_embedding, profile.face_embedding)
                if sim > best_sim and sim > 0.7:  # threshold
                    best_sim = sim
                    best_id = pid
            if best_id:
                self.people[best_id].last_seen = time.time()
                self.people[best_id].total_interactions += 1
                return self.people[best_id]
        
        # New person
        new_id = f"person_{len(self.people)}_{int(time.time())}"
        name = detected_name or f"Stranger-{len(self.people)+1}"
        profile = PersonProfile(person_id=new_id, name=name, face_embedding=face_embedding)
        self.people[new_id] = profile
        return profile

    def update_person(self, person_id: str, **kwargs) -> None:
        if person_id in self.people:
            for k, v in kwargs.items():
                if hasattr(self.people[person_id], k):
                    setattr(self.people[person_id], k, v)
            self.people[person_id].last_seen = time.time()

    # --- Episodes ---
    def record_episode(self, episode: Episode) -> None:
        self.episodes[episode.episode_id] = episode
        # Link to people
        for pid in episode.people_present:
            if pid in self.people:
                self.people[pid].episode_ids.append(episode.episode_id)
                # Deepen relationship slightly
                self.people[pid].relationship_depth = min(1.0, self.people[pid].relationship_depth + 0.05)

    def summarize_recent_episodes(self, hours: float = 24.0) -> str:
        cutoff = time.time() - hours * 3600
        recent = [
            e for e in self.episodes.values()
            if e.timestamp > cutoff
        ]
        recent.sort(key=lambda x: x.timestamp)
        if not recent:
            return "Nothing memorable happened recently."
        lines = [f"- {e.description} (felt: {e.teela_emotion_snapshot.get('dominant', 'neutral') if e.teela_emotion_snapshot else 'neutral'})" 
                 for e in recent[-5:]]
        return "\\n".join(lines)

    # --- Spatial ---
    def remember_location(self, spatial: SpatialMemory) -> None:
        key = f"{spatial.room}:{spatial.object_class}"
        if key not in self.spatial:
            self.spatial[key] = []
        # Update or append
        updated = False
        for existing in self.spatial[key]:
            if self._distance(existing.position_m, spatial.position_m) < 0.5:
                existing.position_m = spatial.position_m
                existing.last_observed = spatial.last_observed
                existing.confidence = min(1.0, existing.confidence + 0.1)
                existing.frequency_observed += 1
                updated = True
                break
        if not updated:
            self.spatial[key].append(spatial)

    def where_is(self, object_class: str, room: Optional[str] = None) -> Optional[SpatialMemory]:
        """Ask Teela where something is. Returns most confident location."""
        candidates = []
        for key, memories in self.spatial.items():
            r, obj = key.split(":", 1)
            if obj == object_class and (room is None or r == room):
                for mem in memories:
                    # Degrade confidence with time
                    hours_old = (time.time() - mem.last_observed) / 3600
                    degraded_conf = mem.confidence * (0.95 ** hours_old)
                    candidates.append((mem, degraded_conf, r))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    # --- Semantic / Facts ---
    def learn_fact(self, key: str, value: str) -> None:
        self.facts[key] = value

    def recall_fact(self, key: str) -> Optional[str]:
        return self.facts.get(key)

    def get_person_summary(self, person_id: str) -> str:
        if person_id not in self.people:
            return "I don't know that person yet."
        p = self.people[person_id]
        parts = [
            f"Name: {p.name}",
            f"Known for {p.total_minutes_together:.0f} minutes over {p.total_interactions} interactions.",
            f"Relationship: {p.relationship_depth:.0%} deep.",
            f"Likes: {', '.join(p.likes) if p.likes else 'not sure yet'}",
            f"Topics: {', '.join(p.topics_of_interest) if p.topics_of_interest else 'still learning'}",
        ]
        return "\\n".join(parts)

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        a_arr = np.array(a)
        b_arr = np.array(b)
        return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr) + 1e-8))

    @staticmethod
    def _distance(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
        return float(np.linalg.norm(np.array(a) - np.array(b)))
