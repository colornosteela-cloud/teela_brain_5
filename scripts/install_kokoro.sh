#!/bin/bash
# install_kokoro.sh — Install Kokoro TTS on Jetson Orin Nano
# =============================================================
# Usage:
#   cd ~/teela_brain_5
#   chmod +x scripts/install_kokoro.sh
#   ./scripts/install_kokoro.sh
#
# What it does:
#   1. Installs espeak-ng (phoneme dependency)
#   2. Installs kokoro + soundfile
#   3. Downloads the 82MB model (English)
#   4. Runs a quick "Hey, I'm Teela!" test

set -euo pipefail

echo "============================================================"
echo "🔧  Installing Kokoro TTS on Jetson"
echo "============================================================"
echo

# ── 1. System deps ──────────────────────────────────────────
echo "➡️  Installing espeak-ng (phoneme dependency)..."
sudo apt-get update -qq
sudo apt-get install -y -qq espeak-ng espeak-ng-data libespeak-ng1 libsndfile1

# ── 2. Python deps ──────────────────────────────────────────
echo
echo "➡️  Installing kokoro TTS + soundfile..."
pip3 install kokoro soundfile

# ── 3. Pre-download model (saves time later) ─────────────────
echo
echo "➡️  Downloading Kokoro model (~82MB)..."
python3 -c "
from kokoro import KPipeline
# This triggers the model download on first use
pipe = KPipeline(lang_code='a')  # 'a' = American English
print('✅ Model downloaded and cached.')
"

# ── 4. Quick sanity test ────────────────────────────────────
echo
echo "➡️  Running quick test: 'Hey, I'm Teela!'"
python3 -c "
from kokoro import KPipeline
import soundfile as sf

text = 'Hey, I am Teela!'
pipe = KPipeline(lang_code='a')

# Generate and save
for i, (gs, ps, audio) in enumerate(pipe(text)):
    sf.write('/tmp/kokoro_test.wav', audio, 24000)
    break

print('✅ Generated /tmp/kokoro_test.wav')
print('   Duration: ~{:.1f} seconds'.format(len(audio) / 24000))
"

# ── 5. Play test (if audio available) ───────────────────────
echo
echo "➡️  Playing test..."
if command -v gst-play-1.0 &>/dev/null; then
    gst-play-1.0 --quiet /tmp/kokoro_test.wav
elif command -v aplay &>/dev/null; then
    aplay /tmp/kokoro_test.wav
else
    echo "⚠️  No audio player found. Test file saved to /tmp/kokoro_test.wav"
fi

echo
echo "============================================================"
echo "🎉  Kokoro TTS is ready!"
echo "============================================================"
echo
echo "Model cached at: ~/.local/lib/python3.10/site-packages/kokoro/"
echo "Test file:      /tmp/kokoro_test.wav"
echo
echo "Next steps:"
echo "  1. Run emotion test:       python3 scripts/test_kokoro_emotions.py"
echo "  2. Run voice comparison:   python3 scripts/kokoro_voice_demo.py"
echo
