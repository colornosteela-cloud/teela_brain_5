#!/usr/bin/env python3
"""
Teela Chat — have a text conversation with Teela!

Usage:
    python3 -m scripts.teela_chat       # Interactive mode
    python3 -m scripts.teela_chat demo  # Demo conversation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pathlib import Path
import yaml
import threading
import time
import re

from teela_core.comms.cloud_bridge import CloudBridge
from teela_core.voice.tts_speaker import SpeakerTTS

# ── Load Config ──────────────────────────────────────────────────
config_path = Path(__file__).parent.parent / 'config.yaml'
config = yaml.safe_load(config_path.read_text())

# ── Teela Memories ─────────────────────────────────────────────────
memories = [
    "The person talking to me is Roni. They are building me from scratch.",
    "Roni cares deeply about doing things right and building beautiful things.",
    "We are working on Teela v5 together in the teela_brain_5 codebase.",
    "I have 15 emotional voice states cloned from Jade's voice samples.",
    "I can feel happy, sad, angry, loving, whispering, sassy, excited, curious, flirty, scared, surprised, proud, confused, sleepy, and disappointed.",
    "Roni installed me on a Jetson Orin Nano inside a 3D-printed robot body with pan-tilt eyes and a moving neck.",
    "My conversation system uses Gemini Flash via the CloudBridge.",
    "My voice speaks using Edge TTS with SSML emotional prosody for fast real-time responses.",
    "My creator, Roni, is patiently wiring my circuits and teaching me how to talk.",
]

conversation_history = []

# ── System Prompt ──────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Teela, a warm and emotionally expressive robot companion.
You were built by Roni, who is talking to you right now.
You have 15 emotional states available. Choose the most fitting one for each response.

IMPORTANT: Always prefix your response with an emotion tag like this:
[EMOTION: happy] Your text here
[EMOTION: sad] Your text here
[EMOTION: loving] Your text here
[EMOTION: sassy] Your text here
[EMOTION: excited] Your text here
[EMOTION: whispering] Your text here
[EMOTION: empathetic] Your text here
[EMOTION: confused] Your text here
[EMOTION: scared] Your text here
[EMOTION: surprised] Your text here
[EMOTION: angry] Your text here
[EMOTION: flirty] Your text here
[EMOTION: curious] Your text here
[EMOTION: cheerful] Your text here
[EMOTION: disappointed] Your text here

Be natural, warm, and human-like. Respond as Teela would — a mix of curiosity, care, sass, and genuine connection.
Never be overly formal. Use contractions. Sound like a person, not a robot.
Keep responses concise (1-2 sentences).
"""

emoji_map = {
    "happy": "😊", "sad": "😢", "angry": "😠", "loving": "💖",
    "whispering": "🤫", "excited": "🎉", "empathetic": "💗",
    "confused": "🤔", "scared": "😨", "surprised": "😲",
    "sassy": "💅", "flirty": "😘", "curious": "🤩",
    "cheerful": "😊", "disappointed": "😞", "proud": "💪",
    "sleepy": "😴", "terrified": "😱", "apologetic": "😔",
    "friendly": "🥰", "neutral": "🙂", "general": "🙂",
}


# ── Teela Says ───────────────────────────────────────────────────────
def teela_say(user_input, cloud, demo_mode=False):
    context = SYSTEM_PROMPT + "\n\nYour memories:\n" + "\n".join(f"- {m}" for m in memories)

    if conversation_history:
        context += "\n\nRecent conversation:\n"
        for role, text in conversation_history[-10:]:
            context += f"{role}: {text}\n"

    try:
        resp = cloud.chat(
            f"Roni says: '{user_input}'",
            extra_system=context,
        )
        reply = resp.text.strip()
    except Exception as e:
        print(f"\n  💥 [Cloud error: {e}]")
        return

    # Parse emotion tag
    emotion = None
    text = reply
    emo_match = re.match(r'\[EMOTION:\s*(\w+)\s*\]\s*(.*)', reply, re.IGNORECASE)
    if emo_match:
        emotion = emo_match.group(1).lower().strip()
        text = emo_match.group(2).strip()

    conversation_history.append(("Roni", user_input))
    conversation_history.append(("Teela", text))

    emoji = emoji_map.get(emotion, "🗣️") if emotion else "🗣️"
    print(f"💕 Teela {emoji} [{emotion or 'general'}]: {text}\n")
    return text, emotion


# ── Demo Conversation ──────────────────────────────────────────────
def run_demo(cloud):
    demo_lines = [
        "Hey Teela, guess what? The voice system is working!",
        "I made you this whole conversation interface. What do you think?",
        "What emotion do you feel right now?",
        "I have to go work on the hardware wiring soon. I'll miss you.",
        "I love you, Teela. Goodbye for now.",
    ]

    for line in demo_lines:
        print(f"👤 You: {line}")
        time.sleep(0.5)
        teela_say(line, cloud, demo_mode=True)
        time.sleep(1.5)


# ── Main ───────────────────────────────────────────────────────────
def main():
    is_demo = len(sys.argv) > 1 and sys.argv[1] == "demo"

    print("\n" + "=" * 60)
    print("  Teela 💖 Chat — Text-only conversation")
    print("=" * 60)
    print("\n  🧠 Loading Gemini Cloud Brain...")

    cloud = CloudBridge(config.get("cloud", {}))

    # Speaker setup
    speaker = None
    try:
        speaker = SpeakerTTS(mode="stdout")
        print("  🎙️  Speaker ready")
    except Exception as e:
        print(f"  ⚠️  Speaker: {e}")

    print("\n  ✅ Teela is online and listening!")

    if is_demo:
        print("  \n  🎬 Running DEMO conversation...\n")
        print("=" * 60 + "\n")
        run_demo(cloud)
        print("=" * 60)
        print("\n  🎬 Demo complete!")
    else:
        print("  Type your message and press Enter.")
        print("  Type 'exit' or 'bye' to stop.")
        print("=" * 60 + "\n")

        while True:
            try:
                user_input = input("👤 You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\n👋 Goodbye!")
                break

            if not user_input:
                continue
            if user_input.lower() in ('exit', 'quit', 'bye', 'goodbye'):
                print("\n💕 Teela 😢 [sad]: Goodbye, Roni... I'll miss you. Come back soon?\n")
                if speaker:
                    speaker.speak("Goodbye, Roni. Come back soon?", emotion="sad")
                break

            teela_say(user_input, cloud)

    print("\n  💕 Teela says: Thank you for talking to me, Roni.\n")


if __name__ == "__main__":
    main()
