#!/usr/bin/env python3
"""Chatterbox-Turbo voice tuning test for Teela.

Tests cfg_weight and exaggeration parameters to find the sweet spot
for Teela's personality: playful, emotional, conversational.

Usage (on Jetson):
    cd ~/teela_brain_5
    python3 scripts/test_chatterbox_tuning.py
"""

import sys, os, subprocess, time, warnings
warnings.filterwarnings("ignore")

print("=" * 60)
print("🎛️  CHATTERBOX-TURBO VOICE TUNING TEST")
print("    Finding Teela's perfect voice settings")
print("=" * 60)

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
    print("❌ No audio player found."); sys.exit(1)
print(f"    Player: {player}")

# ── Load model (reuse if already loaded in memory) ──────────
print("\n⏳  Loading Chatterbox-Turbo...")
model = ChatterboxTurboTTS.from_pretrained(device="cpu")
print("    ✅ Model ready\n")

def play(path: str) -> None:
    if player == "gst-play-1.0":
        subprocess.run([player, "--quiet", path], capture_output=True)
    elif player == "mpg123":
        subprocess.run([player, "-q", path], capture_output=True)
    elif player == "ffplay":
        subprocess.run([player, "-autoexit", "-nodisp", "-loglevel", "quiet", path], capture_output=True)
    elif player == "aplay":
        subprocess.run([player, path], capture_output=True)

# ── Test phrase (emotional, with paralinguistic tag) ────────
TEST_PHRASE = "Hey there! [chuckle] I'm so happy to see you!"

# ── Tuning grid: cfg_weight x exaggeration ───────────────────
# Resemble recommends:
#   - Normal conversation: cfg=0.5, exag=0.5
#   - Expressive/dramatic: cfg=0.3, exag=0.7
#   - Fast speaker reference: cfg=0.3, exag=0.5

TUNES = [
    (0.5, 0.5, "🎯 DEFAULT — balanced, natural"),
    (0.3, 0.5, "🐢 SLOWER — calmer, more deliberate"),
    (0.5, 0.7, "🎭 DRAMATIC — expressive, faster"),
    (0.3, 0.7, "🔥 EXPRESSIVE — dramatic but paced (Resemble's rec for drama)"),
    (0.2, 0.8, "💥 MAX DRAMA — very slow, very theatrical"),
]

print("Testing phrase:")
print(f'    "{TEST_PHRASE}"')
print("\nGenerating samples with different tuning...\n")

for i, (cfg, exag, label) in enumerate(TUNES, 1):
    print(f"Test {i}/{len(TUNES)} — {label}")
    print(f"    cfg_weight={cfg} | exaggeration={exag}")

    wav_path = f"/tmp/teela_tuning_{i:02d}_cfg{cfg}_exag{exag}.wav"
    gen_start = time.time()
    wav = model.generate(TEST_PHRASE, cfg_weight=cfg, exaggeration=exag)
    ta.save(wav_path, wav, model.sr)
    gen_time = time.time() - gen_start
    print(f"    ⚡ Generated in {gen_time*1000:.0f}ms")

    play(wav_path)
    print()
    time.sleep(0.5)

# ── Summary ─────────────────────────────────────────────────
print("=" * 60)
print("🎬  TUNING TEST COMPLETE!")
print("=" * 60)
print("""
Which setting sounded most like Teela?

Teela's personality guide:
┌─────────────────────────┬──────────────────────────────┐
│ Teela's Mood            │ Recommended Settings         │
├─────────────────────────┼──────────────────────────────┤
│ 😊 Normal / Chatting    │ cfg=0.5, exag=0.5            │
│ 😢 Sad / Calm           │ cfg=0.3, exag=0.5            │
│ 😄 Happy / Excited      │ cfg=0.5, exag=0.7            │
│ 😡 Angry / Dramatic     │ cfg=0.3, exag=0.7            │
│ 🤫 Whispering / Teasing   │ cfg=0.2, exag=0.8            │
└─────────────────────────┴──────────────────────────────┘

Next: Want to CLONE your voice?
  Record 10 seconds of yourself talking:
  
      arecord -d 10 -f cd -t wav /tmp/my_voice_ref.wav
  
  Then run:
  
      model.generate(text, audio_prompt_path="/tmp/my_voice_ref.wav")

Files saved:
""")
for i, (cfg, exag, label) in enumerate(TUNES, 1):
    print(f"  /tmp/teela_tuning_{i:02d}_cfg{cfg}_exag{exag}.wav  — {label}")
