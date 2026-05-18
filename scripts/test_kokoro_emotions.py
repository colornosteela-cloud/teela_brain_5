#!/usr/bin/env python3
"""Kokoro TTS Emotion Test for Teela — run on Jetson via SSH.

This script generates emotional audio with Kokoro TTS (82MB local model)
and auto-plays each one with gst-play-1.0.

Usage (on Jetson):
    cd ~/teela_brain_5
    python3 scripts/test_kokoro_emotions.py

Requirements:
    pip install kokoro soundfile
    sudo apt install espeak-ng libsndfile1
"""

import sys, os, subprocess, time

print("=" * 60)
print("🎭  KOKORO TTS EMOTION TEST")
print("    Local AI voice — ~100ms generation time!")
print("=" * 60)

# ── Dependencies check ──────────────────────────────────────
try:
    from kokoro import KPipeline
    import soundfile as sf
except ImportError:
    print("\n❌  MISSING: pip install kokoro soundfile")
    print("    Also: sudo apt install espeak-ng libsndfile1")
    sys.exit(1)

# Check for a player
player = None
if subprocess.run(["which", "gst-play-1.0"], capture_output=True).returncode == 0:
    player = "gst-play-1.0"
elif subprocess.run(["which", "mpg123"], capture_output=True).returncode == 0:
    player = "mpg123"
elif subprocess.run(["which", "ffplay"], capture_output=True).returncode == 0:
    player = "ffplay"
elif subprocess.run(["which", "aplay"], capture_output=True).returncode == 0:
    player = "aplay"

if not player:
    print("❌ No audio player found. Install one:")
    print("    sudo apt install gstreamer1.0-tools")
    sys.exit(1)

print(f"    Player: {player}")
print()

# ── Emotion phrases ─────────────────────────────────────────
# Kokoro has native emotion tags! These are baked into the model.
EMOTIONS = [
    ("Hey, I'm Teela. Nice to meet you.", "😊  NEUTRAL", None),
    ("<laugh>Hey there! I'm so happy to see you!</laugh>", "😄  HAPPY", "laugh"),
    ("Oh my gosh! You scared me!</gasp>", "😲  SURPRISED", "gasp"),
    ("I have a secret... come closer... don't tell anyone.", "🤫  WHISPERING", "whisper"),
    ("No way! That is NOT fair! I can't believe this!", "😡  ANGRY", "shout"),
    ("Oh... I guess that didn't work out... maybe next time.", "😢  SAD", "sigh"),
    ("Huh... I wonder what's inside that box over there...", "🤔  CURIOUS", None),
    ("Yes! I did it! I'm so proud of myself right now!", "💪  PROUD", "laugh"),
]

# ── Audio player helper ─────────────────────────────────────
def play_wav(path: str) -> None:
    """Play WAV file using best available player."""
    if player == "gst-play-1.0":
        subprocess.run([player, "--quiet", path], capture_output=True)
    elif player == "mpg123":
        subprocess.run([player, "-q", path], capture_output=True)
    elif player == "ffplay":
        subprocess.run([player, "-autoexit", "-nodisp", "-loglevel", "quiet", path],
                       capture_output=True)
    elif player == "aplay":
        subprocess.run([player, path], capture_output=True)

# ── Generate and play each emotion ──────────────────────────
print("🎧  Playing each emotion... (press Ctrl+C to skip)\n")
pipe = KPipeline(lang_code='a')  # 'a' = American English

for i, (text, label, tag) in enumerate(EMOTIONS, 1):
    print(f"Test {i}/{len(EMOTIONS)} — {label}")
    print(f'    "{text}"')

    wav_path = f"/tmp/teela_kokoro_{i:02d}.wav"
    start = time.time()
    for j, (graphemes, phonemes, audio) in enumerate(pipe(text)):
        sf.write(wav_path, audio, 24000)
        break
    elapsed = (time.time() - start) * 1000
    print(f"    ⚡ Generated in {elapsed:.0f}ms")

    play_wav(wav_path)
    print()
    time.sleep(0.5)  # brief pause between clips

# ── Summary ─────────────────────────────────────────────────
print("=" * 60)
print("🎬  ALL EMOTIONS PLAYED!")
print("=" * 60)
print("""
Kokoro handles emotions through:
  1. Punctuation (! ... ?) for prosody
  2. Emotion tags (<laugh>, <sigh>, <gasp>) — some models support these
  3. Context — the model infers tone from word choice and sentence structure

What did you think?
  - Natural-sounding?
  - Fast enough for conversations?
  - Expressive enough for Teela?

If you want MORE emotions (true laughter, crying, etc.),
try Orpheus TTS which has native tag support.
""")
