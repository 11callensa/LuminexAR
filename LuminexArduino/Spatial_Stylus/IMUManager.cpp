#include "IMUManager.h"
#include <Arduino.h>

IMUManager::IMUManager()
{
}

bool IMUManager::begin()
{
    Wire.begin(D4, D5);

    Serial.println("Initializing BNO055...");

    if (!bno.begin())
    {
        Serial.println("BNO055 not found!");
        return false;
    }

    delay(1000);

    // Use the external 32.768 kHz crystal for better stability
    bno.setExtCrystalUse(true);

    Serial.println("BNO055 Found!");

    return true;
}

void IMUManager::update()
{
    accel = bno.getVector(Adafruit_BNO055::VECTOR_ACCELEROMETER);
    gyro  = bno.getVector(Adafruit_BNO055::VECTOR_GYROSCOPE);
}

void IMUManager::getSystemStatus(uint8_t &systemStatus, uint8_t &selfTest, uint8_t &systemError)
{
    bno.getSystemStatus(&systemStatus, &selfTest, &systemError);
}

Quaternion IMUManager::getOrientation()
{
    imu::Quaternion quat = bno.getQuat();

    Quaternion q;

    q.w = quat.w();
    q.x = quat.x();
    q.y = quat.y();
    q.z = quat.z();

    return q;
}

float IMUManager::getAccelX()
{
    return accel.x();
}

float IMUManager::getAccelY()
{
    return accel.y();
}

float IMUManager::getAccelZ()
{
    return accel.z();
}

float IMUManager::getGyroX()
{
    return gyro.x();
}

float IMUManager::getGyroY()
{
    return gyro.y();
}

float IMUManager::getGyroZ()
{
    return gyro.z();
}

void IMUManager::getCalibrationStatus(uint8_t &sys, uint8_t &gyro, uint8_t &accel, uint8_t &mag)
{
    bno.getCalibration(&sys, &gyro, &accel, &mag);
}