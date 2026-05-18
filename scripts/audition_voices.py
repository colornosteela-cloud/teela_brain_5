#!/usr/bin/env python3
"""Teela voice audition — test ALL female voices and pick your favorite.

Usage (on Jetson):
    cd ~/teela_brain_5 && python3 scripts/audition_voices.py

The script lists all en-US female voices, plays a sample of each,
and lets you rate them. At the end, it prints a leaderboard.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from typing import Dict, List

import edge_tts

print("=" * 60)
print("🎤  TEELA VOICE AUDITION")
print("    Test every female voice and pick the best one")
print("=" * 60)

# ── Sample lines to test ────────────────────────────────────
SAMPLES = [
    "Hey, I'm Teela. Nice to meet you!",
    "Oh my gosh, that's amazing!",
    "I'm a little scared of the dark...",
]

# ── Fetch all voices ────────────────────────────────────────
async def fetch_voices() -> List[Dict]:
    voices = await edge_tts.list_voices()
    # Filter: English, Neural, female
    female_voices = []
    for v in voices:
        name = v.get("ShortName", "")
        gender = v.get("Gender", "").lower()
        locale = v.get("Locale", "")
        # Only English, female, neural (no standard voices)
        if locale.startswith("en") and gender == "female" and "Neural" in name:
            female_voices.append(v)
    return female_voices


def play_mp3(path: str) -> None:
    cmd = ["gst-launch-1.0", "playbin", f"uri=file://{path}"]
    subprocess.run(cmd, capture_output=True, timeout=30)


async def test_voice(voice: Dict, sample_idx: int = 0) -> str:
    """Generate and return path to MP3 for a voice."""
    name = voice["ShortName"]
    text = SAMPLES[sample_idx % len(SAMPLES)]
    communicate = edge_tts.Communicate(text, name)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tmp_path = f.name

    await communicate.save(tmp_path)
    return tmp_path


# ── Main ────────────────────────────────────────────────────
async def main():
    print("\n📡  Fetching voice list from Microsoft...")
    voices = await fetch_voices()

    if not voices:
        print("❌  No female voices found!")
        sys.exit(1)

    print(f"✅  Found {len(voices)} English female voices")
    print()

    # Ask which emotion/sample to test
    print("Which emotion sample should we use?")
    print("  1. Neutral / Friendly")
    print("  2. Excited / Happy")
    print("  3. Scared / Quiet")
    try:
        choice = int(input("Enter 1-3 (default=1): ").strip() or "1")
    except (EOFError, ValueError):
        choice = 1
    sample_idx = choice - 1

    ratings: Dict[str, int] = {}
    notes: Dict[str, str] = {}

    print(f"\n🎧  Playing {len(voices)} voices... Press ENTER after each to continue,")
    print("    or type a rating (1-10) + ENTER to score it.\n")

    for i, voice in enumerate(voices, 1):
        name = voice["ShortName"]
        display = voice.get("FriendlyName", name)
        locale = voice.get("Locale", "en")

        print(f"--- Voice {i}/{len(voices)} ---")
        print(f"Name:    {name}")
        print(f"Display: {display}")
        print(f"Locale:  {locale}")
        print(f'Sample:  "{SAMPLES[sample_idx]}"')

        tmp = await test_voice(voice, sample_idx)
        play_mp3(tmp)
        os.unlink(tmp)

        # Get rating
        try:
            inp = input("    Rate 1-10 or press ENTER to skip: ").strip()
        except EOFError:
            inp = ""
        if inp.isdigit():
            ratings[name] = int(inp)
            note = input("    Quick note (e.g. 'too mature', 'robotic', 'perfect!'): ").strip()
            notes[name] = note
        print()

    # ── Results ────────────────────────────────────────────
    print("=" * 60)
    print("📊  VOICES YOU RATED")
    print("=" * 60)

    if not ratings:
        print("No ratings given. Try again!")
        sys.exit(0)

    sorted_voices = sorted(ratings.items(), key=lambda x: x[1], reverse=True)
    for rank, (name, score) in enumerate(sorted_voices, 1):
        note = notes.get(name, "")
        print(f"  {rank}. {name:35s}  ⭐ {score}/10   {note}")

    winner = sorted_voices[0][0]
    print()
    print("=" * 60)
    print(f"🏆  TOP VOICE: {winner}")
    print("=" * 60)
    print()
    print(f"To set it in Teela, edit config.yaml:")
    print(f'    tts_voice: {winner}')
    print(f'    edge_tts_voice: {winner}')
    print()
    print("Or copy-paste this into your terminal to update:")
    print(f'  sed -i "s/tts_voice:.*/tts_voice: {winner}/" ~/teela_brain_5/config.yaml')
    print(f'  sed -i "s/edge_tts_voice:.*/edge_tts_voice: {winner}/" ~/teela_brain_5/config.yaml')


if __name__ == "__main__":
    asyncio.run(main())
