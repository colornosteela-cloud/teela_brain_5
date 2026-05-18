# Teela Brain — Emotion Intelligence System
# ==============================================
# This module maps text sentiment to the best Chatterbox emotion
# and auto-generates paralinguistic tags in responses.

import re
import json
from pathlib import Path

# ── Emotion Registry (maps semantic tags → voice files + paralinguistics) ──
EMOTION_REGISTRY = {
    # Original 5 emotions
    "general": {
        "voice_file": "teela_clone_01_happy.wav",
        "label": "neutral/calm",
        "tags_allowed": ["[whisper]", "[chuckle]", "[laugh]"],
    },
    "happy": {
        "voice_file": "teela_clone_01_happy.wav",
        "label": "😄 Happy",
        "tags_allowed": ["[laugh]", "[chuckle]", "[cheer]", "[whoop]"],
    },
    "surprised": {
        "voice_file": "teela_clone_02_surprised.wav",
        "label": "😲 Surprised",
        "tags_allowed": ["[gasp]", "[exclaim]", "[whisper]"],
    },
    "angry": {
        "voice_file": "teela_clone_03_angry.wav",
        "label": "😡 Angry",
        "tags_allowed": ["[sigh]", "[shout]", "[grunt]"],
    },
    "proud": {
        "voice_file": "teela_clone_04_proud.wav",
        "label": "💪 Proud",
        "tags_allowed": ["[cheer]", "[laugh]"],
    },
    "whispering": {
        "voice_file": "teela_clone_05_whispering.wav",
        "label": "🤫 Whispering",
        "tags_allowed": ["[whisper]", "[cough]", "[breathe]"],
    },
    # New 10 emotions
    "sad": {
        "voice_file": "teela_clone_06_sad.wav",
        "label": "😢 Sad",
        "tags_allowed": ["[whisper]", "[sigh]", "[breathe]", "[gasp]"],
    },
    "curious": {
        "voice_file": "teela_clone_07_curious_awed.wav",
        "label": "🤩 Curious & Awed",
        "tags_allowed": ["[gasp]", "[laugh]", "[exclaim]", "[wonder]"],
    },
    "sassy": {
        "voice_file": "teela_clone_08_sassy.wav",
        "label": "💅 Sassy",
        "tags_allowed": ["[laugh]", "[chuckle]", "[whisper]"],
    },
    "flirty": {
        "voice_file": "teela_clone_09_flirty.wav",
        "label": "😘 Flirty",
        "tags_allowed": ["[chuckle]", "[whisper]", "[breathe]"],
    },
    "sleepy": {
        "voice_file": "teela_clone_10_sleepy.wav",
        "label": "😴 Sleepy",
        "tags_allowed": ["[yawn]", "[breathe]", "[whisper]"],
    },
    "scared": {
        "voice_file": "teela_clone_11_scared.wav",
        "label": "😨 Scared",
        "tags_allowed": ["[gasp]", "[whisper]", "[shudder]"],
    },
    "loving": {
        "voice_file": "teela_clone_12_loving.wav",
        "label": "💖 Loving",
        "tags_allowed": ["[chuckle]", "[whisper]", "[breathe]"],
    },
    "confused": {
        "voice_file": "teela_clone_13_confused.wav",
        "label": "🤔 Confused",
        "tags_allowed": ["[murmur]", "[sigh]", "[whisper]"],
    },
    "excited": {
        "voice_file": "teela_clone_14_excited.wav",
        "label": "🥳 Excited",
        "tags_allowed": ["[cheer]", "[laugh]", "[whoop]", "[exclaim]"],
    },
    "disappointed": {
        "voice_file": "teela_clone_15_disappointed.wav",
        "label": "😞 Disappointed",
        "tags_allowed": ["[sigh]", "[whisper]", "[murmur]"],
    },
}

