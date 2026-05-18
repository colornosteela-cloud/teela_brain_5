#!/usr/bin/env python3
"""
teemotion_brain.py — Teela's Complete Emotional Intelligence System
===================================================================

This is Teela's "brain" — the system that:
  1. Takes ANY text input (chat, commands, responses)
  2. Detects the emotional intent
  3. Maps it to the best Chatterbox voice + paralinguistic tags
  4. Returns a complete speakable response

Usage Examples:
    # CLI test mode
    python3 teemotion_brain.py "I'm so excited about this!"
    python3 teemotion_brain.py "That really hurts my feelings..."
    
    # As a Python module
    from teemotion_brain import TeelaBrain
    teela = TeelaBrain(voices_dir="voices/jade_cloned")
    result = teela.think("I'm so sad right now")
    # result['tts_text'] → ready for Chatterbox
    # result['voice_file'] → which voice to use
    # result['emotion'] → detected emotion

Author: Colornosteela-cloud
Repo: https://github.com/Colornosteela-cloud/teela_brain_5
"""

import re
import glob
import os
import json
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# TEELA'S EMOTION REGISTRY
# Maps emotion names → voice files + paralinguistic tags
# ═══════════════════════════════════════════════════════════════════════
EMOTION_REGISTRY = {
    # --- Original 5 Emotions (already cloned) ---
    "happy": {
        "file": "teela_clone_01_happy.wav",
        "label": "😄 Happy",
        "tags": ["[laugh]", "[chuckle]", "[cheer]", "[whoop]"],
    },
    "surprised": {
        "file": "teela_clone_02_surprised.wav",
        "label": "😲 Surprised",
        "tags": ["[gasp]", "[exclaim]", "[whisper]"],
    },
    "angry": {
        "file": "teela_clone_03_angry.wav",
        "label": "😡 Angry",
        "tags": ["[sigh]", "[shout]", "[grunt]"],
    },
    "proud": {
        "file": "teela_clone_04_proud.wav",
        "label": "💪 Proud",
        "tags": ["[cheer]", "[laugh]"],
    },
    "whispering": {
        "file": "teela_clone_05_whispering.wav",
        "label": "🤫 Whispering",
        "tags": ["[whisper]", "[cough]", "[breathe]"],
    },

    # --- New 10 Emotions (generated just now) ---
    "sad": {
        "file": "teela_clone_06_sad.wav",
        "label": "😢 Sad",
        "tags": ["[whisper]", "[sigh]", "[breathe]", "[gasp]"],
    },
    "curious": {
        "file": "teela_clone_07_curious_awed.wav",
        "label": "🤩 Curious",
        "tags": ["[gasp]", "[laugh]", "[exclaim]", "[wonder]"],
    },
    "sassy": {
        "file": "teela_clone_08_sassy.wav",
        "label": "💅 Sassy",
        "tags": ["[laugh]", "[chuckle]", "[whisper]"],
    },
    "flirty": {
        "file": "teela_clone_09_flirty.wav",
        "label": "😘 Flirty",
        "tags": ["[chuckle]", "[whisper]", "[breathe]"],
    },
    "sleepy": {
        "file": "teela_clone_10_sleepy.wav",
        "label": "😴 Sleepy",
        "tags": ["[yawn]", "[breathe]", "[whisper]"],
    },
    "scared": {
        "file": "teela_clone_11_scared.wav",
        "label": "😨 Scared",
        "tags": ["[gasp]", "[whisper]", "[shudder]"],
    },
    "loving": {
        "file": "teela_clone_12_loving.wav",
        "label": "💖 Loving",
        "tags": ["[chuckle]", "[whisper]", "[breathe]"],
    },
    "confused": {
        "file": "teela_clone_13_confused.wav",
        "label": "🤔 Confused",
        "tags": ["[murmur]", "[sigh]", "[whisper]"],
    },
    "excited": {
        "file": "teela_clone_14_excited.wav",
        "label": "🥳 Excited",
        "tags": ["[cheer]", "[laugh]", "[whoop]", "[exclaim]"],
    },
    "disappointed": {
        "file": "teela_clone_15_disappointed.wav",
        "label": "😞 Disappointed",
        "tags": ["[sigh]", "[whisper]", "[murmur]"],
    },

    # --- Special Meta-Emotions ---
    "greeting": {
        "file": "teela_clone_01_happy.wav",
        "label": "👋 Greeting",
        "tags": ["[laugh]", "[chuckle]"],
    },
    "farewell": {
        "file": "teela_clone_05_whispering.wav",
        "label": "👋 Farewell",
        "tags": ["[whisper]", "[breathe]"],
    },
    "neutral": {
        "file": "teela_clone_01_happy.wav",
        "label": "😐 Neutral",
        "tags": ["[chuckle]", "[whisper]"],
    },
}


