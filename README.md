# Teela Brain v5.0 🤖

**Hybrid edge-cloud humanoid robot brain** for Jetson Orin Nano + Teensy 4.1.

> Perception (V-JEPA 2) → Navigation (A* + DWA) → Reflex (safety) → Gait (1kHz on Teensy) → Cloud reasoning (Kimi K2.6)

## Quick Start

### Edge (Jetson)

```bash
# 1. Clone and install
git clone https://github.com/colornosteela-cloud/teela_brain_5.git
cd teela_brain_5
pip install -e ".[jetson]"

# 2. Configure
# Edit config.yaml with your camera, serial port, cloud URI

# 3. Bringup
teela-bringup

# 4. Start perception
python -m teela_core.perception.scene_understanding &

# 5. Start navigation
python -m teela_core.navigation.path_planner &

# 6. Bridge to cloud
python -m teela_core.comms.cloud_bridge &
```

### Teensy Firmware

```bash
cd teensy_firmware
# Install PlatformIO: https://platformio.org/install
pio run --target upload
```

### Cloud Reasoning

```bash
# Set your LLM endpoint
export LLM_API_URL="http://your-cloud-node:8000/v1/chat/completions"

# Start reasoning loop
python -m cloud_reasoning.reasoner
```

## System Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full details.

## Hardware Requirements

| Component | Spec | Role |
|-----------|------|------|
| Jetson Orin Nano Super | 67 TOPS, 8GB RAM | Perception + navigation + comms |
| Teensy 4.1 | 600MHz ARM Cortex-M7 | Real-time gait + servo control |
| PCA9685 | 16ch PWM driver | Servo outputs |
| MPU6050 / BNO055 | I2C IMU | Balance sensing |
| USB Camera | ≥720p | Vision |
| HC-SR04 / ToF | Ultrasonic/distance | Proximity safety |
| 12x servos | ≥20kg-cm torque | Leg joints |

## Multitasking

Teela can **walk + avoid obstacles simultaneously** because:
- Teensy runs a **never-blocking 1kHz gait loop**
- Jetson sends **target pose updates** asynchronously
- Reflex layer can **halt instantly** if an obstacle appears
- Cloud reasoning plans **high-level goals** while the robot moves

See [ARCHITECTURE.md](ARCHITECTURE.md) § Timing Hierarchy for details.

## License

MIT — Colornosteela-cloud
