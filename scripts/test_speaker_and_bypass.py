#!/usr/bin/env python3
"""
Quick speaker + wake-word test. Run on your Jetson.
"""
import os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 1. Instant speaker test
print("=" * 60)
print("SPEAKER TEST: Can you hear Teela?")
print("=" * 60)
from teela_core.voice.tts_speaker import SpeakerTTS
spk = SpeakerTTS(mode="edge_tts")
spk.speak("Hello! This is Teela. I am alive and speaking.")
print("If you DID hear that, your speaker is fine.")
print("If you did NOT hear it, check ALSA volume: run   alsamixer")
print()

# 2. Manual wake-word bypass test
print("=" * 60)
print("WAKE-WORD BYPASS: Forcing Teela to STT + speak back")
print("=" * 60)
print("Instead of 'Hey Teela', this script directly feeds a question")
print("to the brain and forces her to respond out loud.")
print()

question = input("Type a question for Teela (or just press Enter for default): ") or "Hello, are you there?"

from teela_core.comms.cloud_bridge import CloudBridge
from teela_core.cognitive.identity import SelfModel, BodyState

model = SelfModel()
model.update_body_state(BodyState(name="Teela", feelings="ready"))

bridge = CloudBridge({})
print("Sending to Kimi...")
resp = bridge.chat(
    f"The person just said: '{question}'. What do you say?",
    extra_system="You are Teela, a small humanoid robot."
)
reply = resp.text
print(f"[Teela would say]: {reply}")
print("Now speaking it out loud...")
spk.speak(reply)
print()
print("=" * 60)
print("Done. If you heard the reply, everything works except the wake word.")
print("If so, the mic is probably too quiet for 'Hey Teela' detection.")
print("Run:   alsamixer")
print("Then raise 'Mic' or 'Capture' volume with arrow keys, ESC to exit.")
print("=" * 60)