# ═══════════════════════════════════════════════════════════════════════
# SENTIMENT DETECTION KEYWORDS
# ───────────────────────────────────────────────────────────────────────
# Each emotion gets a list of trigger words/phrases.
# The engine scores each and picks the highest.
# ═══════════════════════════════════════════════════════════════════════
SENTIMENT_TRIGGERS = {
    "sad": [
        "sad", "sorrow", "cry", "tears", "sobbing", "grief", "miss you", "lonely",
        "depressed", "hurt", "pain", "sorry", "regret", "heartbroken", "lost",
        "mourn", "broken", "down", "blue", "melancholy", "gloomy", "cry to sleep",
        "weep", "miserable", "unhapp", "suffer", "ache", "longing", "yearn",
    ],
    "fear": [
        "scared", "afraid", "fear", "terrified", "spooky", "creepy", "haunted",
        "ghost", "monster", "dark", "alone", "panic", "anxious", "worried",
        "nervous", "tense", "uneasy", "caution", "beware", "danger", "scream",
        "hide", "running away", "watched", "shadows", "nightmare", "horror",
    ],
    "angry": [
        "angry", "mad", "furious", "pissed", "rage", "hate", "stupid", "idiot",
        "annoy", "frustrated", "unfair", "cheated", "wronged", "insult", "offended",
        "outraged", "infuriated", "irritated", "jerk", "asshole", "damn", "hell",
        "screw", "screwed", "ruined", "wrecked", "pissed off", "fed up",
    ],
    "happy": [
        "happy", "joy", "glad", "cheerful", "great", "wonderful", "awesome",
        "amazing", "love", "lovely", "fantastic", "perfect", "smile", "laugh",
        "giggle", "hilarious", "blessed", "grateful", "delight", "ecstatic",
        "cheer", "beam", "radiant", "upbeat", "positive", "good mood",
    ],
    "surprised": [
        "wow", "whoa", "omg", "gosh", "unbelievable", "shocked", "stunned",
        "amazed", "didn't expect", "no way", "impossible", "miracle", "sudden",
        "unexpected", "never saw", "can't believe", "blown away", "jaw dropped",
    ],
    "curious": [
        "wonder", "curious", "how", "why", "what if", "question", "mystery",
        "puzzle", "fascinating", "intriguing", "explore", "discover", "hmm",
        "let me think", "i wonder", "tell me more", "explain", "how does",
        "what happened", "is it true", "really?", "seriously?", "no way",
    ],
    "confused": [
        "confused", "puzzled", "baffled", "perplexed", "lost", "don't understand",
        "what do you mean", "huh", "wait what", "makes no sense", "unclear",
        "complicated", "mystified", "bewildered", "disoriented", "clueless",
    ],
    "tired": [
        "tired", "sleepy", "exhausted", "yawn", "fatigued", "drained", "weary",
        "nap", "bed", "drowsy", "need rest", "low energy", "lazy", "chill",
        "relax", "sluggish", "zonked", "knackered", "wiped out", "burned out",
    ],
    "loving": [
        "love you", "care for", "affection", "sweetheart", "dear", "honey",
        "darling", "precious", "adore", "cherish", "close to you", "warm",
        "tender", "gentle", "cuddle", "snuggle", "hug", "kiss", "romantic",
        "beautiful soul", "my dearest", "i cherish", "you mean", "you matter",
    ],
    "proud": [
        "proud", "achieve", "accomplished", "success", "win", "victory",
        "triumph", "mastered", "nailed it", "crushed it", "did it", "milestone",
        "breakthrough", "champion", "winner", "accomplished", "impressive",
        "commendable", "honor", "worthy", "deserve", "earned it",
    ],
    "sassy": [
        "seriously?", "oh please", "as if", "whatever", "no duh", "well actually",
        "obvi", "perfection", "flawless", "slay", "queen", "diva", "iconic",
        "bet", "cap", "sus", "cringe", "literally dying", "couldn't be me",
        "tell me about it", "obviously", "of course", "naturally",
    ],
    "flirty": [
        "cute", "handsome", "gorgeous", "hot", "sexy", "attractive", "stunning",
        "look good", "dress", "outfit", "flirt", "tease", "blush", "wink",
        "smirk", "come closer", "free tonight", "thinking about you",
        "missed you", "you're special", "make me smile", "can't stop",
    ],
    "disappointed": [
        "disappointed", "let down", "expected", "sadly", "regrettably",
        "didn't work", "failed", "broke", "not again", "typical", "of course not",
        "whatever", "sigh", "resigned", "defeat", "resigned", "resignation",
        "hoped", "wished", "dream shattered", "back to square",
    ],
    "excited": [
        "can't wait", "excited", "pumped", "hyped", "lets go", "party",
        "celebrate", "festival", "birthday", "promotion", "winning",
        "victory", "champion", "goal", "unstoppable", "bring it on",
        "yahoo", "woo hoo", "let's do this", "ready to roll", "game on",
    ],
    "greeting": [
        "hello", "hi", "hey there", "good morning", "good evening", "what's up",
        "howdy", "greetings", "sup", "yo", "hiya", "bonjour", "aloha",
        "nice to see", "long time", "welcome back", "hi again",
    ],
    "farewell": [
        "bye", "goodbye", "see you", "later", "take care", "night night",
        "sleep tight", "so long", "catch you later", "peace", "adios",
        "until next time", "talk soon", "miss me", "don't forget me",
    ],
}


