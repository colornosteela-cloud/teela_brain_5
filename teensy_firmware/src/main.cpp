/**
 * Teela Teensy 4.1 Firmware
 * ===========================
 * Real-time gait control + servo output + IMU-based balance.
 * Runs a 1kHz control loop, never blocks.
 *
 * Receives via Serial:
 *   TARGET <x> <y> <yaw> <max_speed> <gait>

 *   HALT

 *   EMERGENCY_PARK

 *   PING

 *
 * Sends via Serial:
 *   STATUS <x> <y> <theta> <pitch> <roll> <fallen>

 *   ACK<cmd>

 *
 * Hardware:
 *   - Teensy 4.1 @ 600MHz
 *   - PCA9685 (I2C 0x40) for up to 16 servos (expandable)
 *   - MPU6050 or BNO055 for IMU (I2C 0x68 or 0x28)
 *   - Optional: HC-SR04 ultrasonic on GPIO
 */

#include <Arduino.h>
#include <Wire.h>
#include <Servo.h>
#include <math.h>

// ========== CONFIGURATION ==========
#define NUM_SERVOS           12      // 6 per leg (hip, thigh, knee, shin, ankle, toe)
#define SERVO_MIN_US         500
#define SERVO_MAX_US        2500
#define LOOP_FREQ_HZ       1000      // 1kHz main loop
#define IMU_ADDR          0x68      // MPU6050 default
#define PCA9685_ADDR      0x40

// Servo pin mapping (Teensy 4.1 has many PWM pins)
// Left leg: pins 2-7, Right leg: pins 8-13 (example)
const int SERVO_PINS[NUM_SERVOS] = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13};

// Gait parameters
const float GAIT_CYCLE_S   = 0.6f;    // seconds per gait cycle
const float STANCE_PHASE   = 0.5f;    // fraction of cycle on ground
const float SWING_HEIGHT_M = 0.04f;
const float BODY_HEIGHT_M  = 0.25f;

enum GaitState {
    GAIT_HALT,
    GAIT_WALK,
    GAIT_SHUFFLE,
    GAIT_EMERGENCY_PARK
};

// ========== GLOBALS ==========
Servo servos[NUM_SERVOS];
float servoAngles[NUM_SERVOS];     // current commanded angles (degrees)
float targetAngles[NUM_SERVOS];    // interpolated target

// Target pose from Jetson
volatile float targetX = 0.0f;
volatile float targetY = 0.0f;
volatile float targetYaw = 0.0f;
volatile float maxSpeed = 0.0f;
volatile GaitState gaitState = GAIT_HALT;

// Current estimated pose (from odometry / IMU fusion)
float currentX = 0.0f;
float currentY = 0.0f;
float currentYaw = 0.0f;

// IMU
float pitchDeg = 0.0f;
float rollDeg = 0.0f;
bool fallen = false;

// Timing
uint32_t lastStatusMs = 0;
uint32_t statusIntervalMs = 50;  // 20 Hz status report
float gaitPhase = 0.0f;          // 0-1 within gait cycle

// Serial buffer
char serialBuf[256];
uint8_t serialIdx = 0;

// ========== HELPERS ==========
void setServoAngle(int idx, float angleDeg) {
    angleDeg = constrain(angleDeg, 0.0f, 180.0f);
    int us = SERVO_MIN_US + (int)(angleDeg / 180.0f * (SERVO_MAX_US - SERVO_MIN_US));
    servos[idx].writeMicroseconds(us);
    servoAngles[idx] = angleDeg;
}

void centerAllServos() {
    for (int i = 0; i < NUM_SERVOS; i++) {
        setServoAngle(i, 90.0f);
    }
}

