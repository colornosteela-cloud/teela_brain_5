/**
 * Gait Engine Header
 * Pure math: trajectory planning, IK, balance compensation.
 * No Arduino deps. Can be unit-tested on host.
 */

#pragma once

#include <cstdint>

namespace teela {

struct GaitState {
    float phase;        // 0.0-1.0
    float speed;        // m/s
    float steer;        // rad/s
    float bodyHeight;   // meters
    uint8_t stanceLeg;  // 0=both, 1=left, 2=right
};

struct Pose3D {
    float x, y, z;
    float roll, pitch, yaw;
};

class GaitEngine {
public:
    void init(float bodyHeight, float legLength, float stepHeight);
    void update(float dt, const GaitState &cmd);
    void computeJointAngles(float outAngles[12]); // 6 left + 6 right
private:
    GaitState _state{};
    float _bodyH = 0.25f;
    float _legLen = 0.20f;
    float _stepH = 0.04f;
};

} // namespace teela
