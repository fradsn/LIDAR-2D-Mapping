# 🛰️ LiDAR Studio 2D — Real-Time Mapping & Survey Suite

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6%20%7C%20PyQtGraph-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![Hardware](https://img.shields.io/badge/Hardware-ESP32%20%7C%20TF--Luna-red.svg)](https://en.wikipedia.org/wiki/ESP32)
[![Protocol](https://img.shields.io/badge/BLE-Bidirectional%20Control-blueviolet.svg)](https://www.bluetooth.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**LiDAR Studio 2D** is an high-performance desktop survey and real-time 360° 2D mapping platform. Built around a dual-ESP32 wireless architecture streaming over Bluetooth Low Energy (BLE), it features a real-time PyQt6/PyQtGraph dashboard implementing real-time SLAM spatial occupancy, dynamic ray-clearing (free-space carving), and Dietmayer Adaptive Breakpoint Detection (ABD) for intelligent, instantaneous obstacle isolation and CAD surveying.

---

## 📸 Key Features

- **Decoupled Perimeter Mapping & Target Isolation:** Decouples persistent structural walls (cyan points) from dynamic foreground objects (yellow target bounds). Obstacles do not corrupt the floor plan and vanish instantaneously on the next sweep upon removal.
- **Classic Target Detection (Dietmayer ABD + PCA):** Real-time polar clustering with adaptive distance thresholds:
  $$D_{\text{thresh}} = r_{\text{min}} \cdot \frac{\sin(\Delta\theta)}{\sin(\gamma - \Delta\theta)} + C_0$$
  Includes Principal Component Analysis (PCA via `eigvalsh`) to discard flat wall segments and accurately isolate compact obstacles (people, furniture, columns).
- **Dynamic Ray-Clearing (Free-Space Carving):** Traces line-of-sight laser rays across a 3 cm spatial grid, instantly removing ghost artifacts and cleared obstacles.
- **Fast Cold Calibration (30–60s):** Automatically locks the perimeter geometry in 1–2 initial rotations (with a 6:1 mechanical reduction, 1 full 360° plate rotation takes 30s @ 12 RPM).
- **Interactive Ruler Tool (Click & Measure):** Point-to-point Euclidean canvas measurements with instant distance tags in meters/centimeters, real-time rubberband previews, and quick undo/clear (`Spacebar` / `Esc`).
- **Bidirectional BLE Link:** Real-time speed adjustments (3–16 RPM) and software-defined zero-point angular calibration.
- **CAD & Metric Data Export:** 1:1 scale DXF vector export (compatible with AutoCAD, Fusion 360, Revit, QCAD) and tabular CSV scan logging.
- **Diagnostic Telemetry:** Polar sweep animation, live coordinates under cursor $(X, Y, R, \theta)$, and real-time dual-node RSSI signal monitoring (dBm).

---

## 🎬 Live Demonstrations

### 🎯 Real-Time Target Detection & Instant Clear
*Detection of obstacles interposing inside the room perimeter and immediate clearance upon removal:*

https://github.com/user-attachments/assets/2209494f-8b82-4bdb-b7f4-68df61fd2e87

### 🗺️ Full Floorplan Survey & Live Telemetry
<p align="center">
  <img width="950" alt="Planimetry Survey" src="https://github.com/user-attachments/assets/4158de00-0103-49ca-aa06-af1e7186d401" />
</p>

### 📐 Interactive CAD Distance Measurements
<p align="center">
  <img width="950" alt="CAD Measurements" src="https://github.com/user-attachments/assets/53d47448-5799-4526-8c5d-ffce248f571e" />
</p>

---

## 🏗️ System Architecture

```text
               +-------------------------------------------------+
               |                  DESKTOP HOST                   |
               |                                                 |
               |   PyQt6 GUI  <--->  SLAMEngine (3cm Ray-Clear)   |
               |       ^                           ^             |
               |       |                           |             |
               |   MapCanvas             TargetDetector (ABD)    |
               |       ^                           ^             |
               |       +-------------+-------------+             |
               |                     |                           |
               |             BLEManager (Bleak)                  |
               +---------------------+---------------------------+
                                     |
                    Bluetooth Low Energy (GATT Notifications)
                                     |
               +---------------------+---------------------+
               |                                           |
               v                                           v
+-----------------------------+             +-----------------------------+
|       ESP32 Turntable       |             |         ESP32 LiDAR         |
|    (28BYJ-48 Stepper 6:1)   |             |       (TF-Luna ToF)         |
|                             |             |                             |
| • GPIO: 25, 27, 14, 26      |             | • UART: GPIO 16 (RX), 17(TX)|
| • Angle Stream (GATT Notify)|             | • 100 Hz Distance Stream    |
| • Remote Speed & Zero Calib |             | • Low-Latency GATT Notify   |
+-----------------------------+             +-----------------------------+
