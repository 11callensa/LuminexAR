#include "BLEManager.h"
#include <Arduino.h>

BLEManager::BLEManager()
{
    connected = false;
    characteristic = nullptr;
    needsAdvertisingRestart = false;
}

BLEManager::ServerCallbacks::ServerCallbacks(BLEManager* bleManager)
{
    parent = bleManager;
}


void BLEManager::ServerCallbacks::onConnect(NimBLEServer* server, NimBLEConnInfo& connInfo)
{
    parent->connected = true;

    Serial.print("BLE Connected at t=");
    Serial.println(millis());
}


void BLEManager::ServerCallbacks::onDisconnect(NimBLEServer* server, NimBLEConnInfo& connInfo, int reason)
{
    parent->connected = false;

    Serial.print("BLE Disconnected at t=");
    Serial.print(millis());
    Serial.print("  reason=");
    Serial.println(reason);

    Serial.print("Free heap at disconnect: ");
    Serial.println(ESP.getFreeHeap());

    // Don't restart advertising directly here — NimBLE can be unreliable
    // if this is called from within the disconnect callback's own context.
    // Defer it to the main loop instead.
    parent->needsAdvertisingRestart = true;
}


void BLEManager::loop()
{
    if(needsAdvertisingRestart)
    {
        needsAdvertisingRestart = false;

        NimBLEDevice::startAdvertising();

        Serial.println("Restarted advertising after disconnect");
    }
}


void BLEManager::begin()
{
    NimBLEDevice::init("SpatialStylus");

    NimBLEDevice::setMTU(185);

    NimBLEServer* server = NimBLEDevice::createServer();

    server->setCallbacks(
        new ServerCallbacks(this)
    );

    NimBLEService* service =
        server->createService(
            SERVICE_UUID
        );

    characteristic =
        service->createCharacteristic(
            CHARACTERISTIC_UUID,
            NIMBLE_PROPERTY::NOTIFY | NIMBLE_PROPERTY::READ
        );

    service->start();

    NimBLEAdvertising* advertising =
        NimBLEDevice::getAdvertising();

    advertising->start();

    Serial.println("BLE Advertising...");
}


void BLEManager::send(String message)
{
    if(!connected)
        return;

    characteristic->setValue(
        message.c_str()
    );

    characteristic->notify();
}


bool BLEManager::isConnected()
{
    return connected;
}