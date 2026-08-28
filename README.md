# 🛰️ LiDAR Studio 2D — Real-Time Mapping & Survey Suite

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6%20%7C%20PyQtGraph-green.svg)](https://riverbankcomputing.com/software/pyqt/)
[![Hardware](https://img.shields.io/badge/Hardware-Dual%20ESP32%20%7C%20TF--Luna%20%7C%20SG90-red.svg)](https://en.wikipedia.org/wiki/ESP32)
[![Protocol](https://img.shields.io/badge/BLE-Bidirectional%20Control-blueviolet.svg)](https://www.bluetooth.com/)
[![Export](https://img.shields.io/badge/Export-DXF%20%7C%20CSV-lightgrey.svg)](https://en.wikipedia.org/wiki/AutoCAD_DXF)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**LiDAR Studio 2D** is a high-performance desktop survey and real-time 360° 2D mapping platform. Built around a dual-ESP32 wireless architecture streaming over Bluetooth Low Energy (BLE), it features a responsive PyQt6/PyQtGraph dashboard implementing real-time SLAM spatial occupancy, dynamic ray-clearing (free-space carving), and Dietmayer Adaptive Breakpoint Detection (ABD) for intelligent obstacle isolation and CAD surveying.

> **Universal Hardware & Firmware Ecosystem:** Seamlessly shares the exact same physical hardware and ESP32 firmware with **3D LiDAR Scanner**. In 2D mode, the system automatically commands the pitch gimbal to lock into a level horizon (135°) and handles continuous planar SLAM mapping.

---

## 📸 Key Features

- **Decoupled Perimeter Mapping & Target Isolation:** Decouples persistent structural walls (cyan points) from dynamic foreground objects (yellow target bounds). Obstacles do not corrupt the floor plan and vanish instantaneously on the next sweep upon removal.
- **Dietmayer Adaptive Breakpoint Detection (ABD + PCA):** Real-time polar clustering with adaptive distance thresholds:
  $$D_{\text{thresh}} = r_{\text{min}} \cdot \frac{\sin(\Delta\theta)}{\sin(\gamma - \Delta\theta)} + C_0$$
  Includes Principal Component Analysis (PCA via `eigvalsh`) to discard flat wall segments and accurately isolate compact obstacles (people, furniture, columns).
- **Dynamic Ray-Clearing (Free-Space Carving):** Traces line-of-sight laser rays across a 3 cm spatial grid, instantly removing ghost artifacts and cleared obstacles.
- **Dedicated Scan Toggle & Safe State Transitions:** Independent **Start / Stop Scan** GUI control. Connecting via BLE keeps the stepper at rest until commanded, preventing motor stalling, high-frequency buzzing, or communication stalls.
- **Fast Cold Calibration (30–60s):** Automatically locks the perimeter geometry in 1–2 initial rotations (with a 6:1 mechanical reduction, 1 full 360° plate rotation takes 30s @ 12 RPM).
- **Interactive Ruler Tool (Click & Measure):** Point-to-point Euclidean canvas measurements with instant distance tags in meters/centimeters, real-time rubberband previews, and quick clear controls.
- **Bidirectional BLE Link:** Real-time speed adjustments (4–16 RPM), software-defined zero-point angular calibration, and non-blocking command dispatching (`PROPERTY_WRITE_NR`).
- **CAD & Metric Data Export:** 1:1 scale DXF vector export (compatible with AutoCAD, Fusion 360, Revit, QCAD) and tabular CSV scan logging.
- **Diagnostic Telemetry:** Polar sweep radar animation, live coordinates under cursor $(X, Y, R, \theta)$, and real-time dual-node RSSI signal monitoring (dBm).

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
<img width="3072" height="4080" alt="IMG_20260828_221050443" src="https://github.com/user-attachments/assets/e6530bf7-56e5-4684-b911-a08a870b3ee6" />
<img width="3072" height="4080" alt="IMG_20260828_220927330" src="https://github.com/user-attachments/assets/02a12e3a-6329-41d1-9425-f05d328275e8" />
<img width="4080" height="3072" alt="IMG_20260828_220937666" src="https://github.com/user-attachments/assets/8642cec4-73e0-41fd-b493-e9b802801f99" />
<img width="3072" height="4080" alt="IMG_20260828_220832221" src="https://github.com/user-attachments/assets/febf6096-863c-4f4e-a5eb-b507021b2971" />
<img width="3072" height="4080" alt="IMG_20260828_220851512" src="https://github.com/user-attachments/assets/197a79d0-bc4e-405e-8c93-a3f581aa6106" />

## 🏗️ System Architecture

```text
               ┌─────────────────────────────────────────────────────────┐
               │                      DESKTOP HOST                       │
               │                                                         │
               │   PyQt6 GUI   <───>   SLAMEngine (3cm Ray-Clear Grid)   │
               │       ▲                               ▲                 │
               │       │                               │                 │
               │   MapCanvas               TargetDetector (ABD + PCA)    │
               │       ▲                               ▲                 │
               │       └───────────────┬───────────────┘                 │
               │                       │                                 │
               │               BLEManager (Bleak)                        │
               └───────────────────────┬─────────────────────────────────┘
                                       │
                      Bluetooth Low Energy (GATT Notifications)
                                       │
               ┌───────────────────────┴───────────────────────┐
               │                                               │
               ▼                                               ▼
┌─────────────────────────────┐                 ┌─────────────────────────────┐
│      ESP32-Stepper-Base     │                 │      ESP32-LiDAR-Tilt       │
│    (28BYJ-48 Stepper 6:1)   │                 │  (TF-Luna ToF + SG90 Servo) │
├─────────────────────────────┤                 ├─────────────────────────────┤
│ • GPIO: 25, 27, 14, 26      │                 │ • UART2: GPIO 27 (RX), 26(TX)│
│ • Big-Endian Angle Stream   │                 │ • PWM: GPIO 13 (Servo locked│
│ • Remote RPM & Zero Calib   │                 │   at 135° Planar Horizon)   │
│ • Non-blocking Step Timing  │                 │ • Continuous UART Ring-Flush│
└─────────────────────────────┘                 └─────────────────────────────┘
