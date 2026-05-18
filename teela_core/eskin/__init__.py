Electronic skin (e-skin) distributed body-touch sensory system.

Teela's silicone skin layer is embedded with pressure sensors (Velostat,
FSR, etc.) across her body. This module processes raw sensor values,
classifies touch events by zone and intensity, and feeds body awareness.

Architecture:
    Raw ADC values → Smoothing → Baseline subtraction → Zone mapping
    → Intensity classification → Touch event → Body state / Reflex / Emotion

Body zones are organized hierarchically:
    face.left / face.right / forehead / cheek.left / cheek.right
    neck.front / neck.back
    shoulder.left / shoulder.right
    arm.left.upper / arm.left.lower / arm.right.upper / arm.right.lower
    hand.left.palm / hand.left.back / hand.right.palm / hand.right.back
    torso.front.upper / torso.front.lower / torso.back.upper / torso.back.lower
    hip.left / hip.right
    leg.left.upper / leg.left.lower / leg.right.upper / leg.right.lower

Sensor fusion: if multiple adjacent zones fire simultaneously,
the likely cause is a broad touch, not multiple independent events.
