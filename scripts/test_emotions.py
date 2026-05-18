#!/usr/bin/env python3
"""Teela emotional voice test — run on Jetson to hear SSML emotions.

Requires: pip install edge-tts
Plays via: gst-launch-1.0 (GStreamer, already on Jetson)

Usage:
    python3 scripts/test_emotions.py
"""

import sys, os, asyncio, subprocess, tempfile
sys.path.insert(0, ".")

from teela_core.voice.tts_speaker import SpeakerTTS

print("=" * 56)
print("🎭  TEELA EMOTIONAL VOICE TEST")
print("    Voice: en-US-JennyNeural (teen girl)")
print("=" * 56)

speaker = SpeakerTTS(
    mode="edge_tts",
    edge_tts_voice="en-US-JennyNeural",
    output_device=None,  # uses default ALSA
)

TESTS = [
    ("Hey, I'm Teela! Nice to meet you!", None, "Normal/Neutral"),
    ("Oh my gosh! That is SO cool!", "excited", "🎉 Excited"),
    ("I am so happy to see you today!", "happy", "😊 Happy / Cheerful"),
    ("It's a little dark here... I'm okay though.", "sad", "😢 Sad"),
    ("Shh... I think I heard something...", "whispering", "🤫 Whispering"),
    ("Wait — what was that noise?", "scared", "😱 Terrified"),
    ("Hey! Please don't shake me like that!", "angry", "😠 Angry"),
]

print("\n🎧  Playing each emotion...\n")
for i, (text, emo, label) in enumerate(TESTS, 1):
    print(f"Test {i}/{len(TESTS)} — {label}")
    print(f'      "{text}"')
    speaker.speak(text, emotion=emo, rate="+5%", pitch="+3Hz")
    print()

print("=" * 56)
print("🎬  ALL EMOTIONS PLAYED!")
print("=" * 56)
print("\nHow did JennyNeural sound?")
print("  - Excited:   Should sound faster, high-pitch, energetic")
print("  - Sad:       Slower, lower pitch, softer volume")
print("  - Whisper:   Very quiet, breathy")
print("  - Angry:     Sharper, louder")
print("  - Terrified: Fast, very high pitch")
print()
print("If emotions sound flat, try these alternative voices:")
print("  - en-US-AriaNeural    (warm, mature woman)")
print("  - en-US-DaisyNeural   (youthful, bright)  [if available]")
print("  - en-US-MollyNeural   (cheerful, clear)   [if available]")
print()
print("To list ALL voices:  edge-tts --list-voices  | grep -i 'en-US'")
