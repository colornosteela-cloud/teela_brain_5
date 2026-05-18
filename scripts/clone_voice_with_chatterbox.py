#!/usr/bin/env python3
"""
clone_voice_with_chatterbox.py

Clone any voice (including Jade's) using Chatterbox-Turbo locally.
Supports:
  1. Direct WAV file → clone immediately (no internet needed)
  2. ElevenLabs-generated reference → auto-convert MP3 → WAV → clone

Usage examples:

    # Option A: Clone from existing WAV file (10s recommended)
    python3 scripts/clone_voice_with_chatterbox.py \
        --audio-prompt /path/to/jade_voice_10s.wav

    # Option B: Generate ElevenLabs reference first, then clone
    python3 scripts/clone_voice_with_chatterbox.py \
        --generate-elevenlabs \
        --elevenlabs-key YOUR_KEY \
        --elevenlabs-voice GpOshR6AeCDz0A9MCHKJ

    # Option C: Clone + immediately test emotions
    python3 scripts/clone_voice_with_chatterbox.py \
        --audio-prompt /tmp/jade_v2_sample.wav \
        --test-emotions
"""

import argparse
import os
import subprocess
import sys
import time


def print_banner():
    print("=" * 60)
    print("🎙️  CHATTERBOX-TURBO VOICE CLONER FOR TEELA")
    print("    Clone any voice → Teela speaks in that voice!")
    print("=" * 60)


def check_player():
    """Find best available audio player."""
    for cmd in ["gst-play-1.0", "mpg123", "ffplay -autoexit -nodisp -loglevel quiet", "aplay"]:
        parts = cmd.split()
        try:
            subprocess.run(["which", parts[0]], check=True, capture_output=True)
            return cmd
        except subprocess.CalledProcessError:
            continue
    return None


def play_audio(path, player):
    if not player:
        return
    parts = player.split()
    if parts[0] == "ffplay":
        subprocess.run(parts[:1] + ["-autoexit", "-nodisp", "-loglevel", "quiet", path],
                     capture_output=True)
    elif parts[0] == "gst-play-1.0":
        subprocess.run(["gst-play-1.0", "--quiet", path], capture_output=True)
    elif parts[0] == "mpg123":
        subprocess.run(["mpg123", "-q", path], capture_output=True)
    elif parts[0] == "aplay":
        subprocess.run(["aplay", path], capture_output=True)


def convert_mp3_to_wav(mp3_path, wav_path):
    """Convert MP3 to mono 16kHz WAV (best for voice cloning)."""
    try:
        import torchaudio
        wav, sr = torchaudio.load(mp3_path)
        if sr != 16000:
            resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)
            wav = resampler(wav)
        # Force mono
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)
        torchaudio.save(wav_path, wav, 16000)
        print(f"    ✅ Converted MP3 → WAV: {wav_path}")
        return True
    except ImportError:
        # Try ffmpeg
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", mp3_path,
                "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
                wav_path
            ], check=True, capture_output=True)
            print(f"    ✅ ffmpeg MP3 → WAV: {wav_path}")
            return True
        except FileNotFoundError:
            print("❌ Need either 'torchaudio' or 'ffmpeg' to convert MP3.")
            return False
        except subprocess.CalledProcessError:
            print(f"❌ ffmpeg failed to convert {mp3_path}")
            return False


def generate_elevenlabs_reference(api_key, voice_id, output_mp3):
    """Generate a reference audio using ElevenLabs API (cloud)."""
    try:
        from elevenlabs import VoiceSettings
        from elevenlabs.client import ElevenLabs
    except ImportError:
        print("❌ pip install elevenlabs")
        return False

    client = ElevenLabs(api_key=api_key)
    text = (
        "Hello. This is a voice calibration and cloning sample for Teela. "
        "I am reading in a calm, natural, and steady voice. "
        "The quick brown fox jumps over the lazy dog. "
        "A good voice should not only say words, it should carry meaning."
    )

    print("    ⏳ Calling ElevenLabs API...")
    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id="eleven_flash_v2_5",
        output_format="mp3_44100_128",
        voice_settings=VoiceSettings(
            stability=0.35,
            similarity_boost=0.90,
            style=0.35,
            use_speaker_boost=True,
            speed=0.92,
        ),
    )

    # Convert generator to bytes
    audio_bytes = b"".join(chunk for chunk in audio if isinstance(chunk, bytes))
    with open(output_mp3, "wb") as f:
        f.write(audio_bytes)
    print(f"    ✅ ElevenLabs reference saved: {output_mp3}")
    return True


