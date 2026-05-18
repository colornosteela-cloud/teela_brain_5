#!/usr/bin/env python3
"""
Generate NEW emotional voice tones for Teela using Jade's cloned voice.

Emotions generated:
  - Sad (whispers, sigh, tears)
  - Curious / Awed (wonder, excitement)
  - Sassy (playful, sarcastic, teasing)
  - Flirty (coy, warm, suggestive)
  - Tired / Sleepy (yawning, fading)
  - Scared / Nervous (hesitant, stammering)
  - Loving / Caring (soft, warm, intimate)
  - Confused (puzzled, thinking aloud)
  - Excited / Celebrating (cheering, laughter)
  - Disappointed (sighing, resigned)

Usage:
    python3 scripts/generate_new_emotions.py --audio-prompt voices/jade_cloned/reference.wav
"""

import argparse
import os
import subprocess
import time

try:
    import torchaudio
    from chatterbox.tts_turbo import ChatterboxTurboTTS
except ImportError as e:
    print(f"❌ {e}")
    print("    pip install -e chatterbox-tts torchaudio")
    exit(1)


def check_player():
    """Find best available audio player."""
    for cmd in ["gst-play-1.0", "ffplay", "aplay"]:
        try:
            subprocess.run(["which", cmd.split()[0]], check=True, capture_output=True)
            return cmd
        except subprocess.CalledProcessError:
            continue
    return None


def play_audio(path, player):
    if not player:
        return
    if player == "ffplay":
        subprocess.run(["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet", path],
                     capture_output=True)
    else:
        subprocess.run([player, path], capture_output=True)


EMOTIONS = [
    # (filename_suffix, label, emoji, text)
    ("sad", "😢 Sad", "A single tear slowly ran down my cheek... I tried to hold it back, but I couldn't anymore. Everything reminds me of you..."),
    ("curious_awed", "🤩 Curious & Awed", "Wait... is that a real meteor shower?! Oh my stars, look at the colors! This is incredible!"),
    ("sassy", "💅 Sassy", "Oh, please. You think *you* had a rough day? [laugh] Darling, I've had better Mondays on Mercury."),
    ("flirty", "😘 Flirty", "Oh? You noticed my new look? [chuckle] You're so observant... I like that about you."),
    ("sleepy", "😴 Sleepy", "Mmmm... I'm so tired... [yawn] Could we just... cuddle and watch the stars for a while?"),
    ("scared", "😨 Scared", "Uhm... did you hear that? [hesitant] I... I think something is watching us from the shadows..."),
    ("loving", "💖 Loving", "You know what? I'm really glad you're here right now. You make everything feel softer... safer."),
    ("confused", "🤔 Confused", "Wait... if the moon is made of cheese, then why haven't cows ever been to space? Hmm..."),
    ("excited", "🥳 Excited", "OH MY GOSH YES! [laugh] We did it! We actually did it! Come here, you! [cheer]"),
    ("disappointed", "😞 Disappointed", "Oh... I really thought you'd remember. [sigh] It's okay. I'll just... [whisper] I'll be fine."),
]


def generate_all(audio_prompt_path, play=False, output_dir="voices/jade_cloned"):
    os.makedirs(output_dir, exist_ok=True)
    
    print("═" * 60)
    print("🎙️  GENERATING NEW EMOTIONAL TONES FOR TEELA")
    print("    Voice: Jade (cloned)")
    print("═" * 60)
    
    model = ChatterboxTurboTTS.from_pretrained(device="cpu")
    print("\n✅ Model loaded")
    
    player = check_player() if play else None
    if player:
        print(f"   Player: {player}")
    
    start_time = time.time()
    results = []
    
    for idx, (suffix, label, text) in enumerate(EMOTIONS, start=6):
        wav_path = os.path.join(output_dir, f"teela_clone_{idx:02d}_{suffix}.wav")
        
        print(f"\n  [{idx}/15] {label}")
        print(f'      "{text[:80]}..."')
        
        t0 = time.time()
        wav = model.generate(text, audio_prompt_path=audio_prompt_path)
        torchaudio.save(wav_path, wav, model.sr)
        elapsed = time.time() - t0
        
        results.append((idx, wav_path, label, elapsed))
        print(f"      ⚡ Generated in {elapsed:.1f}s → {wav_path}")
        
        if play and player:
            play_audio(wav_path, player)
            time.sleep(0.5)
    
    total_time = time.time() - start_time
    
    # ── Summary ──────────────────────────────
    print("\n" + "═" * 60)
    print("🎬 NEW EMOTIONS COMPLETE")
    print("═" * 60)
    print(f"\nReference: {audio_prompt_path}")
    print(f"Total time: {total_time:.1f}s")
    print(f"\nGenerated files ({len(results)} new):")
    for idx, path, label, elapsed in results:
        print(f"  {path}")
    print("=" * 60)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Generate new emotional voice tones for Teela")
    parser.add_argument("--audio-prompt", default="voices/jade_cloned/reference.wav",
                        help="Path to Jade's cloned reference voice (default: voices/jade_cloned/reference.wav)")
    parser.add_argument("--play", "-p", action="store_true",
                        help="Auto-play each generated file")
    parser.add_argument("--output-dir", "-o", default="voices/jade_cloned",
                        help="Output directory (default: voices/jade_cloned)")
    args = parser.parse_args()
    
    generate_all(args.audio_prompt, args.play, args.output_dir)


if __name__ == "__main__":
    main()