// Simple inverse kinematics for planar leg (2-link approximation)
// x_forward, z_height in meters
void legIK(float x, float z, float &hip, float &knee) {
    // L1 = thigh, L2 = shin (adjust to your actual link lengths)
    const float L1 = 0.10f;
    const float L2 = 0.10f;
    float d = sqrtf(x*x + z*z);
    d = constrain(d, 0.01f, L1+L2-0.01f);
    float cosKnee = (L1*L1 + L2*L2 - d*d) / (2.0f*L1*L2);
    float kneeRad = acosf(constrain(cosKnee, -1.0f, 1.0f));
    float alpha = atan2f(z, x);
    float beta = acosf((d*d + L1*L1 - L2*L2) / (2.0f*d*L1));
    float hipRad = alpha - beta;
    hip = degrees(hipRad);
    knee = degrees(kneeRad);
}

// ========== GAIT ENGINE ==========
void updateGait(float dt) {
    // Emergency park: slowly lower to ground, freeze
    if (gaitState == GAIT_EMERGENCY_PARK) {
        // Transition to standing/grounded pose
        float rate = 2.0f * dt; // slower transition
        for (int i = 0; i < NUM_SERVOS; i++) {
            float cmd = (i == 2 || i == 3 || i == 8 || i == 9) ? 100.0f : 90.0f;
            servoAngles[i] += (cmd - servoAngles[i]) * rate;
            setServoAngle(i, servoAngles[i]);
        }
        return;
    }

    if (gaitState == GAIT_HALT) {
        // Hold current pose
        return;
    }

    // Advance phase
    float effectiveSpeed = constrain(maxSpeed, 0.0f, 0.8f);
    if (effectiveSpeed < 0.05f) {
        return; // Too slow, stay in stance
    }
    float cycleRate = effectiveSpeed / GAIT_CYCLE_S; // simplified
    gaitPhase += cycleRate * dt;
    if (gaitPhase >= 1.0f) gaitPhase -= 1.0f;

    // Determine which feet are in swing vs stance
    bool leftSwing = (gaitPhase < STANCE_PHASE);
    bool rightSwing = (gaitPhase >= STANCE_PHASE);

    // Compute foot trajectories
    float leftX = 0.0f, leftZ = BODY_HEIGHT_M;
    float rightX = 0.0f, rightZ = BODY_HEIGHT_M;

    // Forward velocity integration into foot positions
    float forward = effectiveSpeed * GAIT_CYCLE_S * 0.25f;
    float halfSpan = forward * (leftSwing ? (gaitPhase / STANCE_PHASE) : ((gaitPhase - STANCE_PHASE) / (1.0f - STANCE_PHASE)));

    if (leftSwing) {
        leftX = halfSpan;
        // Parabolic lift
        float swingT = gaitPhase / STANCE_PHASE; // 0-1 during swing
        leftZ = BODY_HEIGHT_M - SWING_HEIGHT_M * 4.0f * swingT * (1.0f - swingT);
    } else {
        leftX = -forward + (2.0f * forward * (gaitPhase - STANCE_PHASE) / (1.0f - STANCE_PHASE));
    }

    if (rightSwing) {
        float swingT = (gaitPhase - STANCE_PHASE) / (1.0f - STANCE_PHASE);
        rightX = halfSpan;
        rightZ = BODY_HEIGHT_M - SWING_HEIGHT_M * 4.0f * swingT * (1.0f - swingT);
    } else {
        rightX = -forward + (2.0f * forward * gaitPhase / STANCE_PHASE);
    }

    // IK for each leg
    float lHip, lKnee, rHip, rKnee;
    legIK(leftX, leftZ, lHip, lKnee);
    legIK(rightX, rightZ, rHip, rKnee);

    // Map to servo indices (adjust to your wiring)
    // Left leg: 0=hip, 1=thigh, 2=knee, 3=shin, 4=ankle, 5=toe
    float lThigh = constrain(180.0f - (lHip + 90.0f), 0.0f, 180.0f);
    float lKneeServo = constrain(180.0f - lKnee, 0.0f, 180.0f);

    float rThigh = constrain(rHip + 90.0f, 0.0f, 180.0f);
    float rKneeServo = constrain(rKnee, 0.0f, 180.0f);

    // Smooth interpolation (slew rate limit)
    float rate = 5.0f * dt;
    float target[12] = {
        90.0f, lThigh, lKneeServo, 90.0f, 90.0f, 90.0f,   // left
        90.0f, rThigh, rKneeServo, 90.0f, 90.0f, 90.0f,   // right
    };
    for (int i = 0; i < NUM_SERVOS; i++) {
        servoAngles[i] += (target[i] - servoAngles[i]) * rate;
        setServoAngle(i, servoAngles[i]);
    }
}

