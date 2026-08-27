import time
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

class SLAMEngine(QObject):
    map_updated = pyqtSignal()

    def __init__(self, max_points=1200, time_tolerance_ms=80.0):
        super().__init__()
        self.max_points = max_points
        self.tolerance_sec = time_tolerance_ms / 1000.0  # Tolleranza max in secondi

        # Buffer temporale degli angoli: [(timestamp_sec, angle_deg), ...]
        self.angle_buffer = []
        self.points_history = []
        self.xy_coords = []
        self.current_interpolated_angle = 0.0

    def add_angle_sample(self, angle_deg):
        """Registra l'angolo associato al timestamp di ricezione ad alta precisione."""
        now = time.perf_counter()
        self.angle_buffer.append((now, angle_deg))
        self.current_interpolated_angle = angle_deg

        # Mantieni nel buffer solo gli ultimi 1.5 secondi di letture angolari
        if len(self.angle_buffer) > 100:
            self.angle_buffer.pop(0)

    def add_distance_sample(self, distance_cm):
        """Associa la distanza all'angolo esatto tramite interpolazione temporale."""
        if not (5.0 <= distance_cm <= 800.0) or len(self.angle_buffer) < 2:
            return

        t_lidar = time.perf_counter()

        # Cerca i due campioni di angolo a cavallo di t_lidar
        t0, a0 = None, None
        t1, a1 = None, None

        for i in range(len(self.angle_buffer) - 1, 0, -1):
            t_curr, a_curr = self.angle_buffer[i]
            t_prev, a_prev = self.angle_buffer[i - 1]

            if t_prev <= t_lidar <= t_curr:
                t0, a0 = t_prev, a_prev
                t1, a1 = t_curr, a_curr
                break

        # Se il punto cade all'estremità più recente del buffer
        if t0 is None:
            t0, a0 = self.angle_buffer[-2]
            t1, a1 = self.angle_buffer[-1]

        # Verifica che il gap temporale sia entro la tolleranza
        dt = abs(t1 - t0)
        if dt > self.tolerance_sec or dt == 0:
            # Campione troppo vecchio o gap radio anomalo: fallback all'ultimo angolo noto
            interp_angle = a1
        else:
            # Interpolazione lineare (gestisce anche il wrap-around 360°/0°)
            da = a1 - a0
            if da > 180.0:
                da -= 360.0
            elif da < -180.0:
                da += 360.0

            factor = (t_lidar - t0) / dt
            factor = np.clip(factor, 0.0, 1.0)
            interp_angle = (a0 + factor * da) % 360.0

        self.current_interpolated_angle = interp_angle

        # Conversione in coordinate cartesiane
        rad = np.deg2rad(interp_angle)
        r_m = distance_cm / 100.0
        x = r_m * np.sin(rad)
        y = r_m * np.cos(rad)

        self.xy_coords.append([x, y])
        self.points_history.append((x, y, interp_angle, distance_cm))

        if len(self.xy_coords) > self.max_points:
            self.xy_coords.pop(0)
            self.points_history.pop(0)

        self.map_updated.emit()

    def clear(self):
        self.angle_buffer.clear()
        self.xy_coords.clear()
        self.points_history.clear()
        self.map_updated.emit()