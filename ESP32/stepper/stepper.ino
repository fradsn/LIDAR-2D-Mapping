#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// --- PIN DRIVER ULN2003 ---
const int IN1 = 25;
const int IN2 = 27;
const int IN3 = 14;
const int IN4 = 26;

// Half-Step 28BYJ-48 (4096 passi per 1 giro alberino)
const int STEPS_PER_REV = 4096;
const int stepLookup[8] = {
  B01000,
  B01100,
  B00100,
  B00110,
  B00010,
  B00011,
  B00001,
  B01001
};

#define BASE_SERVICE_UUID      "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define BASE_AZIMUTH_CHAR_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define BASE_CONTROL_CHAR_UUID "beb5483f-36e1-4688-b7f5-ea07361b26a8"

BLECharacteristic *pAzimuthCharacteristic;
bool deviceConnected = false;
bool rotating = false;

long currentStep = 0;
int stepIndex = 0;
unsigned long lastStepTime = 0;
unsigned long stepIntervalMicros = 2200; // Default 3D (~9s per giro motore)

void disableCoils() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

class BaseServerCallbacks: public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) {
    deviceConnected = true;
    rotating = false;
    Serial.println("[BASE] Connesso. In attesa di comando START...");
  }
  void onDisconnect(BLEServer* pServer) {
    deviceConnected = false;
    rotating = false;
    disableCoils();
    Serial.println("[BASE] Disconnesso. Motore a riposo.");
    pServer->startAdvertising();
  }
};

class BaseControlCallbacks: public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pCharacteristic) {
    String rxValue = pCharacteristic->getValue();
    size_t len = rxValue.length();
    if (len > 0) {
      uint8_t cmd = rxValue[0];
      
      // CMD 0x01: START (accetta opzionalmente RPM: [0x01, rpm])
      if (cmd == 0x01) {
        if (len >= 2) {
          uint8_t rpm = rxValue[1];
          // Mappatura sicura RPM motore (4-16 RPM alberino)
          rpm = constrain(rpm, 4, 16);
          stepIntervalMicros = (60000000UL) / (4096UL * rpm);
        } else {
          stepIntervalMicros = 2200; // Valore predefinito per il 3D
        }
        rotating = true;
        Serial.printf("[BASE] START rotazione (Intervallo: %lu us)\n", stepIntervalMicros);
      }
      // CMD 0x00: STOP
      else if (cmd == 0x00) {
        rotating = false;
        disableCoils();
        Serial.println("[BASE] STOP rotazione");
      }
      // CMD 0x02: ZERO
      else if (cmd == 0x02) {
        currentStep = 0;
        Serial.println("[BASE] Zero calibrato");
      }
    }
  }
};

void setStepPins(int mask) {
  digitalWrite(IN1, (mask & B00001) ? HIGH : LOW);
  digitalWrite(IN2, (mask & B00010) ? HIGH : LOW);
  digitalWrite(IN3, (mask & B00100) ? HIGH : LOW);
  digitalWrite(IN4, (mask & B01000) ? HIGH : LOW);
}

void setup() {
  Serial.begin(115200);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  disableCoils();

  BLEDevice::init("ESP32-Stepper-Base");
  BLEServer *pServer = BLEDevice::createServer();
  pServer->setCallbacks(new BaseServerCallbacks());

  BLEService *pService = pServer->createService(BASE_SERVICE_UUID);

  pAzimuthCharacteristic = pService->createCharacteristic(
    BASE_AZIMUTH_CHAR_UUID,
    BLECharacteristic::PROPERTY_NOTIFY
  );
  pAzimuthCharacteristic->addDescriptor(new BLE2902());

  BLECharacteristic *pControlCharacteristic = pService->createCharacteristic(
    BASE_CONTROL_CHAR_UUID,
    BLECharacteristic::PROPERTY_WRITE
  );
  pControlCharacteristic->setCallbacks(new BaseControlCallbacks());

  pService->start();
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(BASE_SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->start();

  Serial.println("Base Stepper Universale pronta.");
}

void loop() {
  if (rotating && deviceConnected) {
    unsigned long nowMicros = micros();
    if (nowMicros - lastStepTime >= stepIntervalMicros) {
      lastStepTime = nowMicros;

      stepIndex = (stepIndex + 1) % 8;
      setStepPins(stepLookup[stepIndex]);
      currentStep = (currentStep + 1) % STEPS_PER_REV;

      if (currentStep % 16 == 0) {
        float thetaDeg = (float(currentStep) / STEPS_PER_REV) * 360.0f;
        uint16_t thetaEnc = (uint16_t)(thetaDeg * 10.0f);
        uint32_t nowMs = millis();

        uint8_t packet[6];
        packet[0] = (thetaEnc >> 8) & 0xFF;
        packet[1] = thetaEnc & 0xFF;
        packet[2] = (nowMs >> 24) & 0xFF;
        packet[3] = (nowMs >> 16) & 0xFF;
        packet[4] = (nowMs >> 8) & 0xFF;
        packet[5] = nowMs & 0xFF;

        pAzimuthCharacteristic->setValue(packet, 6);
        pAzimuthCharacteristic->notify();
      }
    }
  } else {
    delay(5);
  }
}