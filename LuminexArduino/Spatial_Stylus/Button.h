#ifndef BUTTON_H
#define BUTTON_H

class Button
{

private:

    int pin;

    bool lastReading;
    bool buttonState;

    bool pressedFlag;

    unsigned long lastDebounceTime;
    unsigned long debounceDelay;


public:

    Button(int buttonPin);

    void begin();

    void update();

    bool wasPressed();
};

#endif