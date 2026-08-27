# 🛰️ LiDAR Studio 2D — Real-Time Mapping & Survey Suite

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6%20%7C%20PyQtGraph-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![Hardware](https://img.shields.io/badge/Hardware-ESP32%20%7C%20TF--Luna-red.svg)](https://en.wikipedia.org/wiki/ESP32)
[![Protocol](https://img.shields.io/badge/BLE-Bidirectional%20Control-blueviolet.svg)](https://www.bluetooth.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**LiDAR Studio 2D** is a complete desktop survey and real-time 360° 2D mapping suite. It integrates a dual-ESP32 wireless architecture via Bluetooth Low Energy (BLE) with a high-performance PyQt6/PyQtGraph dashboard capable of real-time 2D SLAM, dynamic ray-clearing, Dietmayer Adaptive Breakpoint Detection (ABD), and interactive CAD measurement tools.

---

## 📸 Key Features

- **Progressive Room Reconstruction:** Persistent spatial accumulation with 3 cm grid quantization.
- **Dynamic Ray-Clearing (Free-Space Carving):** Instant ghost-point removal along the line of sight when moving obstacles clear an area.
- **Classic Target Detection (Dietmayer ABD + PCA):** Identifies compact obstacles (people, chair/table legs, columns) and separates them from static walls via polar background subtraction.
- **Bidirectional BLE Control:** Remote RPM speed adjustment (4–16 RPM) and software-defined zero-point angle calibration.
- **Interactive Ruler Tool (Click & Measure):** Point-to-point canvas distance measurements with live distance overlays and quick undo/clear (`Spacebar`).
- **CAD & Data Export:** Real-world 1:1 scale vector export to `.DXF` (compatible with AutoCAD, Fusion 360, QCAD) and tabular logging to `.CSV`.
- **Complete Diagnostics:** Real-time animated polar radar sweep and radio link telemetry (RSSI in dBm) for both nodes.
---
<img width="1897" height="950" alt="Screenshot 2026-08-27 201756" src="https://github.com/user-attachments/assets/4158de00-0103-49ca-aa06-af1e7186d401" />

<img width="1897" height="930" alt="Screenshot 2026-08-27 201846" src="https://github.com/user-attachments/assets/20529e3e-4b7d-437a-8f8c-8f967c8945b4" />
<img width="1896" height="952" alt="Screenshot 2026-08-27 201947" src="https://github.com/user-attachments/assets/53d47448-5799-4526-8c5d-ffce248f571e" />

---
## 🏗️ System Architecture

```text
               +---------------------------------------------+
               |              DESKTOP HOST                   |
               |                                             |
               |  PyQt6 GUI  <--->  SLAMEngine (Ray Clear)   |
               |       ^                    ^                |
               |       |                    |                |
               |  MapCanvas         TargetDetector (ABD)     |
               |       ^                    ^                |
               |       +----------+---------+                |
               |                  |                          |
               |           BLEManager (Bleak)                |
               +------------------+--------------------------+
                                  |
                Bluetooth Low Energy (GATT Notifications)
                                  |
           +----------------------+----------------------+
           |                                             |
           v                                             v
+-----------------------+                     +-----------------------+
|    ESP32 Turntable    |                     |      ESP32 LiDAR      |
| (28BYJ-48 Motor 6:1)  |                     |   (TF-Luna Sensor)    |
|                       |                     |                       |
| - Angle Notifications |                     | - Dist Notifications  |
| - Speed/Zero Commands |                     | - 100 Hz Sample Rate  |
+-----------------------+                     +-----------------------+

