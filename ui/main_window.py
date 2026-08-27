from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, QGroupBox)
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
        self.resize(1280, 780)

        # Inizializzazione Core (1200 campioni = 1.5 giri / 540°)
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

        # 1. Canvas Mappa 2D (Sinistra)
        self.map_canvas = MapCanvas(grid_size_m=16.0)
        main_layout.addWidget(self.map_canvas, stretch=3)

        # 2. Pannello Laterale (Destra)
        side_panel = QVBoxLayout()
        main_layout.addLayout(side_panel, stretch=1)

        # Radar Polar Widget
        box_polar = QGroupBox("Orientamento & Bussola")
        layout_polar = QVBoxLayout()
        self.polar_widget = PolarWidget()
        layout_polar.addWidget(self.polar_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        box_polar.setLayout(layout_polar)
        side_panel.addWidget(box_polar)

        # Telemetria & Stato
        box_telemetry = QGroupBox("Stato Sistema")
        layout_tel = QVBoxLayout()
        self.lbl_status = QLabel("Stato: Disconnesso")
        self.lbl_angle = QLabel("Angolo: 0.0°")
        self.lbl_dist = QLabel("Distanza: 0 cm")
        layout_tel.addWidget(self.lbl_status)
        layout_tel.addWidget(self.lbl_angle)
        layout_tel.addWidget(self.lbl_dist)
        box_telemetry.setLayout(layout_tel)
        side_panel.addWidget(box_telemetry)

        # Controlli Operativi
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
        # Segnali BLE
        self.ble.angle_received.connect(self._on_angle_received)
        self.ble.distance_received.connect(self._on_distance_received)
        self.ble.status_changed.connect(self.lbl_status.setText)
        self.ble.connection_changed.connect(self._on_connection_changed)

        # Segnali SLAM Engine
        self.slam.map_updated.connect(self._on_map_updated)

        # Interazioni UI
        self.btn_toggle_ble.clicked.connect(self._on_toggle_ble)
        self.btn_clear.clicked.connect(self._on_clear_clicked)
        self.btn_reset_view.clicked.connect(self.map_canvas.reset_view)
        self.btn_export_csv.clicked.connect(self._save_csv)
        self.btn_export_dxf.clicked.connect(self._save_dxf)

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
        """Assicura la disconnessione quando l'utente chiude la finestra."""
        self.ble.stop()
        event.accept()