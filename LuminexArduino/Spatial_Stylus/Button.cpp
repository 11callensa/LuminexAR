#include "Button.h"
#include <Arduino.h>


Button::Button(int buttonPin)
{
    pin = buttonPin;

    lastReading = HIGH;
    buttonState = HIGH;

    pressedFlag = false;

    lastDebounceTime = 0;
    debounceDelay = 50;
}


void Button::begin()
{
    pinMode(pin, INPUT_PULLUP);

    buttonState = digitalRead(pin);
    lastReading = buttonState;
}


void Button::update()
{
    bool reading = digitalRead(pin);


    // Switch changed, restart debounce timer
    if (reading != lastReading)
    {
        lastDebounceTime = millis();
    }


    // Stable long enough?
    if ((millis() - lastDebounceTime) > debounceDelay)
    {
        if (reading != buttonState)
        {
            buttonState = reading;


            // Detect button press
            if (buttonState == LOW)
            {
                pressedFlag = true;
            }
        }
    }


    lastReading = reading;
}


bool Button::wasPressed()
{
    if (pressedFlag)
    {
        pressedFlag = false;
        return true;
    }

    return false;
}