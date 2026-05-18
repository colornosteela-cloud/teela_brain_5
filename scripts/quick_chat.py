#!/usr/bin/env python3
"""Quick Teela conversation test — no camera, no mic, no serial.
Just keyboard → Ollama (kimi-k2.6:cloud) → TTS (edge_tts with female voice)."""

import sys
sys.path.insert(0, ".")

from teela_core.comms.cloud_bridge import CloudBridge

print("=" * 50)
print("🎀 Teela Quick Chat Mode")
print("Using voice: en-US-AnaNeural (soft, feminine)")
print("Using AI: Ollama kimi-k2.6:cloud")
print("=" * 50)

cfg = {
    "llm_provider": "ollama",
    "llm_model": "kimi-k2.6:cloud",
    "api_base": "http://localhost:11434",
    "temperature": 0.8,
    "max_tokens": 512,
}

brain = CloudBridge(cfg)
print("\n[Brain connected! Type 'bye' to quit]\n")

try:
    while True:
        user = input("[You]  ").strip()
        if user.lower() == "bye":
            print("[Teela 🎀]  Goodbye, friend!")
            break
        if not user:
            continue

        print("[Teela 🧠] Thinking...")
        resp = brain.chat(user)
        print(f"[Teela 🎀]  {resp.text}")
        print(f"         ({resp.latency_ms:.0f}ms, {resp.tokens_used} tokens)\n")

except (KeyboardInterrupt, EOFError):
    print("\n\nGoodbye!")
