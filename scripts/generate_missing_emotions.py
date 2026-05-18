#!/usr/bin/env python3
"""
generate_missing_emotions.py

Generate the remaining emotion voice files for Jade's complete palette.
Uses Chatterbox-Turbo with the existing reference voice from voices/jade_cloned/reference.wav
"""

import os
import sys
import time

sys.path.insert(0, "/home/roni/.local/lib/python3.10/site-packages")

VOICES_DIR = "/home/roni/teela_brain_5/voices/jade_cloned"
REFERENCE_AUDIO = os.path.join(VOICES_DIR, "reference.wav")


def check_player():
    for cmd in ["gst-play-1.0", "mpg123", "ffplay", "aplay"]:
        try:
            subprocess.run(["which", cmd.split()[0]], check=True, capture_output=True)
            return cmd.split()[0]
        except subprocess.CalledProcessError:
            continue
    return None


def play_audio(path, player):
    if not player:
        return
    if player == "ffplay":
        subprocess.run(["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet", path], capture_output=True)
    elif player == "mpg123":
        subprocess.run(["mpg123", "-q", path], capture_output=True)
    elif player == "gst-play-1.0":
        subprocess.run(["gst-play-1.0", "--quiet", path], capture_output=True)
    elif player == "aplay":
        subprocess.run(["aplay", path], capture_output=True)


def generate():
    try:
        import torchaudio
        from chatterbox.tts_turbo import ChatterboxTurboTTS
    except ImportError as e:
        print(f"❌ {e}")
        print("   Chatterbox not installed. Run: pip install chatterbox-tts")
        sys.exit(1)

    print("🎙️  Generating Missing Emotion Samples")
    print("=" * 55)
    print(f"Reference: {REFERENCE_AUDIO}")
    print("=" * 55)

    if not os.path.exists(REFERENCE_AUDIO):
        print(f"❌ Reference not found: {REFERENCE_AUDIO}")
        sys.exit(1)

    print("\n⏳ Loading Chatterbox-Turbo...")
    model = ChatterboxTurboTTS.from_pretrained(device="cpu")
    print("   ✅ Model loaded\n")

    player = check_player()

    # Missing emotions
    emotions = [
        {
            "file": "teela_clone_14_excited.wav",
            "text": "I cannot wait! This is going to be absolutely amazing!",
            "label": "🥳 Excited",
        },
        {
            "file": "teela_clone_15_disappointed.wav",
            "text": "Oh... [sigh] I really thought that would work out better.",
            "label": "😞 Disappointed",
        },
    ]

    for emotion in emotions:
        wav_path = os.path.join(VOICES_DIR, emotion["file"])
        
        # Skip if already exists
        if os.path.exists(wav_path):
            print(f"   ⏭️  {emotion['label']} already exists — skipping")
            continue

        print(f"\n  {emotion['label']}")
        print(f'     "{emotion["text"]}"')
        
        t0 = time.time()
        wav = model.generate(emotion["text"], audio_prompt_path=REFERENCE_AUDIO)
        torchaudio.save(wav_path, wav, model.sr)
        elapsed = time.time() - t0
        
        print(f"     ⚡ {elapsed:.1f}s → {wav_path}")
        
        if player:
            play_audio(wav_path, player)
            print()
        else:
            print("     ⚠️  No audio player found")

    print("\n" + "=" * 55)
    print("🎬 All emotions generated!")
    print("=" * 55)


if __name__ == "__main__":
    import subprocess  # noqa: E402
    generate()
