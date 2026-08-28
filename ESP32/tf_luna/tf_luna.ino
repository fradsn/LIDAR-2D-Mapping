#include <ESP32Servo.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// --- PINNING HARDWARE ---
const int SERVO_PIN  = 13; // PWM Micro-Servo SG90
const int TF_LUNA_RX = 27; // ESP32 riceve (collegato a TX del TF-Luna)
const int TF_LUNA_TX = 26; // ESP32 trasmette (collegato a RX del TF-Luna)

// --- LIMITI CALIBRATI TILT GIMBAL ---
const int SERVO_BOTTOM = 165; // Orizzontale (0° Elevazione)
const int SERVO_TOP    = 70;  // Verticale (+95° Elevazione)

#define SERVICE_UUID        "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
#define DATA_CHAR_UUID      "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
#define CONTROL_CHAR_UUID   "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

Servo tiltServo;
BLECharacteristic *pDataCharacteristic;
bool deviceConnected = false;
bool scanActive = false;
uint8_t currentServoAngle = SERVO_BOTTOM;

class ServerCallbacks: public BLEServerCallbacks {
  void onConnect(BLEServer* pServer) {
    deviceConnected = true;
    scanActive = false;
    Serial.println("[PAYLOAD] Client connesso");
  }
  void onDisconnect(BLEServer* pServer) {
    deviceConnected = false;
    scanActive = false;
    Serial.println("[PAYLOAD] Disconnesso, riavvio advertising...");
    pServer->startAdvertising();
  }
};

class ControlCallbacks: public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pCharacteristic) {
    uint8_t* data = pCharacteristic->getData();
    size_t len = pCharacteristic->getLength();

    if (len > 0) {
      uint8_t cmd = data[0];
      
      // CMD 0x01: Start Scan
      if (cmd == 0x01) {
        while (Serial2.available()) Serial2.read(); // Svuota buffer seriale
        currentServoAngle = SERVO_BOTTOM;
        tiltServo.write(currentServoAngle);
        scanActive = true;
        Serial.println("[PAYLOAD CMD] START scansione 3D");
      }
      // CMD 0x00: Stop Scan (NON scatta violentemente, evita brownout)
      else if (cmd == 0x00) {
        scanActive = false;
        Serial.println("[PAYLOAD CMD] STOP scansione (In Pausa)");
      }
      // CMD 0x02: Imposta Angolo Diretto [0x02, target_angle]
      else if (cmd == 0x02 && len >= 2) {
        uint8_t target = data[1];
        currentServoAngle = constrain(target, SERVO_TOP, SERVO_BOTTOM);
        tiltServo.write(currentServoAngle);
      }
      // CMD 0x03: Incrementa Layer [0x03, delta_deg]
      else if (cmd == 0x03 && len >= 2) {
        uint8_t step = data[1];
        if (currentServoAngle >= SERVO_TOP + step) {
          currentServoAngle -= step;
        } else {
          currentServoAngle = SERVO_TOP;
        }
        tiltServo.write(currentServoAngle);
        Serial.printf("[PAYLOAD CMD] Strato successivo: %d°\n", currentServoAngle);
      }
    }
  }
};

// Parsing continuo pacchetto TF-Luna
bool readTFLuna(uint16_t &dist, uint16_t &flux) {
  while (Serial2.available() >= 9) {
    if (Serial2.read() == 0x59 && Serial2.peek() == 0x59) {
      Serial2.read();
      uint8_t dL = Serial2.read();
      uint8_t dH = Serial2.read();
      uint8_t fL = Serial2.read();
      uint8_t fH = Serial2.read();
      for (int i = 0; i < 3; i++) Serial2.read();

      dist = dL | (dH << 8);
      flux = fL | (fH << 8);
      return true;
    }
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, TF_LUNA_RX, TF_LUNA_TX);

  ESP32PWM::allocateTimer(0);
  tiltServo.setPeriodHertz(50);
  tiltServo.attach(SERVO_PIN, 500, 2400);
  tiltServo.write(SERVO_BOTTOM);

  BLEDevice::init("ESP32-LiDAR-Tilt");
  BLEServer *pServer = BLEDevice::createServer();
  pServer->setCallbacks(new ServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);

  pDataCharacteristic = pService->createCharacteristic(
    DATA_CHAR_UUID,
    BLECharacteristic::PROPERTY_NOTIFY
  );
  pDataCharacteristic->addDescriptor(new BLE2902());

  BLECharacteristic *pControlChar = pService->createCharacteristic(
    CONTROL_CHAR_UUID,
    BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR
  );
  pControlChar->setCallbacks(new ControlCallbacks());

  pService->start();
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->start();

  Serial.println("[PAYLOAD] Pronto e operativo.");
}

void loop() {
  uint16_t distance = 0, flux = 0;
  
  if (readTFLuna(distance, flux)) {
    if (deviceConnected && scanActive && distance > 0 && distance < 1200) {
      uint32_t now = millis();
      
      uint8_t packet[7];
      packet[0] = (distance >> 8) & 0xFF;
      packet[1] = distance & 0xFF;
      packet[2] = currentServoAngle;
      packet[3] = (now >> 24) & 0xFF;
      packet[4] = (now >> 16) & 0xFF;
      packet[5] = (now >> 8) & 0xFF;
      packet[6] = now & 0xFF;

      pDataCharacteristic->setValue(packet, 7);
      pDataCharacteristic->notify();
    }
  }
  
  delay(10);
}