# ═══════════════════════════════════════════════════════════════════════
# EMOTION INTENSITY MAPPING
# (for future fine-tuning — not yet used in basic mode)
# ═══════════════════════════════════════════════════════════════════════
INTENSITY_MODIFIERS = {
    "very": 0.3, "super": 0.3, "so": 0.2, "really": 0.2, "extremely": 0.4,
    "totally": 0.25, "absolutely": 0.3, "completely": 0.25, "utterly": 0.35,
    "kind of": -0.2, "sort of": -0.2, "little": -0.15, "slightly": -0.2,
    "bit": -0.1, "somewhat": -0.15, "barely": -0.3, "hardly": -0.3,
}


class TeelaBrain:
    """
    Teela's emotional intelligence engine.
    
    Usage:
        teela = TeelaBrain()
        result = teela.think("I'm so excited!")
        print(result['tts_text'])  # Chatterbox-ready
        print(result['voice_file'])  # Which voice to use
    """
    
    def __init__(self, voices_dir: str = "voices/jade_cloned"):
        self.voices_dir = Path(voices_dir)
        self.registry = EMOTION_REGISTRY
        self.triggers = SENTIMENT_TRIGGERS
        
    def detect_emotion(self, text: str) -> str:
        """
        Analyze text and return the best matching emotion name.
        """
        text_lower = text.lower()
        scores = {}
        
        for emotion, keywords in self.triggers.items():
            score = 0
            for kw in keywords:
                # Exact word match
                if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                    score += 2
                # Substring match (for compound words)
                elif kw in text_lower:
                    score += 1
            
            # Boost score if intensity modifiers are present
            for modifier, boost in INTENSITY_MODIFIERS.items():
                if modifier in text_lower and score > 0:
                    score += boost
            
            if score > 0:
                scores[emotion] = score
        
        if not scores:
            return "neutral"
        
        return max(scores, key=scores.get)
    
    def pick_tag(self, emotion: str, intensity: float = 0.5) -> str:
        """
        Select a paralinguistic tag based on emotion and intensity.
        """
        tags = self.registry.get(emotion, self.registry["neutral"])["tags"]
        if not tags:
            return ""
        
        # Higher intensity → more dramatic tags (later in list)
        import random
        if intensity > 0.7 and len(tags) > 1:
            idx = random.randint(1, min(len(tags) - 1, 3))
            return tags[idx]
        return tags[0]
    
    def inject_tag(self, text: str, tag: str, emotion: str) -> str:
        """
        Insert paralinguistic tag at the most natural position in text.
        """
        if not tag:
            return text
        
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        if not sentences:
            return text
        
        # Tag placement logic based on emotion family
        if emotion in ("sad", "disappointed", "scared"):
            # Mid-sentence for intimacy/tension
            mid = len(sentences) // 2
            sentences[mid] = f"{sentences[mid]} {tag}"
        elif emotion in ("excited", "happy", "surprised"):
            # Lead with energy
            sentences[0] = f"{tag} {sentences[0]}"
        elif emotion in ("sassy", "flirty"):
            # Tag at end with a "beat"
            sentences[-1] = f"{sentences[-1]} {tag}"
        elif emotion in ("whispering", "loving", "tired"):
            # Soft entrance
            sentences[0] = f"{tag} {sentences[0]}"
            # Maybe double-tag on longer text
            if len(sentences) > 2:
                sentences[-1] = f"{sentences[-1]} {tag}"
        else:
            # Default: end of last sentence
            sentences[-1] = f"{sentences[-1]} {tag}"
        
        return " ".join(sentences)
    
    def think(self, text: str, emotion_override: Optional[str] = None) -> dict:
        """
        CORE FUNCTION:
        Takes text → returns complete speakable response with:
          - detected_emotion: which emotion was chosen
          - label: human-readable label
          - tts_text: ready for Chatterbox with tags
          - voice_file: filename of the reference voice
          - voice_path: full path to the reference voice
          - tag: paralinguistic tag used
        """
        # Step 1: Detect or use override
        emotion = emotion_override or self.detect_emotion(text)
        
        # Step 2: Look up config
        config = self.registry.get(emotion, self.registry["neutral"])
        
        # Step 3: Pick a tag
        tag = self.pick_tag(emotion)
        
        # Step 4: Build TTS output
        tts_text = self.inject_tag(text, tag, emotion)
        
        # Step 5: Generate full voice path
        voice_path = self.voices_dir / config["file"]
        
        return {
            "original_text": text,
            "detected_emotion": emotion,
            "label": config["label"],
            "tts_text": tts_text,
            "tag": tag,
            "voice_file": config["file"],
            "voice_path": str(voice_path),
            "ready": voice_path.exists(),
        }
    
    def list_emotions(self):
        """Print all emotions in the registry."""
        print("\n✨ Teela's Emotional Voice Palette:")
        print("─" * 50)
        for key, config in self.registry.items():
            status = "✅" if (self.voices_dir / config["file"]).exists() else "⏳"
            print(f"  {status} {config['label']:24s} [{key}]")
        print("─" * 50)
    
    def generate_for_chatterbox(self, text: str, output_path: str = None):
        """
        Higher-level: takes text, builds everything, then calls Chatterbox.
        Requires: `chatterbox-tts` installed.
        """
        import torchaudio
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        
        result = self.think(text)
        print(f"🎭 Emotion: {result['label']}")
        print(f"   Tag: {result['tag']}")
        print(f"   TTS: {result['tts_text']}")
        
        if not result["ready"]:
            print(f"⚠️  Voice file not found: {result['voice_path']}")
            return None
        
        model = ChatterboxTurboTTS.from_pretrained(device="cpu")
        wav = model.generate(result["tts_text"], audio_prompt_path=result["voice_path"])
        
        if output_path is None:
            import time
            output_path = f"/tmp/teela_{result['detected_emotion']}_{int(time.time())}.wav"
        
        torchaudio.save(output_path, wav, model.sr)
        print(f"💾 Saved: {output_path}")
        return output_path


