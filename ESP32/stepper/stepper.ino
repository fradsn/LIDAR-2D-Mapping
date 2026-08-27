#include <Stepper.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

const int stepsPerMotorRev = 2048;
const long stepsForPlate360 = 12288; // Riduzione 6:1 (2048 * 6)

// --- Nuova configurazione Pin GPIO ESP32 ---
const int pinIN1 = 25; // IN1 -> D25
const int pinIN2 = 27; // IN2 -> D27
const int pinIN3 = 14; // IN3 -> D14
const int pinIN4 = 26; // IN4 -> D26

// Sequenza corretta per il 28BYJ-48 con Stepper.h: IN1, IN3, IN2, IN4
Stepper myStepper(stepsPerMotorRev, pinIN1, pinIN3, pinIN2, pinIN4);

#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define DATA_CHAR_UUID      "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define CMD_CHAR_UUID       "beb5483e-36e1-4688-b7f5-ea07361b26a9"

BLEServer* pServer = NULL;
BLECharacteristic* pDataChar = NULL;
BLECharacteristic* pCmdChar = NULL;
bool deviceConnected = false;

struct __attribute__((packed)) StepperPacket {
  uint32_t timestamp_ms;
  float angle_deg;
};

enum CommandType : uint8_t {
  CMD_SET_SPEED = 0x01,
  CMD_SET_ZERO  = 0x02
};

long currentStep = 0;
float lastReportedAngle = -1.0;
unsigned long lastBleSend = 0;
int currentSpeedRpm = 12;

class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer, esp_ble_gatts_cb_param_t *param) {
      deviceConnected = true;
      pServer->updateConnParams(param->connect.remote_bda, 0x0006, 0x000C, 0, 200);
    }
    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      BLEDevice::startAdvertising();
    }
};

class CommandCallbacks: public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
      uint8_t* data = pCharacteristic->getData();
      size_t len = pCharacteristic->getLength();

      if (len >= 2) {
        uint8_t cmd = data[0];
        uint8_t val = data[1];

        if (cmd == CMD_SET_SPEED) {
          currentSpeedRpm = constrain(val, 3, 16);
          myStepper.setSpeed(currentSpeedRpm);
          Serial.printf("Nuova velocita RPM: %d\n", currentSpeedRpm);
        } else if (cmd == CMD_SET_ZERO) {
          currentStep = 0;
          lastReportedAngle = -1.0;
          Serial.println("Zero Angolare Ricalibrato.");
        }
      }
    }
};

void setup() {
  Serial.begin(115200);
  myStepper.setSpeed(currentSpeedRpm);

  BLEDevice::init("ESP32_RotaryPlate");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);

  pDataChar = pService->createCharacteristic(
                DATA_CHAR_UUID,
                BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
              );
  pDataChar->addDescriptor(new BLE2902());

  pCmdChar = pService->createCharacteristic(
               CMD_CHAR_UUID,
               BLECharacteristic::PROPERTY_WRITE
             );
  pCmdChar->setCallbacks(new CommandCallbacks());

  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  BLEDevice::startAdvertising();

  Serial.println("ESP32 Stepper: Nuovi pin D25, D27, D14, D26 configurati con successo.");
}

void loop() {
  myStepper.step(1);
  currentStep = (currentStep + 1) % stepsForPlate360;

  float currentAngle = (float)currentStep * 360.0f / (float)stepsForPlate360;
  unsigned long now = millis();

  if (deviceConnected && (now - lastBleSend > 40)) {
    if (fabs(currentAngle - lastReportedAngle) >= 0.4f) {
      StepperPacket packet;
      packet.timestamp_ms = now;
      packet.angle_deg = currentAngle;

      pDataChar->setValue((uint8_t*)&packet, sizeof(packet));
      pDataChar->notify();

      lastReportedAngle = currentAngle;
      lastBleSend = now;
    }
  }
}