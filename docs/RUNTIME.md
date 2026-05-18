# Teela Runtime Guide

This guide helps you deploy Teela on the **Jetson Nano Orin** with her
 **current physical hardware**: eyes (camera), ears (microphone), and neck
(pan/tilt servos).

---

## 📋 Hardware Setup

### What You Need to Have Built

| Component | Status | Required | Notes |
|-----------|--------|----------|-------|
| Jetson Nano Orin | ✅ Required | JetPack 6.x | Python 3.10+ |
| USB Camera | ✅ Required | Any UVC camera | /dev/video0 |
| USB Microphone | ✅ Required | Any USB mic | ALSA device |
| Teensy 4.1 | ✅ Required | Running neck firmware | USB Serial |
| Pan Servo | ✅ Required | MG996R or equivalent | 180° range |
| Tilt Servo | ✅ Required | MG996R or equivalent | Pins 2 & 3 |
| Speaker | ⬜ Optional | Any ALSA output | fallback: stdout |
| Leg servos | ⬜ Future | Not needed yet | Placeholder in config |
| E-skin | ⬜ Future | Silicone + sensors | Placeholder in config |
| IMU | ⬜ Future | MPU6050/BNO055 | Placeholder in config |
| Ultrasonic | ⬜ Future | HC-SR04 | Placeholder in config |

### Wiring: Servos → Teensy 4.1

| Signal | Teensy Pin | Servo Wire |
|--------|-----------|------------|
| Neck PAN  | **2** | PWM (orange/yellow) |
| Neck TILT | **3** | PWM (orange/yellow) |
| GND | GND | Brown/black |
| +5V | VIN (if via USB) or external 5V | Red |

**Important**: Do NOT power MG996R servos from Teensy 3.3V.
Use external 5V supply or VIN if Teensy is powered by USB (5V from USB).
Teensy 4.1 can source ~250mA on 3.3V — servos draw 0.5–1.5A.
Use a separate 5V BEC or regulator.

---

## 🔧 Flashing the Teensy Firmware

### 1. Install PlatformIO

```bash
pip install platformio
```

### 2. Navigate to firmware

```bash
cd ~/teela_brain_5/teensy_firmware
```

### 3. Wire your servos, then build & upload

```bash
# Build
pio run

# Upload (Teensy will auto-enter bootloader briefly)
pio run --target upload
```

### 4. Verify in Serial Monitor

```bash
pio device monitor --baud 921600
```

You should see:
```
BOOT NECK_PANTILT v1.0
READY
```

Then type `PING` and press Enter — Teensy replies `ACK PONG`.

---

## 🚀 Running Teela

### 1. First-Time Setup

```bash
cd ~/teela_brain_5

# Install Python deps
pip install -r requirements.txt

# Set your Kimi API key
export KIMI_API_KEY="your-key-here"
# (add to ~/.bashrc so it persists)
```

### 2. Hardware Check

```bash
python3 -m scripts.bringup
```

This checks:
- Camera available
- Microphone found
- Teensy on Serial
- Network connectivity

If any check fails, the advice tells you exactly what to do.

### 3. Start the Brain

```bash
python3 -m scripts.conversation_loop
```

You will see:
```
Teela Runtime Mind — Starting...
✅ Teela is LIVE.
   Eyes:    OK
   Ears:    OK
   Neck:    OK
   Cloud:   Kimi API

[Teela 🗣️]  Hello. I'm Teela. My eyes are open and I'm listening.
```

Without a microphone, you'll see:
```
[YOU] Type what you want to say:
```

Just type and press Enter — Teela will respond via text (or speaker if `aplay` is configured).

---

## 🎙️ Try Pointing

Teela can understand pointing right now — you just need a webcam
that can see you.

```bash
python3 -m scripts.test_pointing
```

Show your hand to the camera, point at an object.
Teela will print what she thinks you're pointing at.

---

## 🔁 Auto-Start on Boot (systemd)

Install so Teela starts automatically when Jetson boots:

```bash
cd ~/teela_brain_5

# 1. Replace placeholder in service file with real API key
sudo sed -i "s|%KIMI_API_KEY%|$(echo $KIMI_API_KEY)|g" services/teela.service

# 2. Copy to systemd
sudo cp services/teela.service /etc/systemd/system/

# 3. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable teela.service
sudo systemctl start teela.service

# 4. Check status
sudo journalctl -u teela.service -f
```

To stop:
```bash
sudo systemctl stop teela.service
```

---

## 🐛 Troubleshooting

### Camera not detected
```bash
ls /dev/video*    # should show /dev/video0
v4l2-ctl --list-devices   # detailed info
sudo modprobe uvcvideo    # if driver missing
```

### Serial not found
```bash
ls /dev/ttyACM*    # should show /dev/ttyACM0 or ACM1
sudo chmod 666 /dev/ttyACM0    # permissions
sudo usermod -aG dialout $USER  # permanent fix (logout & back in)
```

### Teensy not responding
- Ensure Teensy is plugged in via USB
- Firmware uploaded correctly (check Serial Monitor for `READY`)
- Baud rate matches: config.yaml and firmware both set to 921600

### No sound
```bash
# Test
speaker-test -t sine -f 880

# Set default output
amixer sset 'Master' 80%
aplay /usr/share/sounds/alsa/Front_Center.wav
```

---

## 🗺️ What's Placeholder (Will Activate Later)

| Component | How It Works Now |
|-----------|------------------|
| **E-skin** | All code exists (`teela_core/eskin/`). When you install silicone skin & sensors, update `config.yaml: robot.capabilities.e_skin: true`. Then the brain will start reading touch events. |
| **Legs / Gait** | Complete gait planner exists (`teela_core/gait/`, `teensy_firmware/src/main.cpp`). When servos are installed, switch from `neck_pantilt.cpp` to `main.cpp` and bump `servos.count` to 12. |
| **IMU** | IMU fields exist in firmware. The Jetson already parses `STATUS` lines for IMU. Just wire MPU6050/BNO055 to I2C. |
| **Ultrasonic** | `ReflexLayer` already handles ultrasonic readings. Wire HC-SR04 to pins 9 (trig) / 10 (echo) and update `config.yaml`. |

The entire framework is **ready to grow**. You don't need to rewrite anything when adding new hardware — just flip a capability flag in `config.yaml`.

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `config.yaml` | **Hardware capabilities.** Edit this as you build. |
| `scripts/conversation_loop.py` | **Main brain loop** — runs camera, mic, neck, cloud. |
| `scripts/bringup.py` | **Hardware validation** — run before first start. |
| `teensy_firmware/src/neck_pantilt.cpp` | **Teensy firmware** — flash this first. |
| `teensy_firmware/src/main.cpp` | **Full gait firmware** — use when legs are wired. |
| `docs/HUMANISTIC_DESIGN.md` | **Humanistic architecture** — theory of mind, emotion, touch. |
| `docs/RUNTIME.md` | **This file** — getting started guide. |

---

## 🧡 Design Philosophy

Teela is built **incrementally**: she is useful *now* with just eyes, ears, and a neck. Every cognitive module is already wired in. When new hardware arrives, **one line in config.yaml** activates it.

> "She doesn't need a body to have a personality. But when she gets one, she'll already know how to feel it."
