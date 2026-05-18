#!/usr/bin/env python3
"""Test the full voice pipeline: mic → wake word → STT

Usage:
    python3 -m scripts.test_voice

Options:
    --backend energy|porcupine   Wake word backend (default: energy)
    --rms                        Print live audio levels
    --duration 30                Seconds to run

What it should print:
    [MicSTT] Mic stream started at 16000 Hz
    [MicSTT] STT: whisper (local)
    [MicSTT] Say 'Hey Teela' to wake me!
    ...........................          ← dots while idle
    [WakeWord] 🔔 WAKE WORD DETECTED     ← when you speak
    [MicSTT] Wake word detected!
    ...........................          ← dots while recording your speech
    [MicSTT] Transcribing 2.1s of audio
    [MicSTT] Recognized: "hello teela"
    [MicSTT] Returned to idle
    ...........................

If you see nothing, check:
    1. Mic is plugged in and detected:  arecord -l
    2. Sounddevice installed:  pip install sounddevice
    3. Run with --rms to see levels:  python3 -m scripts.test_voice --rms
"""

import argparse
import time
from pathlib import Path
import sys

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from teela_core.voice.wakeword import WakeWordDetector
from teela_core.voice.stt_mic import MicSTT


def main():
    parser = argparse.ArgumentParser(description="Test Teela's voice pipeline")
    parser.add_argument(
        "--backend", choices=["energy", "porcupine"], default="energy",
        help="Wake word backend (default: energy)"
    )
    parser.add_argument(
        "--duration", type=int, default=30,
        help="How many seconds to listen"
    )
    parser.add_argument(
        "--rms", action="store_true",
        help="Print live RMS values for mic calibration"
    )
    parser.add_argument(
        "--whisper-model", default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (default: base = 74MB)"
    )
    parser.add_argument(
        "--no-whisper", action="store_true",
        help="Skip loading Whisper (test just mic + wake word)"
    )
    args = parser.parse_args()

    # Wake word detector
    print(f"[TestVoice] Loading wake word detector (backend: {args.backend})...")
    detector = WakeWordDetector(backend=args.backend)

    # Mic + STT
    stt_backend = "keyboard" if args.no_whisper else "whisper"
    mic = MicSTT(
        stt_endpoint=None,
        stt_backend=stt_backend,
        whisper_model=args.whisper_model,
        samplerate=16000,
        block_duration_ms=500,
        silence_duration_ms=1500,
    )

    mic.set_wake_word_detector(detector)

    transcripts: list[str] = []

    def on_transcript(text: str) -> None:
        transcripts.append(text)
        print(f"\n[RESULT] You said: \"{text}\"")

    def on_wake() -> None:
        print("\n[RESULT] 🔔 Wake word detected! (Teela is now listening)")

    mic.set_wake_callback(on_wake)
    mic.start(on_transcript)

    print(f"\n[+] Teela is listening for '{args.duration}s'. Say 'Hey Teela'!")
    print("[+] Try: \"Hey Teela, what do you see?\"")
    print("[+] Or just say something loud if using --backend energy")
    if args.rms:
        print("[+] Live RMS printing enabled — speak at different volumes.")
    print()
    print("   [Ctrl+C to stop]\n")

    start = time.time()
    try:
        while time.time() - start < args.duration:
            time.sleep(0.5)
            if not args.rms:
                print(".", end="", flush=True)
    except KeyboardInterrupt:
        print("\n\n[Stopped by user]")

    mic.stop()

    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"{'='*50}")
    if transcripts:
        print(f"Recognized {len(transcripts)} utterance(s):")
        for i, t in enumerate(transcripts, 1):
            print(f"  {i}. \"{t}\"")
    else:
        print("No speech recognized.")
        print("\n💡 Debug steps:")
        print("  1. Check mic works:  arecord -d 3 test.wav && aplay test.wav")
        print("  2. Run with --rms:    python3 -m scripts.test_voice --rms")
        print("  3. Speak louder/closer to the mic.")
        print("  4. Use --no-whisper if faster-whisper isn't installed yet.")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
