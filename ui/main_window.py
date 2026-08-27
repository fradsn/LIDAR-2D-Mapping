from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QFileDialog, QGroupBox, QSlider)
from PyQt6.QtCore import Qt

from core.ble_manager import BLEManager
from core.slam_engine import SLAMEngine
from core.post_processing import PostProcessor
from ui.widgets.map_canvas import MapCanvas
from ui.widgets.polar_widget import PolarWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LiDAR Studio 2D - Professional Desktop Suite")
        self.resize(1300, 780)

        self.slam = SLAMEngine(max_points=1200, time_tolerance_ms=80.0)
        self.ble = BLEManager()
        
        self.is_connected = False
        self.current_angle = 0.0
        self.current_dist = 0.0

        self._setup_ui()
        self._bind_signals()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # 1. Canvas Mappa 2D
        self.map_canvas = MapCanvas(grid_size_m=16.0)
        main_layout.addWidget(self.map_canvas, stretch=3)

        # 2. Pannello Laterale
        side_panel = QVBoxLayout()
        main_layout.addLayout(side_panel, stretch=1)

        # Bussola Radar
        box_polar = QGroupBox("Orientamento Istantaneo")
        layout_polar = QVBoxLayout()
        self.polar_widget = PolarWidget()
        layout_polar.addWidget(self.polar_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        box_polar.setLayout(layout_polar)
        side_panel.addWidget(box_polar)

        # Controllo Hardware Piatto
        box_hw = QGroupBox("Controllo Piatto Rotante")
        layout_hw = QVBoxLayout()
        
        self.lbl_speed = QLabel("Velocità: 12 RPM")
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(4, 16)
        self.slider_speed.setValue(12)
        
        self.btn_zero_calib = QPushButton("🎯 Imposta Zero Istantaneo")
        self.btn_zero_calib.setStyleSheet("background-color: #213042; font-weight: bold;")
        
        layout_hw.addWidget(self.lbl_speed)
        layout_hw.addWidget(self.slider_speed)
        layout_hw.addWidget(self.btn_zero_calib)
        box_hw.setLayout(layout_hw)
        side_panel.addWidget(box_hw)

        # Telemetria & RSSI
        box_telemetry = QGroupBox("Diagnostica & Telemetria")
        layout_tel = QVBoxLayout()
        self.lbl_status = QLabel("Stato: Disconnesso")
        self.lbl_angle = QLabel("Angolo: 0.0°")
        self.lbl_dist = QLabel("Distanza: 0 cm")
        self.lbl_rssi = QLabel("Segnale Radio: -- dBm")

        layout_tel.addWidget(self.lbl_status)
        layout_tel.addWidget(self.lbl_angle)
        layout_tel.addWidget(self.lbl_dist)
        layout_tel.addWidget(self.lbl_rssi)
        box_telemetry.setLayout(layout_tel)
        side_panel.addWidget(box_telemetry)

        # Controlli Mappa
        box_ctrl = QGroupBox("Controlli Mappatura")
        layout_ctrl = QVBoxLayout()
        
        self.btn_toggle_ble = QPushButton("Connetti Scanner BLE")
        self.btn_clear = QPushButton("Pulisci Mappa")
        self.btn_reset_view = QPushButton("Ripristina Vista Zoom")
        self.btn_export_csv = QPushButton("Esporta Coordinate (CSV)")
        self.btn_export_dxf = QPushButton("Esporta per CAD (.DXF)")
        
        layout_ctrl.addWidget(self.btn_toggle_ble)
        layout_ctrl.addWidget(self.btn_clear)
        layout_ctrl.addWidget(self.btn_reset_view)
        layout_ctrl.addWidget(self.btn_export_csv)
        layout_ctrl.addWidget(self.btn_export_dxf)
        box_ctrl.setLayout(layout_ctrl)
        side_panel.addWidget(box_ctrl)

        side_panel.addStretch()

    def _bind_signals(self):
        self.ble.angle_received.connect(self._on_angle_received)
        self.ble.distance_received.connect(self._on_distance_received)
        self.ble.status_changed.connect(self.lbl_status.setText)
        self.ble.connection_changed.connect(self._on_connection_changed)
        self.ble.rssi_updated.connect(lambda s, l: self.lbl_rssi.setText(f"Segnale: Motore {s} dBm | LiDAR {l} dBm"))

        self.slam.map_updated.connect(self._on_map_updated)

        self.btn_toggle_ble.clicked.connect(self._on_toggle_ble)
        self.btn_clear.clicked.connect(self._on_clear_clicked)
        self.btn_reset_view.clicked.connect(self.map_canvas.reset_view)
        self.btn_export_csv.clicked.connect(self._save_csv)
        self.btn_export_dxf.clicked.connect(self._save_dxf)

        self.slider_speed.valueChanged.connect(self._on_speed_changed)
        self.btn_zero_calib.clicked.connect(self._on_zero_calibrate)

    def _on_speed_changed(self, val):
        self.lbl_speed.setText(f"Velocità: {val} RPM")
        self.ble.send_speed_command(val)

    def _on_zero_calibrate(self):
        self.ble.send_zero_calibration()
        self.slam.clear()
        self.map_canvas.update_points([])

    def _on_toggle_ble(self):
        if not self.is_connected:
            self.btn_toggle_ble.setEnabled(False)
            self.ble.start()
        else:
            self.btn_toggle_ble.setEnabled(False)
            self.ble.stop()

    def _on_connection_changed(self, connected):
        self.is_connected = connected
        self.btn_toggle_ble.setEnabled(True)
        if connected:
            self.btn_toggle_ble.setText("Disconnetti BLE")
            self.btn_toggle_ble.setStyleSheet("background-color: #8b2635; color: white; font-weight: bold;")
        else:
            self.btn_toggle_ble.setText("Connetti Scanner BLE")
            self.btn_toggle_ble.setStyleSheet("")
            self.map_canvas.update_laser(self.current_angle, 0)
            self.lbl_rssi.setText("Segnale Radio: Disconnesso")

    def _on_angle_received(self, angle):
        self.current_angle = angle
        self.slam.add_angle_sample(angle)
        self.lbl_angle.setText(f"Angolo: {angle:5.1f}°")
        self.polar_widget.set_telemetry(self.slam.current_interpolated_angle, self.current_dist)

    def _on_distance_received(self, dist):
        self.current_dist = dist
        self.slam.add_distance_sample(dist)
        self.lbl_dist.setText(f"Distanza: {dist:5.1f} cm")
        self.polar_widget.set_telemetry(self.slam.current_interpolated_angle, self.current_dist)
        self.map_canvas.update_laser(self.slam.current_interpolated_angle, self.current_dist)

    def _on_map_updated(self):
        self.map_canvas.update_points(self.slam.xy_coords)

    def _on_clear_clicked(self):
        self.slam.clear()
        self.map_canvas.update_points([])

    def _save_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva CSV", "", "CSV Files (*.csv)")
        if path:
            PostProcessor.export_csv(path, self.slam.points_history)

    def _save_dxf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva DXF CAD", "", "DXF Files (*.dxf)")
        if path:
            PostProcessor.export_dxf(path, self.slam.points_history)

    def closeEvent(self, event):
        self.ble.stop()
        event.accept()