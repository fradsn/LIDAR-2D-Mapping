#include <Stepper.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// Configurazione Meccanica (72:12 = 6:1)
const int stepsPerMotorRev = 2048;
const long stepsForPlate360 = 12288; // 6 giri motore = 360° piatto

// Pin ESP32
const int pinIN1 = 19;
const int pinIN2 = 18;
const int pinIN3 = 5;
const int pinIN4 = 21;

Stepper myStepper(stepsPerMotorRev, pinIN1, pinIN3, pinIN2, pinIN4);

// UUID BLE
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

BLEServer* pServer = NULL;
BLECharacteristic* pCharacteristic = NULL;
bool deviceConnected = false;

// Struttura pacchetto binario (8 byte)
struct __attribute__((packed)) StepperPacket {
  uint32_t timestamp_ms;
  float angle_deg;
};

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

long currentStep = 0;
float lastReportedAngle = -1.0;
unsigned long lastBleSend = 0;

void setup() {
  Serial.begin(115200);
  myStepper.setSpeed(12); // Velocità costante

  BLEDevice::init("ESP32_RotaryPlate");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
                      CHARACTERISTIC_UUID,
                      BLECharacteristic::PROPERTY_READ   |
                      BLECharacteristic::PROPERTY_NOTIFY
                    );
  pCharacteristic->addDescriptor(new BLE2902());
  pService->start();

  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  BLEDevice::startAdvertising();

  Serial.println("ESP32 Stepper: Rotazione continua 360° attiva.");
}

void loop() {
  // 1. Avanza sempre di 1 passo in senso orario
  myStepper.step(1);
  currentStep = (currentStep + 1) % stepsForPlate360;

  // 2. Calcolo angolo piatto da 0.0° a 360.0°
  float currentAngle = (float)currentStep * 360.0f / (float)stepsForPlate360;

  // 3. Invio notifica BLE se variato di almeno 0.4° o ogni 40ms
  unsigned long now = millis();
  if (deviceConnected && (now - lastBleSend > 40)) {
    if (fabs(currentAngle - lastReportedAngle) >= 0.4f) {
      StepperPacket packet;
      packet.timestamp_ms = now;
      packet.angle_deg = currentAngle;

      pCharacteristic->setValue((uint8_t*)&packet, sizeof(packet));
      pCharacteristic->notify();

      lastReportedAngle = currentAngle;
      lastBleSend = now;
    }
  }
}