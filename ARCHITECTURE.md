# Teela Brain v5.0 Architecture

## System Overview

Teela is a **hybrid edge-cloud humanoid robot brain** built for the Jetson Orin Nano + Teensy 4.1 platform.

```
┌─────────────────────────────────────────────────────────────┐
│  CLOUD (optional)                                           │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Kimi K2.6 / OpenAI-compatible LLM                   │    │
│  │  • Reasoning about user intent                       │    │
│  │  • Long-horizon planning                             │    │
│  │  • Natural language understanding                    │    │
│  └──────────────────────────────────────────────────────┘    │
│         ↑↓ websockets (Tailscale)                            │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  EDGE: Jetson Orin Nano Super (67 TOPS, 8GB RAM)            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │ Perception   │  │ Navigation   │  │ Reflex Layer     │    │
│  │ V-JEPA 2     │  │ A* + DWA     │  │ Emergency stop   │    │
│  │ Moondream2   │  │ Path planner │  │ Cliff detect     │    │
│  │ ~5-20 FPS    │  │ ~10 Hz       │  │ ~50-100 Hz       │    │
│  └──────────────┘  └──────────────┘  └──────────────────┘    │
│         ↓                 ↓                 ↓                 │
│  ┌──────────────────────────────────────────────────────┐    │
│  │           CloudBridge (WebSocket client)             │    │
│  │           SerialLink (to Teensy)                     │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │ USB serial @ 921600 baud
┌─────────────────────────────────────────────────────────────┐
│  REAL-TIME: Teensy 4.1 @ 600MHz                             │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Gait Engine (1kHz)                                   │    │
│  │ • Inverse kinematics                                 │    │
│  │ • Balance compensation (IMU)                         │    │
│  │ • Servo PWM output (PCA9685)                         │    │
│  │ • Serial command parser                              │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Timing Hierarchy

| Layer | Frequency | Latency Budget | Processor |
|-------|-----------|----------------|-----------|
| Servo output | 1kHz | <1ms | Teensy 4.1 |
| IMU / balance | 1kHz | <1ms | Teensy 4.1 |
| Gait interpolation | 1kHz | <1ms | Teensy 4.1 |
| Reflex / emergency stop | 50-100Hz | <10ms | Teensy or Jetson |
| Perception (V-JEPA) | 5-20 FPS | <100ms | Jetson |
| Path planning (A*/DWA) | 10 Hz | <100ms | Jetson |
| Scene understanding | 5-10 Hz | <200ms | Jetson |
| Cloud reasoning | 0.5-2 Hz | 1-3s | Cloud GPU |

## Communication Protocols

### Jetson → Teensy (Serial @ 921600 baud)
```
TARGET <x_m> <y_m> <yaw_rad> <max_speed_mps> <gait>

HALT

EMERGENCY_PARK

PING

Teensy → Jetson:
STATUS <x_m> <y_m> <yaw_rad> <pitch_deg> <roll_deg> <fallen>

ACK<cmd>

PONG

```

### Jetson ↔ Cloud (WebSocket over Tailscale)
```json
{"type": "scene_state", "data": {...}, "t": 1234567890.0}
{"type": "telemetry", "data": {...}, "t": 1234567890.0}
{"type": "action", "action_type": "move", "parameters": {...}}
```

## Safety Architecture

**Reflex Layer**:
- Ultrasonic / ToF distance threshold: 0.4m = emergency, 0.8m = caution
- IMU tilt threshold: >25° = halt, >30° = emergency park
- Cliff detection: sudden drop = immediate halt
- EMERGENCY_PARK: slow freeze-dance to ground, then lock joints

## File Structure

```
teela_brain_5/
├── teela_core/
│   ├── perception/          # V-JEPA 2, object tracking, scene state
│   ├── navigation/          # A*, DWA path planner, gait targets
│   ├── reflex/              # Safety layer, emergency stop
│   ├── comms/               # Serial (Teensy), WebSocket (cloud)
│   └── gait/                # Trajectory planning, IK stubs
├── cloud_reasoning/
│   ├── reasoner.py          # LLM reasoning engine
│   └── action_dispatcher.py # Route actions to subsystems
├── teensy_firmware/
│   ├── src/main.cpp         # Gait engine (1kHz loop)
│   ├── include/gait_engine.hpp
│   └── platformio.ini
├── scripts/
│   ├── bringup.py           # System health check
│   ├── health_check.py      # Continuous monitoring
│   └── calibrate_camera.py  # Camera calibration
├── tests/                   # Unit tests
├── docs/
├── config.yaml              # Robot configuration
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Design Principles

1. **Fast at the bottom:** Real-time loop on Teensy, never blocking
2. **Smart at the top:** Cloud LLM for reasoning, not time-critical
3. **Safe in the middle:** Reflex layer can override everything
4. **Testable:** Pure math in headers, mockable peripherals in Python
5. **Movable:** Scene state is JSON, model is swappable, serial protocol is fixed
