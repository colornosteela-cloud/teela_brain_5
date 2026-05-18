"""
Prosody Engine: Voice modulation for emotional expression

Maps emotional state to speech parameters:
    - Speaking rate (arousal)
    - Pitch (valence + arousal)
    - Volume (dominance)
    - Pause patterns (thoughtfulness)
    - Interjections/hesitations (uncertainty)
    - Color words (happier = warmer words, anxious = more "um", "uh")
"""

import random
from typing import Dict, Optional


class ProsodyEngine:
    """Modulates text generation and speech synthesis parameters."""

    def __init__(self):
        self.last_speech_params: Optional[Dict] = None

    def compute_speech_params(self, emotional_state: Dict) -> Dict:
        """Convert emotion to TTS parameters."""
        valence = emotional_state.get("pleasure", 0)
        arousal = emotional_state.get("arousal", 0)
        dominance = emotional_state.get("dominance", 0)

        # Speed: excited = faster, sad/bored = slower
        words_per_minute = 140 + (arousal * 40) + (valence * 10)

        # Pitch shift: +50Hz for excitement, -30Hz for sadness
        pitch_shift_hz = int(arousal * 50 + valence * 30)

        # Volume intensity
        volume_db = -12 + dominance * 6 + arousal * 3

        # Pause frequency
        pause_rate = max(0, 0.1 - arousal * 0.08)  # calm = more pauses

        params = {
            "wpm": int(words_per_minute),
            "pitch_shift_hz": pitch_shift_hz,
            "volume_db": int(volume_db),
            "pause_rate": round(pause_rate, 3),
            "use_breaths": arousal < 0.3,  # calmer speech = audible breaths
        }
        self.last_speech_params = params
        return params

    def inject_prosody_markers(self, text: str, emotional_state: Dict) -> str:
        """Add SSML/emotion markers to text for TTS."""
        valence = emotional_state.get("pleasure", 0)
        arousal = emotional_state.get("arousal", 0)
        dominant_emotion = emotional_state.get("dominant_emotion", "neutral")
        
        markers = []
        
        if dominant_emotion == "joy":
            markers.append("[cheerful]")
        elif dominant_emotion == "sadness":
            markers.append("[sad]")
        elif dominant_emotion == "anger":
            markers.append("[firm]")
        elif dominant_emotion == "fear":
            markers.append("[gentle]")
        elif dominant_emotion == "surprise":
            markers.append("[excited]")
        
        # Add hesitation if anxious or uncertain
        if arousal > 0.5 and valence < 0:
            # Insert occasional "um" in longer sentences
            words = text.split()
            if len(words) > 8 and random.random() < 0.3:
                split_point = len(words) // 2
                text = " ".join(words[:split_point]) + ", um, " + " ".join(words[split_point:])

        if markers:
            return markers[0] + " " + text
        return text