def run_clone(audio_prompt_path, test_emotions=False):
    """Load Chatterbox-Turbo and clone voice."""
    try:
        import torchaudio
        from chatterbox.tts_turbo import ChatterboxTurboTTS
    except ImportError as e:
        print(f"❌ {e}")
        print("    pip install chatterbox-tts torchaudio")
        sys.exit(1)

    print("\n⏳ Loading Chatterbox-Turbo model...")
    model = ChatterboxTurboTTS.from_pretrained(device="cpu")
    print("    ✅ Model loaded")

    player = check_player()
    if player:
        print(f"    Player: {player.strip()}")

    # ── Generate test phrases ────────────────────────────────
    if test_emotions:
        phrases = [
            ("Hey there! [chuckle] I'm so happy to see you!", "😄 Happy"),
            ("Oh my gosh, you scared me!", "😲 Surprised"),
            ("No way! That is not fair at all!", "😡 Angry"),
            ("I'm so proud of us right now!", "💪 Proud"),
            ("Psst... come closer... [cough] I have a secret...", "🤫 Whispering"),
        ]
    else:
        phrases = [
            ("Hey, I'm Teela! It's great to finally meet you!", "🎙️ Teela Intro"),
            ("I can speak with any voice you clone. How cool is that?", "🎭 Demo"),
        ]

    print(f"\n🎧 Generating {len(phrases)} sample(s) with cloned voice...\n")
    for i, (text, label) in enumerate(phrases, 1):
        print(f"  Sample {i}/{len(phrases)} — {label}")
        print(f'      "{text}"')
        wav_path = f"/tmp/teela_clone_{i:02d}_{label.strip('😄😲😡💪🤫🎙️🎭').strip().replace(' ', '_').lower()}.wav"

        t0 = time.time()
        wav = model.generate(text, audio_prompt_path=audio_prompt_path)
        torchaudio.save(wav_path, wav, model.sr)
        elapsed = time.time() - t0
        print(f"      ⚡ Generated in {elapsed:.1f}s → {wav_path}")

        if player:
            play_audio(wav_path, player)
            print()
        else:
            print("      (No player found — file saved)")
        time.sleep(0.3)

    # ── Summary ───────────────────────────────────────────────
    print("=" * 60)
    print("🎬 VOICE CLONE COMPLETE")
    print("=" * 60)
    print(f"\nReference voice file: {audio_prompt_path}")
    print("\nGenerated samples:")
    for i, (text, label) in enumerate(phrases, 1):
        wav_path = f"/tmp/teela_clone_{i:02d}_{label.strip('😄😲😡💪🤫🎙️🎭').strip().replace(' ', '_').lower()}.wav"
        print(f"  {wav_path}")
    print("\n" + "=" * 60)


def main():
    print_banner()
    parser = argparse.ArgumentParser(description="Clone any voice into Teela using Chatterbox-Turbo")
    parser.add_argument("--audio-prompt", help="Path to 10-second WAV/MP3 reference audio")
    parser.add_argument("--generate-elevenlabs", action="store_true",
                        help="Generate ElevenLabs reference first (requires --elevenlabs-key)")
    parser.add_argument("--elevenlabs-key", default=os.getenv("ELEVENLABS_API_KEY"),
                        help="ElevenLabs API key (or set ELEVENLABS_API_KEY env var)")
    parser.add_argument("--elevenlabs-voice", default="GpOshR6AeCDz0A9MCHKJ",
                        help="ElevenLabs voice ID")
    parser.add_argument("--test-emotions", action="store_true",
                        help="Generate emotion test phrases after cloning")
    args = parser.parse_args()

    # ── Determine reference audio path ──────────────────────
    if args.generate_elevenlabs:
        if not args.elevenlabs_key:
            print("❌ --elevenlabs-key required (or set ELEVENLABS_API_KEY env var)")
            sys.exit(1)
        mp3_path = "/tmp/elevenlabs_ref.mp3"
        if not generate_elevenlabs_reference(args.elevenlabs_key, args.elevenlabs_voice, mp3_path):
            sys.exit(1)
        wav_path = "/tmp/elevenlabs_ref.wav"
        if not convert_mp3_to_wav(mp3_path, wav_path):
            sys.exit(1)
        audio_prompt = wav_path
    elif args.audio_prompt:
        audio_prompt = args.audio_prompt
        # Ensure WAV format
        if audio_prompt.lower().endswith(".mp3"):
            wav_path = audio_prompt.rsplit(".", 1)[0] + ".wav"
            if not convert_mp3_to_wav(audio_prompt, wav_path):
                sys.exit(1)
            audio_prompt = wav_path
    else:
        print("❌ Error: Provide --audio-prompt OR --generate-elevenlabs")
        parser.print_help()
        sys.exit(1)

    # ── Run cloning ─────────────────────────────────────────
    run_clone(audio_prompt, args.test_emotions)


if __name__ == "__main__":
    main()
