#include "BLEManager.h"
#include "Button.h"
#include "RotaryEncoder.h"
#include "IMUManager.h"
#include "StylusState.h"


BLEManager ble;

// Rotary encoder
// CLK = D0
// DT  = D1
// SW  = D2
RotaryEncoder encoder(D0, D1, D8);

// Mode button
// Button between D6 and GND
Button modeButton(
    D6
);

// IMU
IMUManager imuManager;

// Current stylus state
StylusState state;

// Timer for BLE sending
unsigned long lastSend = 0;

// Cached calibration status — refreshed once per second, not every send,
// to avoid 100Hz I2C reads for data that barely changes frame to frame
uint8_t cachedSysCal = 0;
uint8_t cachedGyroCal = 0;
uint8_t cachedAccelCal = 0;
uint8_t cachedMagCal = 0;


void setup()
{
    Serial.begin(115200);
    Serial.println("Starting Spatial Stylus...");

    ble.begin();
    encoder.begin();
    modeButton.begin();
    imuManager.begin();

    Serial.println("Waiting for Bluetooth connection...");
}


void loop()
{
    ble.loop();

    encoder.update();
    modeButton.update();
    imuManager.update();

    state.orientation = imuManager.getOrientation();

    // Calibration status — throttled to once per second
    static unsigned long lastCalPrint = 0;
    if(millis() - lastCalPrint > 1000)
    {
        lastCalPrint = millis();

        imuManager.getCalibrationStatus(cachedSysCal, cachedGyroCal, cachedAccelCal, cachedMagCal);

        // Serial.print("Calibration - Sys:");
        // Serial.print(cachedSysCal);
        // Serial.print(" Gyro:");
        // Serial.print(cachedGyroCal);
        // Serial.print(" Accel:");
        // Serial.print(cachedAccelCal);
        // Serial.print(" Mag:");
        // Serial.println(cachedMagCal);

        // uint8_t systemStatus, selfTest, systemError;
        // imuManager.getSystemStatus(systemStatus, selfTest, systemError);

        // Serial.print("System Status:");
        // Serial.print(systemStatus);
        // Serial.print("  Self Test:0x");
        // Serial.print(selfTest, HEX);
        // Serial.print("  System Error:0x");
        // Serial.println(systemError, HEX);
    }

    int rotation = encoder.getRotation();

    if (rotation != 0)
    {
        state.wheelDelta += rotation;
    }

    if (encoder.wasClicked())
    {
        state.wheelPressed = true;
    }

    if (modeButton.wasPressed())
    {
        state.modePressed = true;
    }

    state.batteryVoltage = 0;

    // BLE
    if (millis() - lastSend > 10)
    {
        lastSend = millis();

        char messageBuffer[96];

        snprintf(
            messageBuffer,
            sizeof(messageBuffer),
            "Q:%.6f,%.6f,%.6f,%.6f;W:%d;WC:%d;MB:%d;CAL:%d,%d,%d,%d",
            state.orientation.w,
            state.orientation.x,
            state.orientation.y,
            state.orientation.z,
            state.wheelDelta,
            state.wheelPressed,
            state.modePressed,
            cachedSysCal,
            cachedGyroCal,
            cachedAccelCal,
            cachedMagCal
        );

        ble.send(String(messageBuffer));

        state.wheelDelta = 0;
        state.wheelPressed = false;
        state.modePressed = false;
    }
}