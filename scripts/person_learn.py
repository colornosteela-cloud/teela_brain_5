#!/usr/bin/env python3
"""Person Learning Tool

Interactive script to teach Teela about a person.
Stores in episodic + semantic memory.

Usage:
    python3 -m scripts.person_learn

Prompts you for:
    - Name
    - Relationship to you
    - Likes / dislikes
    - Topics they care about
    - A photo (optional face embedding)
"""

import argparse
import time
from pathlib import Path

from teela_core.cognitive.memory import MemoryStore, PersonProfile


def interview() -> None:
    print("=== Teela Person Learning ===\\n")
    print("I'll ask you some questions about someone Teela should know.\\n")
    
    name = input("Their name: ").strip()
    if not name:
        print("No name provided. Exiting.")
        return

    relationship = input(f"How does {name} know you? (friend/family/colleague/stranger/custom): ").strip()
    likes = input(f"What does {name} like? (comma-separated): ").strip().split(",") if input else []
    dislikes = input(f"What does {name} dislike? (comma-separated): ").strip().split(",") if input else []
    topics = input(f"Topics {name} enjoys talking about? (comma-separated): ").strip().split(",") if input else []
    voice_tone = input(f"How should Teela speak to {name}? (playful/formal/gentle/casual): ").strip() or "neutral"

    store = MemoryStore()
    
    # Check if person exists
    existing = None
    for pid, prof in store.people.items():
        if prof.name.lower() == name.lower():
            existing = pid
            break

    if existing:
        print(f"\\nUpdating profile for {name}...")
        store.update_person(existing, 
            likes=[l.strip() for l in likes if l.strip()],
            dislikes=[d.strip() for d in dislikes if d.strip()],
            topics_of_interest=[t.strip() for t in topics if t.strip()],
            voice_tone_preference=voice_tone,
        )
    else:
        print(f"\\nCreating new profile for {name}...")
        new_id = f"person_{len(store.people)}_{int(time.time())}"
        profile = PersonProfile(
            person_id=new_id,
            name=name,
            likes=[l.strip() for l in likes if l.strip()],
            dislikes=[d.strip() for d in dislikes if d.strip()],
            topics_of_interest=[t.strip() for t in topics if t.strip()],
            voice_tone_preference=voice_tone,
        )
        store.people[new_id] = profile

    store.save()
    print(f"\\n✅ Saved. Teela now knows {name}.")
    print("\\nSummary:")
    print(store.get_person_summary(new_id if not existing else existing))


def main():
    interview()


if __name__ == "__main__":
    main()
