#!/bin/bash
# Teela Voice Comparison — generate ALL voices then play them one by one
# Usage on Jetson:
#   cd ~/teela_brain_5
#   chmod +x scripts/compare_all_voices.sh
#   ./scripts/compare_all_voices.sh

set -e

VOICES=(
    "en-US-JennyNeural"
    "en-US-DaisyNeural"
    "en-US-AriaNeural"
    "en-US-CoraNeural"
    "en-US-AmberNeural"
    "en-US-AshleyNeural"
    "en-US-SaraNeural"
    "en-US-AnaNeural"
    "en-US-ElizabethNeural"
    "en-US-NancyNeural"
)

TEXT="Hey, I am Teela! Nice to meet you!"

# ── 1. GENERATE all MP3s ────────────────────────────
echo "==============================================="
echo "🎤 Generating all voices..."
echo "==============================================="
for VOICE in "${VOICES[@]}"; do
    SAFE=$(echo "$VOICE" | tr '-' '_')
    OUT="/tmp/teela_${SAFE}.mp3"
    echo -n "  → $VOICE ... "
    if [ -f "$OUT" ]; then
        echo "already exists, skipping."
    else
        edge-tts --text "$TEXT" --voice "$VOICE" --write-media "$OUT" 2>/dev/null
        echo "done."
    fi
done
echo

# ── 2. PLAY them one by one ─────────────────────────
echo "==============================================="
echo "🎧 Voice Comparison — press ENTER to advance"
echo "==============================================="
echo

# Pick best available player
PLAYER=""
if command -v gst-play-1.0 &>/dev/null; then
    PLAYER="gst-play-1.0"
elif command -v mpg123 &>/dev/null; then
    PLAYER="mpg123 -q"
elif command -v ffplay &>/dev/null; then
    PLAYER="ffplay -autoexit -nodisp -loglevel quiet"
else
    echo "❌  No audio player found! Install one of these:"
    echo "    sudo apt install gstreamer1.0-tools   # gst-play-1.0"
    echo "    sudo apt install mpg123              # mpg123"
    echo "    sudo apt install ffmpeg              # ffplay"
    exit 1
fi

echo "Using player: $PLAYER"
echo

for VOICE in "${VOICES[@]}"; do
    SAFE=$(echo "$VOICE" | tr '-' '_')
    OUT="/tmp/teela_${SAFE}.mp3"
    echo "───────────────────────────────────────────────"
    echo "  Playing: $VOICE"
    echo "  File:    $OUT"
    echo "───────────────────────────────────────────────"

    if [ ! -f "$OUT" ]; then
        echo "  ⚠️  File not found!"
        continue
    fi

    # Play the file
    if [ "$PLAYER" = "gst-play-1.0" ]; then
        gst-play-1.0 "$OUT" >/dev/null 2>&1
    elif [ "$PLAYER" = "mpg123 -q" ]; then
        mpg123 -q "$OUT"
    elif [ "$PLAYER" = "ffplay -autoexit -nodisp -loglevel quiet" ]; then
        ffplay -autoexit -nodisp -loglevel quiet "$OUT"
    fi

    echo
    echo -n "  Press ENTER for next voice (or type 'q' to quit): "
    read CHOICE
    if [ "$CHOICE" = "q" ]; then
        echo "  Exiting."
        break
    fi
    echo
done

echo
echo "==============================================="
echo "🎬 All voices played!"
echo "Which two did you like? Tell me the names."
echo "==============================================="
