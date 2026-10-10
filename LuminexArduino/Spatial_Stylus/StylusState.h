#ifndef STYLUSSTATE_H
#define STYLUSSTATE_H

#include "Quaternion.h"

struct StylusState
{
    Quaternion orientation;

    int wheelDelta;

    bool wheelPressed;

    bool modePressed;

    float batteryVoltage;
};

#endif