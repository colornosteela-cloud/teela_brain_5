# Teela Voice Troubleshooting Guide

## Quick Diagnosis Questions

When you say "Hey Teela" into the mic:

1. **Do you hear a BEEP?**
   - **YES BEEP** → Wake word detection works. The problem is later in the chain (STT, LLM, or speaker playback).
   - **NO BEEP** → Wake word isn't being detected. The mic is too quiet, wrong device, or the threshold is wrong.

2. **Does the terminal show `[MicSTT] Wake word detected!`?**
   - **YES** → The mic is picking up sound. Check if STT hears you.
   - **NO** → The mic isn't picking up any sound at all.

---

## 🔧 Fix Steps

### Step 0: Check your API Key

Teela needs `KIMI_API_KEY` to generate replies.

```bash
# On your Jetson:
echo $KIMI_API_KEY
```

If nothing shows:
```bash
export KIMI_API_KEY=your_actual_key_here
# Add to ~/.bashrc so it persists
```

### Step 1: Run the Diagnostic Script

```bash
cd ~/teela_brain_5
python3 -m scripts.check_jetson
```

This script checks:
- Are all packages installed?
- Is the API key set?
- Can the LLM connect?
- Does the speaker work?
- Does the mic hear you?
- Is config.yaml correct?

### Step 2: Quick Speaker + Bypass Test

If the wake word "Hey Teela" isn't working, test the speaker directly:

```bash
cd ~/teela_brain_5
python3 -m scripts.test_speaker_and_bypass
```

This will:
1. Play a test sentence through the speaker immediately
2. Ask you to type a question
3. Send it to Kimi and speak the response out loud

If this works, your speaker, LLM, and STT are all fine — the issue is just the **wake word threshold**.

---

## 🎯 Common Problems

### "No wake word detected"

The energy-based wake word detector needs your mic to be **loud enough**.

```bash
# Check your mic volume
alsamixer
```

Hit `F4` to switch to "Capture" settings. Raise the mic volume to ~80%. Press `ESC` to save.

Then try:
```bash
# Visualize mic input
arecord -D plughw:0,0 -f S16_LE -r 16000 -c 1 -d 3 test.wav
# Speak into the mic while this runs
cat test.wav | od -A x -t x1z | head -20
```

If the hex dump is mostly `00 00`, your mic is silent.

If the mic is confirmed working, lower the wake word energy threshold in **config.yaml**:

```yaml
voice:
  wakeword_sensitivity: 0.7   # try 0.5 for quieter mics
```

Or edit `teela_core/voice/wakeword.py` line 48:
```python
self._energy_threshold = 0.006   # try 0.003 for a very quiet mic
```

### "Wake word detected but no reply"

1. Check if the terminal shows `[MicSTT] Recognized: "..."` after the beep.
   - **NO** → The STT didn't understand you. Speak louder, closer to the mic.
   - **YES** → The LLM pipeline. Check if `KIMI_API_KEY` is set.

2. Check if `[Teela 🗣️]` appears in the terminal.
   - **NO** → The LLM isn't returning a reply (probably no API key).
   - **YES but no audio** → The `speaker.mode` in config.yaml is `stdout` instead of `edge_tts`.

### "Text appears on screen but no audio"

Your `config.yaml` might have:
```yaml
speaker:
  mode: stdout
```

Change it to:
```yaml
speaker:
  mode: edge_tts
```

---

## 🧪 Manual Component Tests

### Test just the speaker

```bash
cd ~/teela_brain_5
python3 -c "
from teela_core.voice.tts_speaker import SpeakerTTS
spk = SpeakerTTS(mode='edge_tts')
spk.speak('Hello, this is a test')
"
```

### Test just the mic (no wake word)

```bash
cd ~/teela_brain_5
python3 -c "
from teela_core.voice.stt_mic import MicSTT
mic = MicSTT(stt_endpoint=None)
heard = []
mic.start(on_transcript=lambda t: [heard.append(t), print('HEARD:', t)])
import time; time.sleep(5)
mic.stop()
print('Total heard:', len(heard))
"
```

### Test just the LLM

```bash
cd ~/teela_brain_5
python3 -c "
from teela_core.comms.cloud_bridge import CloudBridge
b = CloudBridge({'api_key': 'YOUR_KEY'})
r = b.chat('Say hello')
print(r.text)
"
```

---

## 🔊 ALSA Device Names

Your USB speaker is on `plughw:1,0`. Verify:

```bash
aplay -l   # list playback devices
arecord -l # list capture devices
```

If your mic is on a different card, update `config.yaml`:

```yaml
hardware:
  microphone:
    device: "plughw:0,0"  # change this to your actual mic
  speaker:
    output_device: "plughw:1,0"  # change to your actual speaker
```
