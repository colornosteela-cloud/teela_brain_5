#!/usr/bin/env python3
"""
test_tts_emotion_demo.py — Demo the FULL wire: Emotion Brain → Chatterbox TTS → Jade's Voice

This demonstrates the complete pipeline:
  1. User text → Emotion detection (emotion_brain.py)
  2. Emotion → Jade's cloned voice file selection
  3. Voice file + tagged text → Chatterbox-Turbo generation
  4. Audio → Jetson speakers

Usage:
    python3 scripts/test_tts_emotion_demo.py
    
Or with custom text:
    python3 scripts/test_tts_emotion_demo.py "I'm so excited to see you!"
"""

import os
import sys
import time
from pathlib import Path

# Add project paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path.home() / ".local" / "lib" / "python3.10" / "site-packages"))

from teela_brain.emotion_brain import teela_speak, list_all_emotions, get_voice_path


def check_player():
    """Find best available audio player."""
    for cmd in ["gst-play-1.0", "mpg123", "ffplay", "aplay"]:
        try:
            import subprocess
            subprocess.run(["which", cmd.split()[0]], check=True, capture_output=True)
            return cmd.split()[0]
        except subprocess.CalledProcessError:
            continue
    return None


def play_audio(path, player):
    """Play audio file."""
    if not player:
        return
    import subprocess
    if player == "ffplay":
        subprocess.run(["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet", path], capture_output=True)
    elif player == "mpg123":
        subprocess.run(["mpg123", "-q", path], capture_output=True)
    elif player == "gst-play-1.0":
        subprocess.run(["gst-play-1.0", "--quiet", path], capture_output=True)
    elif player == "aplay":
        subprocess.run(["aplay", path], capture_output=True)


def generate_with_chatterbox(text: str, emotion: str, voice_file: str) -> str:
    """
    Generate audio using Chatterbox-Turbo with Jade's cloned emotion voice.
    
    Returns path to generated WAV file.
    """
    try:
        import torchaudio
        from chatterbox.tts_turbo import ChatterboxTurboTTS
    except ImportError as e:
        print(f"❌ Error: {e}")
        print("   Install: pip install chatterbox-tts torchaudio")
        sys.exit(1)
    
    # Load model (cached - only loads once)
    print("  ⏳ Loading Chatterbox-Turbo...")
    model = ChatterboxTurboTTS.from_pretrained(device="cpu")
    print("     ✅ Model loaded")
    
    # Prepare paths
    voices_dir = PROJECT_ROOT / "voices" / "jade_cloned"
    ref_voice = voices_dir / voice_file
    
    if not ref_voice.exists():
        print(f"   ⚠️ Voice file not found: {ref_voice}")
        print(f"   Using reference.wav as fallback")
        ref_voice = voices_dir / "reference.wav"
    
    # Generate
    print(f"  🎙️ Generating with {emotion} voice...")
    t0 = time.time()
    wav = model.generate(text, audio_prompt_path=str(ref_voice))
    
    # Save to temp
    output_path = f"/tmp/teela_{emotion}_{int(time.time())}.wav"
    torchaudio.save(output_path, wav, model.sr)
    elapsed = time.time() - t0
    
    print(f"     ⚡ Generated in {elapsed:.1f}s")
    print(f"     📁 Saved: {output_path}")
    
    return output_path


def demo_full_pipeline(user_text: str = None):
    """Run the complete emotion → voice → audio pipeline."""
    
    print("=" * 60)
    print("🎭 TEELA EMOTION → VOICE PIPELINE DEMO")
    print("=" * 60)
    
    # Show all available emotions
    if not user_text:
        print("\n📋 Available Emotions:")
        list_all_emotions()
        print()
    
    # Use test text if none provided
    test_cases = user_text and [user_text] or [
        "I'm so excited to see you! This is amazing!",
        "I really miss him... it hurts so much.",
        "Wait, what? I don't understand what's going on.",
        "Oh... sure. Whatever. I'm sure you know best.",  # Sassy
        "You're so brave... [whisper] I love you.",       # Loving/Flirty
    ]
    
    player = check_player()
    if player:
        print(f"🎧 Audio player: {player}")
    else:
        print("⚠️  No audio player found. Install gst-play-1.0 or aplay.")
    
    for text in test_cases:
        print(f"\n{'─' * 60}")
        print(f"📝 INPUT: \"{text}\"")
        
        # Step 1: Analyze emotion
        result = teela_speak(text)
        emotion = result['detected_emotion']
        label = result['label']
        voice_file = result['voice_file']
        tts_text = result['tts_text']
        
        print(f"   🎭 Emotion: {label} ({emotion})")
        print(f"   🏷️  Tag injected: {result['tag_used']}")
        print(f"   🔊 Voice file: {voice_file}")
        print(f"   💬 TTS text: \"{tts_text}\"")
        
        # Step 2: Generate audio
        audio_path = generate_with_chatterbox(tts_text, emotion, voice_file)
        
        # Step 3: Play
        if player:
            print(f"   ▶️  Playing...")
            play_audio(audio_path, player)
            time.sleep(0.5)
        
        # Pause between samples
        time.sleep(1.0)
    
    print("\n" + "=" * 60)
    print("🎓 HOW TO USE IN CONVERSATION_LOOP.PY:")
    print("=" * 60)
    print("""
    # In conversation_loop.py, the LLM can add emotion tags:
    #   [EMOTION: happy] Hey, great to see you!
    #   [EMOTION: sad] I miss you...
    #
    # The system automatically:
    #   1. Parses the [EMOTION: xxx] tag
    #   2. Passes it to self.speaker.speak(text, emotion=emotion)
    #   3. The new SpeakerTTS picks Jade's cloned voice for that emotion
    #
    # To enable Chatterbox mode, update config.yaml:
    #   voice:
    #     tts_engine: "chatterbox"  # or "edge_tts", "piper"
    """)


if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    demo_full_pipeline(text)
