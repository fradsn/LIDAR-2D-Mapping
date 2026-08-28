#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// --- PIN DRIVER ULN2003 ---
const int IN1 = 25;
const int IN2 = 27;
const int IN3 = 14;
const int IN4 = 26;

// Half-Step 28BYJ-48 con riduzione 6:1 (4096 * 6 = 24576 passi per giro completo del piatto)
const long STEPS_PER_MOTOR_REV = 4096;
const long TOTAL_PLATE_STEPS   = 24576;

const int stepLookup[8] = {
  B01000, B01100, B00100, B00110,
  B00010, B00011, B00001, B01001
};

#define BASE_SERVICE_UUID      "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define BASE_AZIMUTH_CHAR_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"
#define BASE_CONTROL_CHAR_UUID "beb5483f-36e1-4688-b7f5-ea07361b26a8"

BLECharacteristic *pAzimuthCharacteristic;
bool deviceConnected = false;
bool rotating = false;

long currentAbsoluteStep = 0;
int stepIndex = 0;
int direction = 1; // 1: orario (CW), -1: antiorario (CCW)

long minTargetStep = 0;
long maxTargetStep = TOTAL_PLATE_STEPS;
bool isFullCircle = true;

unsigned long lastStepTime = 0;
unsigned long stepIntervalMicros = 2200;

void disableCoils() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

void setStepPins(int mask) {
  digitalWrite(IN1, (mask & B00001) ? HIGH : LOW);
  digitalWrite(IN2, (mask & B00010) ? HIGH : LOW);
  digitalWrite(IN3, (mask & B00100) ? HIGH : LOW);
  digitalWrite(IN4, (mask & B01000) ? HIGH : LOW);
}

class BaseServerCallbacks: public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) {
    deviceConnected = true;
    rotating = false;
    Serial.println("[BASE] Connesso. In attesa di comando...");
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
    uint8_t* data = pCharacteristic->getData();
    size_t len = pCharacteristic->getLength();

    if (len > 0) {
      uint8_t cmd = data[0];

      // CMD 0x01: START / CONFIGURA RANGE [0x01, rpm, minH, minL, maxH, maxL]
      if (cmd == 0x01) {
        if (len >= 2) {
          uint8_t rpm = constrain(data[1], 4, 16);
          stepIntervalMicros = (60000000UL) / (STEPS_PER_MOTOR_REV * rpm);
        } else {
          stepIntervalMicros = 2200;
        }

        if (len >= 6) {
          uint16_t minDegEnc = (data[2] << 8) | data[3];
          uint16_t maxDegEnc = (data[4] << 8) | data[5];

          minTargetStep = (long)(((float)minDegEnc / 3600.0f) * TOTAL_PLATE_STEPS);
          maxTargetStep = (long)(((float)maxDegEnc / 3600.0f) * TOTAL_PLATE_STEPS);

          isFullCircle = (minDegEnc == 0 && maxDegEnc >= 3600);
          direction = 1;
        } else {
          minTargetStep = 0;
          maxTargetStep = TOTAL_PLATE_STEPS;
          isFullCircle = true;
          direction = 1;
        }

        rotating = true;
        Serial.printf("[BASE] START: [%ld -> %ld], FullCircle: %d\n", minTargetStep, maxTargetStep, isFullCircle);
      }
      // CMD 0x00: STOP
      else if (cmd == 0x00) {
        rotating = false;
        disableCoils();
        Serial.println("[BASE] STOP");
      }
      // CMD 0x02: ZERO
      else if (cmd == 0x02) {
        currentAbsoluteStep = 0;
        Serial.println("[BASE] Zero calibrato");
      }
    }
  }
};

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
    BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR
  );
  pControlCharacteristic->setCallbacks(new BaseControlCallbacks());

  pService->start();
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(BASE_SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->start();

  Serial.println("ESP32-Stepper-Base Universale (360 + Sector) Pronto.");
}

void loop() {
  if (rotating && deviceConnected) {
    unsigned long nowMicros = micros();
    if (nowMicros - lastStepTime >= stepIntervalMicros) {
      lastStepTime = nowMicros;

      // Inversione per settore limitato
      if (!isFullCircle) {
        if (currentAbsoluteStep >= maxTargetStep && direction > 0) {
          direction = -1;
        } else if (currentAbsoluteStep <= minTargetStep && direction < 0) {
          direction = 1;
        }
      }

      stepIndex = (stepIndex + direction + 8) % 8;
      setStepPins(stepLookup[stepIndex]);

      if (isFullCircle) {
        currentAbsoluteStep = (currentAbsoluteStep + 1) % TOTAL_PLATE_STEPS;
      } else {
        currentAbsoluteStep += direction;
      }

      // Notifica ogni 16 micro-passi
      if (abs(currentAbsoluteStep) % 16 == 0) {
        float plateDeg = ((float)currentAbsoluteStep / (float)TOTAL_PLATE_STEPS) * 360.0f;
        if (plateDeg < 0.0f) plateDeg += 360.0f;

        uint16_t plateEnc = (uint16_t)(plateDeg * 10.0f);
        uint32_t nowMs = millis();

        uint8_t packet[6];
        packet[0] = (plateEnc >> 8) & 0xFF;
        packet[1] = plateEnc & 0xFF;
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