#!/usr/bin/env python3
"""
Jetson Voice Diagnostics — Run this ON your Jetson to find the exact failure point.
Usage: python3 scripts/check_jetson.py
"""
import os, sys, subprocess, json, time

FAILURES = []

def heading(h): print(f"\n{'='*60}\n{h}\n{'='*60}")
def fail(msg): print(f"  ❌ {msg}"); FAILURES.append(msg)
def ok(msg): print(f"  ✅ {msg}")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

heading("1. ENVIRONMENT CHECKS")

# Python version
print(f"  Python: {sys.version.split()[0]}")

# Check key packages
for pkg in ["numpy", "edge_tts", "faster_whisper", "opencv_python", "cv2"]:
    try:
        mod = __import__(pkg)
        ver = getattr(mod, "__version__", "?")
        ok(f"{pkg} installed ({ver})")
    except ImportError:
        fail(f"{pkg} NOT installed (pip install {pkg.replace('_', '-')})")

# Check gst-launch-1.0
for tool in ["gst-launch-1.0", "arecord", "aplay"]:
    try:
        subprocess.run([tool, "--version"], capture_output=True, check=True)
        ok(f"{tool} available")
    except Exception:
        fail(f"{tool} NOT found (apt-get install gstreamer1.0-tools alsa-utils)")

heading("2. ALSA DEVICES")
try:
    out = subprocess.run(["arecord", "-l"], capture_output=True, text=True).stdout
    if out.strip():
        print("  Capture devices:")
        for line in out.strip().split("\n"):
            print(f"    {line}")
    else:
        fail("No ALSA capture devices found. Plug in a USB mic!")
except Exception as e:
    fail(f"arecord -l failed: {e}")

try:
    out = subprocess.run(["aplay", "-l"], capture_output=True, text=True).stdout
    if out.strip():
        print("  Playback devices:")
        for line in out.strip().split("\n"):
            print(f"    {line}")
    else:
        fail("No ALSA playback devices found.")
except Exception as e:
    fail(f"aplay -l failed: {e}")

heading("3. API KEY CHECK")
api_key = os.getenv("KIMI_API_KEY", "")
config_key = ""
try:
    import yaml
    with open(os.path.join(ROOT, "config.yaml")) as f:
        cfg = yaml.safe_load(f)
        config_key = cfg.get("cloud", {}).get("api_key", "") or ""
except Exception:
    pass

key = api_key or config_key
if key and str(key).lower() not in ("null", "none", "", "your_key_here"):
    ok(f"KIMI API key is set (len={len(key)})")
    # Test connectivity
    heading("3b. LLM CONNECTIVITY TEST")
    url = "https://api.moonshot.cn/v1/chat/completions"
    payload = json.dumps({
        "model": "moonshot-v1-32k",
        "messages": [{"role": "user", "content": "Say HELLO"}],
        "max_tokens": 20
    }).encode()
    req = __import__("urllib.request").request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }, method="POST")
    try:
        with __import__("urllib.request").request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            reply = body["choices"][0]["message"]["content"]
            ok(f"LLM responds: '{reply.strip()}'")
    except Exception as e:
        fail(f"LLM ERROR: {e}")
else:
    fail("NO KIMI API KEY. Set it with: export KIMI_API_KEY=your_key_here")

heading("4. SPEAKER TEST")
try:
    from teela_core.voice.tts_speaker import SpeakerTTS
    spk = SpeakerTTS(mode="edge_tts")
    print("  [DIAG] Playing 'Hello, this is Teela speaking'...")
    spk.speak("Hello, this is Teela speaking")
    ok("TTS speak() returned (check if you heard audio!)")
except Exception as e:
    fail(f"SpeakerTTS failed: {e}")
    import traceback
    traceback.print_exc()

heading("5. STT / MICROPHONE TEST")
try:
    from teela_core.voice.stt_mic import MicSTT
    mic = MicSTT(
        stt_endpoint="http://127.0.0.1:5000/transcribe",
        samplerate=16000,
    )
    heard = []
    def on_t(t):
        print(f"    [HEARD] {t}")
        heard.append(t)
    mic.start(on_transcript=on_t)
    print("  Listening for 8 seconds... SPEAK NOW! Say 'Testing one two three'")
    time.sleep(8)
    mic.stop()
    if heard:
        ok(f"STT heard {len(heard)} utterance(s): {heard}")
    else:
        fail("STT heard NOTHING. Is your mic plugged in? Is it too quiet? Type: alsamixer and raise Mic capture volume.")
except Exception as e:
    fail(f"MicSTT failed: {e}")
    import traceback
    traceback.print_exc()

heading("6. CONFIG CHECK")
try:
    import yaml
    with open(os.path.join(ROOT, "config.yaml")) as f:
        cfg = yaml.safe_load(f)
    spk_mode = cfg.get("hardware", {}).get("speaker", {}).get("mode", "???")
    out_dev = cfg.get("hardware", {}).get("speaker", {}).get("output_device", "???")
    mic_dev = cfg.get("hardware", {}).get("microphone", {}).get("device", "???")
    stt = cfg.get("hardware", {}).get("microphone", {}).get("stt_backend", "???")
    print(f"  speaker.mode: {spk_mode}")
    print(f"  speaker.output_device: {out_dev}")
    print(f"  microphone.device: {mic_dev}")
    print(f"  microphone.stt_backend: {stt}")
    if spk_mode == "stdout":
        fail("speaker.mode is 'stdout' — Teela will only PRINT, not talk. Set it to 'edge_tts' in config.yaml.")
except Exception as e:
    fail(f"Config check failed: {e}")

heading("SUMMARY")
if FAILURES:
    print(f"\n❌ {len(FAILURES)} problem(s) found:")
    for f in FAILURES:
        print(f"   • {f}")
    print("\nFix the issues above, then run this script again.")
else:
    print("\n✅ All checks passed! If you still don't hear Teela, the issue is")
    print("   the wake-word threshold or the mic being too quiet.")
    print("\n   Try speaking VERY CLOSE to the mic, or run alsamixer to raise")
    print("   the capture volume.")
