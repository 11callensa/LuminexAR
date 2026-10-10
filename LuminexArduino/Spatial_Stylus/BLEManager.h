#ifndef BLEMANAGER_H
#define BLEMANAGER_H

#include <NimBLEDevice.h>

#define SERVICE_UUID        "12345678-1234-1234-1234-1234567890ab"
#define CHARACTERISTIC_UUID "87654321-4321-4321-4321-ba0987654321"

class BLEManager
{
private:

    NimBLECharacteristic* characteristic;
    bool connected;
    volatile bool needsAdvertisingRestart;

    class ServerCallbacks : public NimBLEServerCallbacks
    {
    private:
        BLEManager* parent;

    public:
        ServerCallbacks(BLEManager* bleManager);

        void onConnect(NimBLEServer* server, NimBLEConnInfo& connInfo) override;

        void onDisconnect(NimBLEServer* server, NimBLEConnInfo& connInfo, int reason) override;
    };

public:

    BLEManager();

    void begin();

    void loop();

    void send(String message);

    bool isConnected();
};

#endif