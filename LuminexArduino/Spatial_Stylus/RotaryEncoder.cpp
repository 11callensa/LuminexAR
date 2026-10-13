#include "RotaryEncoder.h"
#include <Arduino.h>


RotaryEncoder::RotaryEncoder(
    int clk,
    int dt,
    int sw
)
{
    clkPin = clk;
    dtPin = dt;
    swPin = sw;

    lastCLK = HIGH;
    lastSwitch = HIGH;
    clickFlag = false;
    rotationCount = 0;
}


void RotaryEncoder::begin()
{
    pinMode(clkPin, INPUT_PULLUP);
    pinMode(dtPin, INPUT_PULLUP);

    // Button connected between D6 and GND
    pinMode(swPin, INPUT_PULLUP);

    lastCLK = digitalRead(clkPin);
    lastSwitch = digitalRead(swPin);
}


void RotaryEncoder::update()
{

    // Rotary encoder rotation
    int currentCLK = digitalRead(clkPin);

    if(
        currentCLK != lastCLK &&
        currentCLK == LOW
    )
    {
        if(
            digitalRead(dtPin) != currentCLK
        )
        {
            rotationCount++;
        }
        else
        {
            rotationCount--;
        }
    }

    lastCLK = currentCLK;


    // Button press detection
    bool currentSwitch = digitalRead(swPin);

    if(
        currentSwitch == LOW &&
        lastSwitch == HIGH
    )
    {
        clickFlag = true;
    }

    lastSwitch = currentSwitch;
}


int RotaryEncoder::getRotation()
{
    int value = rotationCount;

    rotationCount = 0;

    return value;
}


bool RotaryEncoder::wasClicked()
{
    if(clickFlag)
    {
        clickFlag = false;
        return true;
    }

    return false;
}