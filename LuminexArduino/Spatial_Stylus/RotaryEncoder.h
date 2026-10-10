#ifndef ROTARYENCODER_H
#define ROTARYENCODER_H


class RotaryEncoder
{

private:

    int clkPin;
    int dtPin;
    int swPin;

    int lastCLK;

    bool lastSwitch;
    bool clickFlag;

    int rotationCount;

public:

    RotaryEncoder(
        int clk,
        int dt,
        int sw
    );

    void begin();

    void update();

    int getRotation();

    bool wasClicked();

};


#endif