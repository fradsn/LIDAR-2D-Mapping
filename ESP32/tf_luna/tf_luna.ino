#include <ESP32Servo.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// --- PINNING HARDWARE (LATO DESTRO / VIN) ---
const int SERVO_PIN  = 13; // PWM Micro-Servo SG90
const int TF_LUNA_RX = 27; // ESP32 riceve (collegato a TX del TF-Luna)
const int TF_LUNA_TX = 26; // ESP32 trasmette (collegato a RX del TF-Luna)

// --- LIMITI CALIBRATI TILT GIMBAL ---
const int SERVO_BOTTOM = 165; // Orizzontale (0° Elevazione)
const int SERVO_TOP    = 70;  // Verticale (+95° Elevazione)

// --- BLE UUIDs (Allineati a config.py) ---
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
    Serial.println("[BLE] Client connesso al Payload LiDAR");
  }
  void onDisconnect(BLEServer* pServer) {
    deviceConnected = false;
    scanActive = false;
    Serial.println("[BLE] Client disconnesso. Riavvio advertising...");
    pServer->startAdvertising();
  }
};

class ControlCallbacks: public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pCharacteristic) {
    String rxValue = pCharacteristic->getValue();
    if (rxValue.length() > 0) {
      uint8_t cmd = rxValue[0];
      
      // CMD 0x01: Start Scan
      if (cmd == 0x01) {
        scanActive = true;
        currentServoAngle = SERVO_BOTTOM;
        tiltServo.write(currentServoAngle);
        Serial.println("[CMD] Avvio scansione 3D (Servo a 165°)");
      }
      // CMD 0x00: Stop Scan
      else if (cmd == 0x00) {
        scanActive = false;
        tiltServo.write(SERVO_BOTTOM);
        Serial.println("[CMD] Scansione interrotta");
      }
      // CMD 0x02: Imposta Angolo Tilt Diretto [0x02, target_angle]
      else if (cmd == 0x02 && rxValue.length() >= 2) {
        uint8_t target = rxValue[1];
        currentServoAngle = constrain(target, SERVO_TOP, SERVO_BOTTOM);
        tiltServo.write(currentServoAngle);
        Serial.printf("[CMD] Tilt impostato a: %d°\n", currentServoAngle);
      }
      // CMD 0x03: Incrementa Layer (Sale di tot gradi) [0x03, delta_deg]
      else if (cmd == 0x03 && rxValue.length() >= 2) {
        uint8_t step = rxValue[1];
        if (currentServoAngle >= SERVO_TOP + step) {
          currentServoAngle -= step;
        } else {
          currentServoAngle = SERVO_TOP;
        }
        tiltServo.write(currentServoAngle);
        Serial.printf("[CMD] Avanzamento strato! Nuovo angolo: %d°\n", currentServoAngle);
      }
    }
  }
};

// Parsing pacchetto TF-Luna (Standard 9-byte binary frame)
bool readTFLuna(uint16_t &dist, uint16_t &flux) {
  while (Serial2.available() >= 9) {
    if (Serial2.read() == 0x59 && Serial2.peek() == 0x59) {
      Serial2.read(); // Scarta secondo header 0x59
      uint8_t dL = Serial2.read();
      uint8_t dH = Serial2.read();
      uint8_t fL = Serial2.read();
      uint8_t fH = Serial2.read();
      for (int i = 0; i < 3; i++) Serial2.read(); // Scarta temp_L, temp_H, checksum

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

  // Inizializzazione BLE Server
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
    BLECharacteristic::PROPERTY_WRITE
  );
  pControlChar->setCallbacks(new ControlCallbacks());

  pService->start();
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->start();

  Serial.println("Payload Node (LiDAR + Tilt) inizializzato e in attesa BLE...");
}

void loop() {
  if (deviceConnected && scanActive) {
    uint16_t distance = 0, flux = 0;
    if (readTFLuna(distance, flux) && distance > 0 && distance < 1200) {
      uint32_t now = millis();
      
      // Payload (7 Byte): [Dist_H, Dist_L, ServoAngle, Time_B3, Time_B2, Time_B1, Time_B0]
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
  delay(15); // Campionamento a ~60 Hz
}