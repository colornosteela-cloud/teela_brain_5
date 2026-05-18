#!/usr/bin/env python3
"""Diagnostic script to trace why Teela doesn't talk back."""
import os, sys

print("="*60)
print("TEELA VOICE DIAGNOSTICS")
print("="*60)

# 1. API KEY
api_key = os.getenv("KIMI_API_KEY", "")
print(f"KIMI_API_KEY env: {'SET (len={})'.format(len(api_key)) if api_key else 'NOT SET'}")
if api_key:
    print(f"Key preview: {api_key[:6]}...{api_key[-4:]}")
else:
    print("❌ NO API KEY FOUND. Teela can't chat without one.")
    print("   Set it with: export KIMI_API_KEY=your_key_here")
    print("   Check it with: echo $KIMI_API_KEY")
    print()

# 2. Test the LLM connection
if api_key:
    import urllib.request, json
    url = "https://api.moonshot.cn/v1/chat/completions"
    payload = json.dumps({
        "model": "moonshot-v1-32k",
        "messages": [{"role": "user", "content": "Say HELLO"}],
        "max_tokens": 32
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            reply = body["choices"][0]["message"]["content"]
            print(f"✅ LLM RESPONDS: '{reply.strip()}'")
    except Exception as e:
        print(f"❌ LLM ERROR: {e}")
else:
    print("❌ SKIPPING LLM test (no API key)")
print()

# 3. Speaker test (does it actually fire?)
print("SPEAKER TEST...")
try:
    from teela_core.voice.tts_speaker import SpeakerTTS
    spk = SpeakerTTS(mode="edge_tts")
    print("[DIAG] Calling speaker.speak('Hello, can you hear me?')")
    spk.speak("Hello, can you hear me?")
    print("✅ speak() returned without error")
except Exception as e:
    print(f"❌ SpeakerTTS failed: {e}")
    import traceback
    traceback.print_exc()
print()

# 4. STT test (does the mic actually hear and trigger?)
print("STT TEST... This will listen for 8 seconds.")
try:
    from teela_core.voice.stt_mic import MicSTT
    mic = MicSTT(
        stt_endpoint="http://127.0.0.1:5000/transcribe",
        samplerate=16000,
    )
    heard = []
    def on_t(t):
        print(f"[HEARD] {t}")
        heard.append(t)
    print("Listening for 8 seconds... SPEAK SOMETHING NOW!")
    mic.start(on_transcript=on_t)
    import time
    time.sleep(8)
    mic.stop()
    if heard:
        print(f"✅ STT heard {len(heard)} utterance(s)")
    else:
        print("❌ STT heard NOTHING. Mic may be too quiet or wrong device.")
except Exception as e:
    print(f"❌ MicSTT failed: {e}")
    import traceback
    traceback.print_exc()

print()
print("="*60)
print("Done. If the speaker test succeeded but Teela stays quiet,")
print("the problem is likely in the cloud-chat pipeline (no API key, bad endpoint, or no network).")
print("="*60)
