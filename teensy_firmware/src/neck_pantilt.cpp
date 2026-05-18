/**
 * Teensy 4.1 Minimal Firmware — Neck Pan / Tilt Only
 * ======================================================
 * Receives from Jetson via Serial:
 *   NECK <pan_deg> <tilt_deg> <speed_dps> <hold_ms>
 *
 *   PING
 *
 * Sends to Jetson:
 *   ACK NECK <pan_deg> <tilt_deg>
 *   STATUS <pan_deg> <tilt_deg> <uptime_ms>
 *
 * Hardware:
 *   - Teensy 4.1 @ 600MHz
 *   - 2x MG996R servos (or equivalent):
 *         PAN  → pin 2
 *         TILT → pin 3
 *   - Optional: MPU6050 on I2C 0x68 for head IMU (future)
 */

#include <Arduino.h>
#include <Servo.h>

// ========== CONFIG ==========
#define PIN_PAN   2
#define PIN_TILT  3
#define SERVO_MIN_US   500
#define SERVO_MAX_US  2500
#define UPDATE_HZ     100       // 100 Hz servo update rate

// ========== GLOBALS ==========
Servo servoPan;
Servo servoTilt;

// Current commanded position (ramp toward target)
float currentPanDeg  = 0.0;
float currentTiltDeg = 5.0;
float targetPanDeg   = 0.0;
float targetTiltDeg  = 5.0;
float maxStepDeg     = 1.0;  // per tick at default speed

// Serial parsing
char serialBuf[80];
uint8_t serialIdx = 0;
unsigned long lastStatusMs = 0;

// ========== HELPERS ==========
void writeServo(Servo &s, float angleDeg) {
    angleDeg = constrain(angleDeg, -90.0f, 90.0f);
    // Map -90..+90 to servo pulse (microseconds)
    int us = SERVO_MIN_US + (int)((angleDeg + 90.0f) / 180.0f * (SERVO_MAX_US - SERVO_MIN_US));
    s.writeMicroseconds(us);
}

void parseCommand(const char* cmd) {
    if (strncmp(cmd, "NECK ", 5) == 0) {
        float pan, tilt, spd;
        int hold;
        int n = sscanf(cmd + 5, "%f %f %f %d", &pan, &tilt, &spd, &hold);
        if (n >= 2) {
            targetPanDeg = pan;
            targetTiltDeg = tilt;
            if (n >= 3 && spd > 0.1f) {
                // speed_dps → max degrees per tick
                maxStepDeg = spd / float(UPDATE_HZ);
            }
            Serial.printf("ACK NECK pan=%.1f tilt=%.1f\r\n", targetPanDeg, targetTiltDeg);
        }
    } else if (strcmp(cmd, "PING") == 0) {
        Serial.println("ACK PONG");
    } else if (strcmp(cmd, "STOP") == 0) {
        targetPanDeg = currentPanDeg;
        targetTiltDeg = currentTiltDeg;
        Serial.println("ACK STOP");
    }
}

void updateServos() {
    // Smooth interpolation toward target
    float diffP = targetPanDeg - currentPanDeg;
    float diffT = targetTiltDeg - currentTiltDeg;

    if (abs(diffP) <= maxStepDeg) {
        currentPanDeg = targetPanDeg;
    } else {
        currentPanDeg += (diffP > 0 ? maxStepDeg : -maxStepDeg);
    }
    if (abs(diffT) <= maxStepDeg) {
        currentTiltDeg = targetTiltDeg;
    } else {
        currentTiltDeg += (diffT > 0 ? maxStepDeg : -maxStepDeg);
    }

    writeServo(servoPan,  currentPanDeg);
    writeServo(servoTilt, currentTiltDeg);
}

void sendStatus() {
    Serial.printf("STATUS pan=%.1f tilt=%.1f uptime=%lu\r\n",
                  currentPanDeg, currentTiltDeg, millis());
}

// ========== SETUP ==========
void setup() {
    Serial.begin(921600);
    while (!Serial && millis() < 3000) { /* wait for USB Serial */ }

    servoPan.attach(PIN_PAN,  SERVO_MIN_US, SERVO_MAX_US);
    servoTilt.attach(PIN_TILT, SERVO_MIN_US, SERVO_MAX_US);

    // Initialize to neutral
    writeServo(servoPan,  currentPanDeg);
    writeServo(servoTilt, currentTiltDeg);

    serialIdx = 0;
    Serial.println("BOOT NECK_PANTILT v1.0");
    Serial.println("READY");
}

// ========== LOOP ==========
void loop() {
    // 1. Read serial commands
    while (Serial.available() > 0) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            serialBuf[serialIdx] = '\0';
            if (serialIdx > 0) {
                parseCommand(serialBuf);
            }
            serialIdx = 0;
        } else if (serialIdx < sizeof(serialBuf) - 1) {
            serialBuf[serialIdx++] = c;
        }
    }

    // 2. Update servo motion
    updateServos();

    // 3. Periodic status at 10 Hz
    if (millis() - lastStatusMs >= 100) {
        sendStatus();
        lastStatusMs = millis();
    }

    // 100 Hz → wait 10 ms
    delayMicroseconds(10000);  // 10 ms
}