# ── Sentiment Detection Patterns ───────────────────────────────────────
SENTIMENT_PATTERNS = {
    "sad": [
        "sad", "cry", "cryi", "tear", "tears", "miss you", "lonely", "hurt", "pain",
        "upset", "depressed", "sorry", "regret", "heartbroken", "lost", "grief",
        "mourn", "broken", "down", "blue", "melancholy", "nostalgic", "gloomy",
    ],
    "fear": [
        "scared", "afraid", "fear", "terrified", "spooky", "creepy", "scary",
        "haunted", "monster", "ghost", "dark", "alone", "panic", "anxious",
        "nervous", "worry", "worried", "worrying", "tense", "uneasy", "cautious",
    ],
    "angry": [
        "angry", "mad", "furious", "pissed", "rage", "hate", "stupid", "idiot",
        "annoy", "annoyed", "frustrated", "unfair", "cheated", "robbed", "wronged",
        "insult", "offended", "outraged", "infuriated", "irritated", "jerk",
    ],
    "happy": [
        "happy", "joy", "glad", "cheerful", "great", "wonderful", "awesome",
        "amazing", "love", "lovely", "fantastic", "beautiful", "perfect",
        "excited", "thrilled", "delighted", "blessed", "grateful", "smile",
        "laugh", "laughed", "funny", "hilarious", "giggle", "giggling",
    ],
    "surprised": [
        "wow", "whoa", "omg", "gosh", "unbelievable", "incredible", "shocked",
        "stunned", "amazed", "astonished", "didn't expect", "no way", "what!?",
        "holy", "impossible", "miracle", "sudden", "unexpected",
    ],
    "curious": [
        "wonder", "curious", "how", "why", "what if", "maybe", "question",
        "mystery", "puzzle", "strange", "odd", "fascinating", "intriguing",
        "interested", "explore", "discover", "hmm", "let me think", "i wonder",
    ],
    "confused": [
        "confused", "puzzled", "baffled", "perplexed", "lost", "don't understand",
        "what do you mean", "huh", "wait what", "mind blown", "makes no sense",
        "unclear", "complicated", "complex", "mystified",
    ],
    "tired": [
        "tired", "sleepy", "exhausted", "yawn", "fatigued", "drained", "weary",
        "nap", "bed", "sleep", "drowsy", "burned out", "need rest", "low energy",
        "lazy", "couch", "chill", "relax", "relaxing",
    ],
    "loving": [
        "love you", "miss you", "care", "affection", "sweet", "dear", "honey",
        "darling", "precious", "treasure", "adore", "cherish", "close to you",
        "warm", "tender", "gentle", "cuddle", "snuggle", "hug", "kiss",
        "heart", "romantic", "beautiful soul", "my dearest",
    ],
    "proud": [
        "proud", "achieve", "accomplished", "success", "win", "won", "victory",
        "triumph", "mastered", "nailed it", "crushed it", "did it", "finished",
        "graduated", "promotion", "bonus", "milestone", "breakthrough",
    ],
    "sassy": [
        "seriously?", "oh please", "as if", "whatever", "eye roll", "obviously",
        "duh", "no duh", "literally", "actually", "technically", "well actually",
        "not my problem", "told you so", "obvi", "perfection", "flawless",
        "slay", "queen", "diva", "iconic", "bet", "cap", "sus",
    ],
    "flirty": [
        "cute", "handsome", "pretty", "gorgeous", "hot", "sexy", "attractive",
        "stunning", "beautiful", "look good", "dress", "outfit", "flirt",
        "flirty", "tease", "blush", "shy", "nervous laugh", "wink", "smirk",
        "come closer", "what are you doing later", "free tonight",
    ],
    "disappointed": [
        "disappointed", "let down", "expected better", "thought you", "sadly",
        "unfortunately", "regrettably", "didn't work", "failed", "broke",
        "not again", "same old", "typical", "sigh", "of course not", "whatever",
    ],
    "excited": [
        "can't wait", "so excited", "pumped", "hyped", "lets go", "party",
        "celebrate", "festival", "birthday", "graduation", "promotion",
        "winning", "victory", "champion", "goal", "score", "unstoppable",
        "let's do this", "bring it on", "here we go", "yahoo", "woo hoo",
    ],
}