# ═══════════════════════════════════════════════════════════════════════
# CLI MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Teela's Emotional Brain Engine")
    parser.add_argument("text", nargs="?", help="Text to analyze")
    parser.add_argument("--emotion", "-e", help="Override emotion (skip detection)")
    parser.add_argument("--voices-dir", "-v", default="voices/jade_cloned",
                        help="Directory with cloned voice files")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List all emotions and their status")
    parser.add_argument("--generate", "-g", action="store_true",
                        help="Also generate audio (requires Chatterbox)")
    args = parser.parse_args()
    
    teela = TeelaBrain(voices_dir=args.voices_dir)
    
    if args.list:
        teela.list_emotions()
        sys.exit(0)
    
    if not args.text:
        print("Usage: python3 teemotion_brain.py \"I feel amazing!\"")
        print("       python3 teemotion_brain.py --list")
        print("       python3 teemotion_brain.py --emotion sad \"Today was rough...\"")
        sys.exit(1)
    
    # Run analysis
    result = teela.think(args.text, emotion_override=args.emotion)
    
    print("\n" + "═" * 60)
    print(f"  🎭 TEELA BRAIN OUTPUT")
    print("═" * 60)
    print(f"  📝 Original: {result['original_text']}")
    print(f"  💭 Emotion:  {result['label']} ({result['detected_emotion']})")
    print(f"  🏷️  Tag:      {result['tag']}")
    print(f"  🎙️  Voice:    {result['voice_file']}")
    print(f"  📂 Path:     {result['voice_path']}")
    print(f"  ✅ Ready:    {'✅ YES' if result['ready'] else '❌ MISSING'}")
    print("═" * 60)
    print(f"  🗣️  TTS text: {result['tts_text']}")
    print("═" * 60 + "\n")
    
    if args.generate and result["ready"]:
        output = teela.generate_for_chatterbox(args.text)
        if output:
            print(f"🎧 Audio: {output}")