// ========== IMU ==========
void readIMU() {
    // Stub: replace with actual MPU6050 or BNO055 read
    // For MPU6050: Wire.beginTransmission(IMU_ADDR); etc.
    // Simulate for now:
    pitchDeg += random(-1, 2) * 0.1f; // slight noise
    rollDeg += random(-1, 2) * 0.1f;
    if (fabsf(pitchDeg) > 30.0f || fabsf(rollDeg) > 30.0f) {
        fallen = true;
        gaitState = GAIT_EMERGENCY_PARK;
    } else {
        fallen = false;
    }
}

// ========== SERIAL PARSER ==========
void processSerialLine(const char *line) {
    if (strncmp(line, "TARGET ", 7) == 0) {
        float x, y, yaw, speed;
        char gaitName[32];
        if (sscanf(line + 7, "%f %f %f %f %31s", &x, &y, &yaw, &speed, gaitName) == 5) {
            targetX = x;
            targetY = y;
            targetYaw = yaw;
            maxSpeed = speed;
            if (strcmp(gaitName, "walk") == 0) gaitState = GAIT_WALK;
            else if (strcmp(gaitName, "shuffle") == 0) gaitState = GAIT_SHUFFLE;
            else if (strcmp(gaitName, "halt") == 0) gaitState = GAIT_HALT;
            Serial.print("ACKTARGET
");
        }
    } else if (strcmp(line, "HALT") == 0) {
        gaitState = GAIT_HALT;
        Serial.print("ACKHALT
");
    } else if (strcmp(line, "EMERGENCY_PARK") == 0) {
        gaitState = GAIT_EMERGENCY_PARK;
        Serial.print("ACKEP
");
    } else if (strcmp(line, "PING") == 0) {
        Serial.print("PONG
");
    }
}

void handleSerial() {
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            serialBuf[serialIdx] = '\0';
            if (serialIdx > 0) {
                processSerialLine(serialBuf);
            }
            serialIdx = 0;
        } else if (serialIdx < sizeof(serialBuf) - 1) {
            serialBuf[serialIdx++] = c;
        }
    }
}

// ========== SETUP & LOOP ==========
void setup() {
    Serial.begin(921600);
    while (!Serial && millis() < 2000) { ; } // wait for serial or 2s timeout

    Wire.begin();
    Wire.setClock(400000);

    for (int i = 0; i < NUM_SERVOS; i++) {
        servos[i].attach(SERVO_PINS[i], SERVO_MIN_US, SERVO_MAX_US);
    }

    centerAllServos();
    delay(500); // Let servos settle

    Serial.print("STATUS 0.00 0.00 0.00 0.00 0.00 false\n");
}

void loop() {
    static uint32_t lastMicros = 0;
    uint32_t now = micros();
    if (now - lastMicros < 1000) {
        // Still within 1ms window — idle
        // Process serial in idle time
        handleSerial();
        return;
    }
    float dt = (now - lastMicros) * 1e-6f;
    lastMicros = now;

    // 1. Read sensors
    readIMU();

    // 2. Run gait
    updateGait(dt);

    // 3. Send status periodically
    if (millis() - lastStatusMs >= statusIntervalMs) {
        lastStatusMs = millis();
        Serial.printf("STATUS %.4f %.4f %.4f %.2f %.2f %s\n",
            currentX, currentY, currentYaw,
            pitchDeg, rollDeg,
            fallen ? "true" : "false");
    }

    // 4. Loop timing enforced: if we finished early, handle serial until next tick
    while (micros() - lastMicros < 1000) {
        handleSerial();
    }
}
