#ifndef IMUMANAGER_H
#define IMUMANAGER_H

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>
#include <utility/imumaths.h>

#include "Quaternion.h"

class IMUManager
{
private:
    Adafruit_BNO055 bno = Adafruit_BNO055(55, 0x28);

    imu::Vector<3> accel;
    imu::Vector<3> gyro;

public:
    IMUManager();

    bool begin();

    void update();

    void getCalibrationStatus(uint8_t &sys, uint8_t &gyro, uint8_t &accel, uint8_t &mag);

    void getSystemStatus(uint8_t &systemStatus, uint8_t &selfTest, uint8_t &systemError);

    Quaternion getOrientation();

    float getAccelX();
    float getAccelY();
    float getAccelZ();

    float getGyroX();
    float getGyroY();
    float getGyroZ();
};

#endif