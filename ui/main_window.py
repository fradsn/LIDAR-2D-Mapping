from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QPushButton, QLabel, QFileDialog, QGroupBox, QSlider, QCheckBox, QScrollArea)
from PyQt6.QtCore import Qt, QTimer

from core.ble_manager import BLEManager
from core.slam_engine import SLAMEngine
from core.post_processing import PostProcessor
from core.target_detector import TargetDetector
from ui.widgets.map_canvas import MapCanvas
from ui.widgets.polar_widget import PolarWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LiDAR Studio 2D - Professional Desktop Suite")
        self.resize(1280, 820)

        self.slam = SLAMEngine(spatial_resolution_m=0.03, time_tolerance_ms=80.0)
        self.ble = BLEManager()
        
        self.is_connected = False
        self.current_angle = 0.0
        self.current_dist = 0.0

        self._setup_ui()
        self._bind_signals()

        self.detection_timer = QTimer(self)
        self.detection_timer.timeout.connect(self._run_target_detection)
        self.detection_timer.start(250)

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 1. Canvas Mappa 2D (Sinistra)
        self.map_canvas = MapCanvas(grid_size_m=16.0)
        main_layout.addWidget(self.map_canvas, stretch=3)

        # 2. Scroll Area per il Pannello Laterale (Destra)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 8px; background: #0d1117; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #30363d; border-radius: 4px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background: #8b949e; }
        """)
        main_layout.addWidget(scroll_area, stretch=1)

        side_widget = QWidget()
        side_panel = QVBoxLayout(side_widget)
        side_panel.setContentsMargins(4, 4, 8, 4)
        side_panel.setSpacing(6)
        scroll_area.setWidget(side_widget)

        # Bussola Radar
        box_polar = QGroupBox("Orientamento Istantaneo")
        layout_polar = QVBoxLayout()
        layout_polar.setContentsMargins(6, 6, 6, 6)
        self.polar_widget = PolarWidget()
        layout_polar.addWidget(self.polar_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        box_polar.setLayout(layout_polar)
        side_panel.addWidget(box_polar)

        # Controllo Hardware Piatto
        box_hw = QGroupBox("Controllo Piatto Rotante")
        layout_hw = QVBoxLayout()
        layout_hw.setContentsMargins(6, 6, 6, 6)
        layout_hw.setSpacing(4)
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

        # Sezione Target Detection
        box_targets = QGroupBox("Rilevamento Target")
        layout_targets = QVBoxLayout()
        layout_targets.setContentsMargins(6, 6, 6, 6)
        layout_targets.setSpacing(2)
        self.chk_enable_targets = QCheckBox("Abilita Target Detection")
        self.chk_enable_targets.setChecked(True)
        self.lbl_targets_info = QLabel("Target Rilevati: 0")
        self.lbl_targets_info.setStyleSheet("color: #ffd600; font-weight: bold;")
        layout_targets.addWidget(self.chk_enable_targets)
        layout_targets.addWidget(self.lbl_targets_info)
        box_targets.setLayout(layout_targets)
        side_panel.addWidget(box_targets)

        # Telemetria & RSSI
        box_telemetry = QGroupBox("Diagnostica & Telemetria")
        layout_tel = QVBoxLayout()
        layout_tel.setContentsMargins(6, 6, 6, 6)
        layout_tel.setSpacing(2)
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

        # Controlli Mappa e Strumenti CAD (Griglia compatta)
        box_ctrl = QGroupBox("Controlli & Strumenti Mappa")
        layout_ctrl = QGridLayout()
        layout_ctrl.setContentsMargins(6, 6, 6, 6)
        layout_ctrl.setSpacing(6)
        
        self.btn_measure = QPushButton("📏 Righello")
        self.btn_measure.setCheckable(True)
        self.btn_measure.setStyleSheet("QPushButton:checked { background-color: #e65100; color: white; font-weight: bold; }")

        self.btn_clear_measures = QPushButton("🗑️ Pulisci Quote")
        self.btn_toggle_ble = QPushButton("Connetti BLE")
        self.btn_clear = QPushButton("Pulisci Mappa")
        self.btn_reset_view = QPushButton("Reset Zoom")
        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_dxf = QPushButton("Export DXF")
        
        # Disposizione a 2 colonne per risparmiare spazio verticale
        layout_ctrl.addWidget(self.btn_toggle_ble, 0, 0, 1, 2)
        layout_ctrl.addWidget(self.btn_measure, 1, 0)
        layout_ctrl.addWidget(self.btn_clear_measures, 1, 1)
        layout_ctrl.addWidget(self.btn_clear, 2, 0)
        layout_ctrl.addWidget(self.btn_reset_view, 2, 1)
        layout_ctrl.addWidget(self.btn_export_csv, 3, 0)
        layout_ctrl.addWidget(self.btn_export_dxf, 3, 1)
        
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
        self.btn_clear_measures.clicked.connect(self.map_canvas.clear_measurements)
        self.btn_reset_view.clicked.connect(self.map_canvas.reset_view)
        self.btn_export_csv.clicked.connect(self._save_csv)
        self.btn_export_dxf.clicked.connect(self._save_dxf)

        self.slider_speed.valueChanged.connect(self._on_speed_changed)
        self.btn_zero_calib.clicked.connect(self._on_zero_calibrate)
        self.btn_measure.toggled.connect(self._on_measure_toggled)

    def _on_measure_toggled(self, active: bool):
        self.map_canvas.set_measure_mode(active)
        if active:
            self.lbl_status.setText("Righello attivo: Click fissa punti | Spazio annulla/elimina")

    def _run_target_detection(self):
        if not self.chk_enable_targets.isChecked():
            self.map_canvas.clear_targets()
            self.lbl_targets_info.setText("Target Rilevati: 0")
            return

        scan_data = self.slam.get_sorted_scan()
        if len(scan_data) < 15:
            return

        targets = TargetDetector.detect_targets_polar(
            scan_data, 
            background_map=self.slam.background_map,
            min_pts=4,
            max_pts=70,
            max_diameter=0.85
        )

        self.map_canvas.draw_targets(targets)
        self.lbl_targets_info.setText(f"Target Rilevati: {len(targets)}")

    def _on_speed_changed(self, val):
        self.lbl_speed.setText(f"Velocità: {val} RPM")
        self.ble.send_speed_command(val)

    def _on_zero_calibrate(self):
        self.ble.send_zero_calibration()
        self.slam.clear()
        self.map_canvas.update_points([])
        self.map_canvas.clear_targets()
        self.map_canvas.clear_measurements()
        self.map_canvas.update_laser(self.current_angle, 0)

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
            self.btn_toggle_ble.setText("Connetti BLE")
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
        self.map_canvas.clear_targets()
        self.map_canvas.clear_measurements()
        self.map_canvas.update_laser(self.current_angle, 0)
        self.lbl_targets_info.setText("Target Rilevati: 0")

    def _save_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva CSV", "", "CSV Files (*.csv)")
        if path:
            PostProcessor.export_csv(path, self.slam.points_history)

    def _save_dxf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva DXF CAD", "", "DXF Files (*.dxf)")
        if path:
            PostProcessor.export_dxf(path, self.slam.points_history)

    def closeEvent(self, event):
        self.detection_timer.stop()
        self.ble.stop()
        event.accept()