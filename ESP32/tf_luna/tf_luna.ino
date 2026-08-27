#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define LIDAR_SERVICE_UUID        "19b10000-e8f2-537e-4f6c-d104768a1214"
#define LIDAR_DATA_CHAR_UUID      "19b10001-e8f2-537e-4f6c-d104768a1214"

const int RX_PIN = 18;
const int TX_PIN = 19;

HardwareSerial lidarSerial(2);

BLEServer* pServer = NULL;
BLECharacteristic* pLidarChar = NULL;
bool deviceConnected = false;

struct __attribute__((packed)) LidarPacket {
  uint32_t timestamp_ms;
  uint16_t distance_cm;
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

void setup() {
  Serial.begin(115200);
  lidarSerial.begin(115200, SERIAL_8N1, RX_PIN, TX_PIN);

  BLEDevice::init("ESP32_LidarNode");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(LIDAR_SERVICE_UUID);
  pLidarChar = pService->createCharacteristic(
                 LIDAR_DATA_CHAR_UUID,
                 BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
               );
  pLidarChar->addDescriptor(new BLE2902());
  pService->start();

  BLEAdvertising *pAdv = BLEDevice::getAdvertising();
  pAdv->addServiceUUID(LIDAR_SERVICE_UUID);
  pAdv->setScanResponse(true);
  BLEDevice::startAdvertising();

  Serial.println("ESP32 LiDAR pronto.");
}

void loop() {
  if (lidarSerial.available() >= 9) {
    if (lidarSerial.read() == 0x59 && lidarSerial.read() == 0x59) {
      uint8_t distL = lidarSerial.read();
      uint8_t distH = lidarSerial.read();
      uint16_t distance_cm = distL + (distH << 8);

      for (int i = 0; i < 5; i++) lidarSerial.read();

      if (deviceConnected && distance_cm >= 2 && distance_cm <= 800) {
        LidarPacket packet;
        packet.timestamp_ms = millis();
        packet.distance_cm = distance_cm;

        pLidarChar->setValue((uint8_t*)&packet, sizeof(packet));
        pLidarChar->notify();
      }
    }
  }
}