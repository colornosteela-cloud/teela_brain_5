# Pointing Gesture Understanding

## Overview

Teela can understand when a human points at an object in her field of view.
This is called **deictic gesture understanding** — one of the most natural
ways for humans to communicate intent to robots.

## How It Works

1. **Pose Detection**: MediaPipe extracts body keypoints (shoulder, elbow, wrist).
2. **Pointing Detection**: If the wrist is farther from the shoulder than the elbow,
   and the arm is roughly straight (dot product > 0.6), the person is pointing.
3. **Ray Casting**: A ray is cast from the wrist in the direction of the forearm.
4. **Object Matching**: The nearest scene object within an angular tolerance is selected.
5. **Scene State Update**: `scene_state.json` now includes a `pointed_at` field with:
   - `object_id`: track ID of the pointed object
   - `name`: class name (e.g., "cup", "chair")
   - `confidence`: pointing certainty (0.0–1.0)
   - `pixel_distance`: screen-space distance from hand to object

## Architecture

```
Camera frame
    → MediaPipe Pose
    → PointingDetector.compute_pointing_ray()
    → PointingSceneIntegrator.update_scene_state()
    → scene_state.json (now contains "pointed_at")
    → Cloud LLM sees: "The user is pointing at the {name}"
```

## Usage

### In the perception loop:

```python
from teela_core.perception.scene_understanding import SceneUnderstanding
from teela_core.gestures.pointing_integration import PointingSceneIntegrator

scene = SceneUnderstanding()
pointing = PointingSceneIntegrator()

frame = scene.capture()
state = scene.process_frame(frame)
state = pointing.update_scene_state(frame, state)
# state.pointed_at now contains the target
```

### Standalone test:

```bash
pip install mediapipe opencv-python
python3 -m scripts.test_pointing --camera 0
```

## Integration with Cloud Reasoning

When `pointed_at` is present in scene_state, the LLM prompt automatically receives:

```
Scene state:
{
  ...,
  "pointed_at": {
    "object_id": 3,
    "name": "cup",
    "confidence": 0.78,
    "pixel_distance": 145.2
  }
}
```

The LLM can then respond:
- "You are pointing at the **cup**."
- "I see you're pointing at the **chair** on the left."
- "I don't recognize what you're pointing at."

## Known Limitations

- Requires MediaPipe pose or similar → ~5-15 FPS on Jetson
- Only works if the person's arm is visible in frame
- Depth from pointing ray requires camera calibration + known object sizes for true 3D accuracy
- Ambiguous when multiple objects align with the ray (closest in pixel space wins)

## Future Improvements

- [ ] Use wrist/finger direction instead of wrist-only for finer accuracy
- [ ] Incorporate gaze (nose → eye direction) + pointing for disambiguation
- [ ] Use V-JEPA action anticipation to predict *why* the user is pointing
- [ ] Support "point there and tap foot" combinatory gestures