def detect_emotion(text: str) -> str:
    """Detect the dominant emotion from text input."""
    text_lower = text.lower()
    scores = {}
    
    for emotion, keywords in SENTIMENT_PATTERNS.items():
        score = 0
        for kw in keywords:
            if kw in text_lower:
                # Boost multi-word matches
                score += 2 if " " in kw else 1
            # Check word boundary matches using regex
            if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                score += 1
        if score > 0:
            scores[emotion] = score
    
    if not scores:
        return "general"  # Default
    
    # Return highest scoring emotion
    return max(scores, key=scores.get)


def get_paralinguistic_tag(emotion: str, intensity: float = 0.5) -> str:
    """Get a contextual paralinguistic tag for the emotion."""
    tags = EMOTION_REGISTRY.get(emotion, EMOTION_REGISTRY["general"])["tags_allowed"]
    if not tags:
        return ""
    
    # Simple selection — first tag is the "signature" for that emotion
    import random
    if intensity > 0.7 and len(tags) > 1:
        return random.choice(tags[1:])  # More intense = secondary tags
    return tags[0]


def teela_speak(text: str, emotion_override: str = None, intensity: float = 0.5) -> dict:
    """
    Core function: analyze text → pick emotion → inject paralinguistic tags.
    
    Returns a dict with:
      - 'original_text': what the user said
      - 'detected_emotion': the AI-chosen emotion
      - 'tts_text': text ready for Chatterbox with tags injected
      - 'voice_file': which reference voice to use
      - 'label': human-readable emotion label
    """
    
    # Step 1: Detect or override emotion
    emotion = emotion_override or detect_emotion(text)
    
    # Step 2: Get emotion config
    config = EMOTION_REGISTRY.get(emotion, EMOTION_REGISTRY["general"])
    
    # Step 3: Get paralinguistic tag
    tag = get_paralinguistic_tag(emotion, intensity)
    
    # Step 4: Inject tag into text intelligently
    tts_text = inject_tag(text, tag, emotion, intensity)
    
    return {
        "original_text": text,
        "detected_emotion": emotion,
        "tts_text": tts_text,
        "voice_file": config["voice_file"],
        "label": config["label"],
        "tag_used": tag,
    }


def inject_tag(text: str, tag: str, emotion: str, intensity: float = 0.5) -> str:
    """Inject a paralinguistic tag at the most natural point in the text."""
    if not tag:
        return text
    
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if not sentences:
        return text
    
    # Strategy: emotional tags go at the "peak" of the sentence
    if emotion in ("sad", "disappointed", "scared", "loving"):
        # Add tag mid-sentence for intimacy/tension
        mid = len(sentences) // 2
        sentences[mid] = f"{sentences[mid]} {tag}"
    elif emotion in ("excited", "happy", "curious", "surprised"):
        # Add tag early for energy
        sentences[0] = f"{tag} {sentences[0]}"
    elif emotion in ("sassy", "flirty"):
        # Add tag at the end with a pause
        sentences[-1] = f"{sentences[-1]} {tag}"
    else:
        # Default: end of sentence
        sentences[-1] = f"{sentences[-1]} {tag}"
    
    return " ".join(sentences)


def get_voice_path(emotion: str, voices_dir: str = "voices/jade_cloned") -> str:
    """Get the full path to the voice file for an emotion."""
    config = EMOTION_REGISTRY.get(emotion, EMOTION_REGISTRY["general"])
    return str(Path(voices_dir) / config["voice_file"])


def list_all_emotions():
    """Print all available emotions."""
    print("✨ Teela's Emotional Voice Palette:")
    print("=" * 50)
    for key, config in EMOTION_REGISTRY.items():
        print(f"  {config['label']:20s} → {config['voice_file']}")
    print("=" * 50)


# ── Simple CLI Test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python teela_emotion_brain.py 'Your text here'")
        print("\nAvailable emotions:")
        list_all_emotions()
        sys.exit(0)
    
    input_text = " ".join(sys.argv[1:])
    result = teela_speak(input_text)
    
    print("\n🎭 Teela Emotion Analysis:")
    print(f"   Input: {result['original_text']}")
    print(f"   Emotion: {result['label']} ({result['detected_emotion']})")
    print(f"   Tag: {result['tag_used']}")
    print(f"   TTS-ready: {result['tts_text']}")
    print(f"   Voice file: {result['voice_file']}")
