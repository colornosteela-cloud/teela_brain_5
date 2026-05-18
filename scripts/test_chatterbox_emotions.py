#!/usr/bin/env python3
"""Chatterbox-Turbo TTS Emotion Test for Teela — run on Jetson via SSH.

Usage (on Jetson):
    cd ~/teela_brain_5
    python3 scripts/test_chatterbox_emotions.py

Requirements:
    pip install chatterbox-tts
    # (Downloads ~350M model on first use)
"""

import sys, os, subprocess, time, warnings

warnings.filterwarnings("ignore")

print("=" * 60)
print("🎭  CHATTERBOX-TURBO TTS EMOTION TEST")
print("    SoTA open-source TTS by Resemble AI")
print("    Native paralinguistic tags: [laugh], [chuckle], [cough]")
print("=" * 60)

# ── Dependencies check ──────────────────────────────────────
try:
    import torchaudio as ta
    import torch
    from chatterbox.tts_turbo import ChatterboxTurboTTS
except ImportError as e:
    print(f"\n❌  MISSING: {e}")
    print("    pip install chatterbox-tts")
    sys.exit(1)

# Check for a player
player = None
for cmd in ["gst-play-1.0", "mpg123", "ffplay", "aplay"]:
    if subprocess.run(["which", cmd], capture_output=True).returncode == 0:
        player = cmd
        break

if not player:
    print("❌ No audio player found.")
    sys.exit(1)

print(f"    Player: {player}")
print()

# ── Emotion phrases with paralinguistic tags ─────────────────
EMOTIONS = [
    ("Hey, I'm Teela. Nice to meet you.", "😊  NEUTRAL"),
    ("Hey there! [chuckle] I'm so happy to see you!", "😄  HAPPY"),
    ("Oh my gosh! You scared me! Ah!", "😲  SURPRISED"),
    ("Psst... come closer... [cough] I have a secret to tell you...", "🤫  WHISPERING"),
    ("No way! That is NOT fair! I can't believe this!", "😡  ANGRY"),
    ("Oh... I guess that didn't work out... maybe next time...", "😢  SAD"),
    ("Huh... I wonder what's inside that box over there...", "🤔  CURIOUS"),
    ("Yes! [chuckle] I did it! I'm so proud of myself right now!", "💪  PROUD"),
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

# ── Load model ──────────────────────────────────────────────
print("⏳  Loading Chatterbox-Turbo model (~350MB download on first use)...")
print("    This may take a few minutes...")
device = "cpu"  # Jetson CUDA driver too old for torch 2.6
start = time.time()
model = ChatterboxTurboTTS.from_pretrained(device=device)
load_time = time.time() - start
print(f"    ✅ Model loaded in {load_time:.1f}s")
print(f"    Device: {device}")
print()

# ── Generate and play each emotion ──────────────────────────
print("🎧  Playing each emotion... (press Ctrl+C to skip)\n")

for i, (text, label) in enumerate(EMOTIONS, 1):
    print(f"Test {i}/{len(EMOTIONS)} — {label}")
    print(f'    "{text}"')

    wav_path = f"/tmp/teela_chatterbox_{i:02d}.wav"
    gen_start = time.time()
    wav = model.generate(text)
    ta.save(wav_path, wav, model.sr)
    gen_time = time.time() - gen_start
    print(f"    ⚡ Generated in {gen_time*1000:.0f}ms")

    play_wav(wav_path)
    print()
    time.sleep(0.5)

# ── Summary ─────────────────────────────────────────────────
print("=" * 60)
print("🎬  ALL EMOTIONS PLAYED!")
print("=" * 60)
print("""
Chatterbox-Turbo uses native paralinguistic tags:
  [laugh]    — adds genuine laughter
  [chuckle]  — soft chuckle
  [cough]    — cough sound
  
These are baked into the model, not post-processed.

Compare to Kokoro:
  - Kokoro: infers emotion from punctuation + context
  - Chatterbox: explicit [tags] for precise control

What did you think?
  - Could you hear [laugh] and [chuckle]?
  - More natural than Kokoro?
  - Fast enough for conversations?
""")
