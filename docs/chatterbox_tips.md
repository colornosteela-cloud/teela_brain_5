# 🎙️ Chatterbox-Turbo Tips for Teela — Quick Reference

## 🏷️ Paralinguistic Tags (Built-in Emotions)

These tags are **baked into the model** — they produce actual sounds, not just prosody changes:

| Tag | Sound Effect | Example |
|-----|--------------|---------|
| `[laugh]` | Genuine laughter | "That's hilarious! [laugh]" |
| `[chuckle]` | Soft chuckle/giggle | "I knew you'd say that [chuckle]" |
| `[cough]` | Cough sound | "Excuse me [cough], as I was saying..." |
| `[sigh]` | Audible sigh | "Oh well... [sigh] maybe next time" |
| `[gasp]` | Sharp intake of breath | "[gasp] You did WHAT?!" |
| `[sniffle]` | Sniffle sound | "I'm not crying... [sniffle]" |
| `[yawn]` | Yawn | "It's so late... [yawn]" |
| `[groan]` | Groan | "Ugh, not again... [groan]" |
| `[sneeze]` | Sneeze | "Ah... ah... [sneeze] bless me" |
| `[mmm]` | Thoughtful hum | "[mmm] let me think about that" |

> 💡 **Tip**: Tags work best mid-sentence or at natural pauses. Don't put them at the very start.

---

## 🎛️ Voice Tuning Parameters

### `cfg_weight` (0.0 - 1.0, default: 0.5)
Controls **pacing and adherence** to the text:
- **0.5** → Natural, balanced (default)
- **0.3** → Slower, more deliberate, calmer
- **0.2** → Very slow, dramatic pauses
- **0.7** → Faster, more literal reading

### `exaggeration` (0.0 - 1.0, default: 0.5)
Controls **expressiveness and emotion intensity**:
- **0.5** → Natural expressiveness (default)
- **0.7** → More animated, dramatic
- **0.8+** → Very theatrical, faster speech
- **0.3** → Flat, monotone (robotic)

---

## 🎭 Teela's Recommended Settings by Mood

| Teela's Mood | cfg_weight | exaggeration | Why |
|--------------|------------|--------------|-----|
| 😊 Normal chatting | 0.5 | 0.5 | Balanced, friendly |
| 😄 Happy/excited | 0.5 | 0.7 | Animated but natural pace |
| 😡 Angry/shouting | 0.3 | 0.7 | Dramatic but paced (not too fast) |
| 😢 Sad/reflective | 0.3 | 0.5 | Slow, calm, melancholic |
| 🤫 Whispering/teasing | 0.2 | 0.8 | Slow, dramatic, intimate |
| 😲 Surprised/shocked | 0.5 | 0.7 | Animated response |
| 😴 Tired/sleepy | 0.2 | 0.5 | Very slow, low energy |

> 💡 **Resemble's Pro Tip**: If the reference speaker talks fast, lower `cfg_weight` to ~0.3 to prevent rushed speech.

---

## 🗣️ Voice Cloning (Make Teela Sound Like Anyone!)

```python
# 1. Record a 10-second reference clip
#    On Jetson: arecord -d 10 -f cd -t wav /tmp/my_voice.wav

# 2. Generate with that voice
wav = model.generate(
    "Hey there! I'm Teela!",
    audio_prompt_path="/tmp/my_voice.wav"
)
```

- **10 seconds** is the sweet spot
- Clear speech, no background noise
- The voice will match the reference's tone, accent, and speaking style
- If the reference has a fast style, lower `cfg_weight` to compensate

---

## ⚡ Speed vs Quality Trade-offs

| Setting | Speed | Quality | Best For |
|---------|-------|---------|----------|
| Default | Baseline | Best | Most emotions |
| cfg=0.3, exag=0.7 | Slightly slower | Best drama | Angry, whispering |
| cfg=0.5, exag=0.7 | Baseline | Very good | Happy, excited |
| No tags | Fastest | Good | Neutral narration |

---

## 🧪 Quick Test Commands

```bash
# Play all tuning samples:
for f in /tmp/teela_tuning_*.wav; do echo "▶ $(basename $f)"; gst-play-1.0 --quiet "$f"; sleep 1; done

# Play all emotion samples:
for f in /tmp/teela_chatterbox_*.wav; do echo "▶ $(basename $f)"; gst-play-1.0 --quiet "$f"; sleep 1; done

# Record your own 10s voice sample:
arecord -d 10 -f cd -t wav /tmp/my_voice_ref.wav
```

---

*From: https://github.com/resemble-ai/chatterbox | Chatterbox-Turbo by Resemble AI*
