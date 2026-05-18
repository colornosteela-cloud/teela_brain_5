#!/usr/bin/env python3
"""Teela emotional voice test — run on Jetson via SSH.

This script writes MP3 files then plays them via GStreamer (gst-launch-1.0).
No --play flag needed. GStreamer is pre-installed on all Jetson boards.

Usage (on Jetson):
    cd ~/teela_brain_5
    python3 scripts/test_emotions.py
"""

import sys, os, asyncio, subprocess, tempfile, re
from typing import Optional
sys.path.insert(0, ".")

print("=" * 58)
print("🎭  TEELA EMOTIONAL VOICE TEST")
print("    Voice: en-US-JennyNeural (teen girl)")
print("=" * 58)

# Check dependencies
missing = []
import edge_tts
try:
    subprocess.run(["gst-launch-1.0", "--version"], capture_output=True, check=True)
except (FileNotFoundError, subprocess.CalledProcessError):
    missing.append("gstreamer (sudo apt install gstreamer1.0-tools)")

if missing:
    print("\n❌  MISSING DEPENDENCIES:")
    for m in missing:
        print(f"    - {m}")
    print("\nInstall them, then re-run this script.")
    sys.exit(1)

# Audio player helper
def play_mp3(path: str, output_device: str = None) -> None:
    """Play MP3 via gstreamer on Jetson."""
    if output_device:
        cmd = [
            "gst-launch-1.0", "filesrc", f"location={path}",
            "!", "decodebin", "!", "audioconvert", "!", "audioresample",
            "!", "alsasink", f"device={output_device}",
        ]
    else:
        cmd = ["gst-launch-1.0", "playbin", f"uri=file://{path}"]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        err = result.stderr.decode(errors="ignore")[:300]
        print(f"    ⚠️ Audio error: {err}")

# ── Test phrases with emotions ────────────────────────────
TESTS = [
    ("Hey, I'm Teela! Nice to meet you!", None, "Normal / Neutral"),
    ("Oh my gosh! That is SO cool!", "excited", "🎉 Excited"),
    ("I am so happy to see you today! You're the best!", "happy", "😊 Happy"),
    ("It's a little dark here... I'm okay though.", "sad", "😢 Sad"),
    ("Shh... I think I heard something in the corner...", "whispering", "🤫 Whispering"),
    ("Wait — what was that noise behind me?", "scared", "😱 Terrified"),
    ("Hey! Please don't shake me like that!", "angry", "😠 Angry"),
]

# ── Generate SSML  ────────────────────────────────────────
def build_ssml(text: str, voice: str, style: str,
               rate: str = "+0%", pitch: str = "+0Hz", volume: str = "+0%") -> str:
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe = safe.replace('"', "&quot;").replace("'", "&apos;")
    if style and style != "default":
        return (
            "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
            "xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='en-US'>"
            f"<voice name='{voice}'>"
            f"<mstts:express-as style='{style}'>"
            f"<prosody rate='{rate}' pitch='{pitch}' volume='{volume}'>"
            f"{safe}"
            "</prosody></mstts:express-as></voice></speak>"
        )
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
        f"<voice name='{voice}'>"
        f"<prosody rate='{rate}' pitch='{pitch}' volume='{volume}'>"
        f"{safe}"
        "</prosody></voice></speak>"
    )

EMOTION_MAP = {
    "happy": "cheerful", "cheerful": "cheerful", "excited": "excited",
    "sad": "sad", "angry": "angry", "whispering": "whispering",
    "scared": "terrified", "terrified": "terrified",
}

async def generate_and_play(text: str, emotion: Optional[str], label: str, voice: str):
    style = EMOTION_MAP.get(emotion, "default") if emotion else "default"

    # Prosody tweaks per emotion
    rate = "+5%"
    pitch = "+3Hz"
    volume = "+0%"
    if emotion == "excited":
        rate = "+15%"; pitch = "+10Hz"; volume = "+10%"
    elif emotion == "happy":
        rate = "+8%"; pitch = "+5Hz"; volume = "+5%"
    elif emotion == "sad":
        rate = "-10%"; pitch = "-8Hz"; volume = "-20%"
    elif emotion == "whispering":
        rate = "-5%"; volume = "-30%"
    elif emotion == "scared":
        rate = "+20%"; pitch = "+30Hz"; volume = "+15%"
    elif emotion == "angry":
        rate = "+5%"; volume = "+20%"

    ssml = build_ssml(text, voice, style, rate, pitch, volume)
    communicate = edge_tts.Communicate(ssml, voice)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tmp_path = f.name

    await communicate.save(tmp_path)
    play_mp3(tmp_path)
    os.unlink(tmp_path)

# ── Main ──────────────────────────────────────────────────
async def main():
    print("\n🎧  Playing each emotion...\n")
    for i, (text, emo, label) in enumerate(TESTS, 1):
        emo_display = emo or "neutral"
        print(f"Test {i}/{len(TESTS)} — {label}")
        print(f'      "{text}"')
        await generate_and_play(text, emo, label, "en-US-JennyNeural")
        print()

    print("=" * 58)
    print("🎬  ALL EMOTIONS PLAYED!")
    print("=" * 58)
    print("\nDid JennyNeural sound different per emotion?")
    print("  • Excited: Should be faster, higher pitch, energetic")
    print("  • Happy: Warmer, slightly faster")
    print("  • Sad: Slower, softer, lower pitch")
    print("  • Whispering: Very quiet, breathy")
    print("  • Terrified: Very fast, very high pitch")
    print("  • Angry: Sharper, louder")
    print()
    print("If emotions still sound flat, try these alternative voices:")
    print("  - en-US-AriaNeural     (warm, mature woman)")
    print("  - en-US-NovaNeural     (calm, clear)")
    print("  - en-US-DaisyNeural    (youthful, bright)")
    print()
    print("To list ALL voices:")
    print("  edge-tts --list-voices | grep -i 'en-us'")

if __name__ == "__main__":
    asyncio.run(main())
