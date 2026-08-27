import time
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

class SLAMEngine(QObject):
    map_updated = pyqtSignal()

    def __init__(self, spatial_resolution_m=0.03, time_tolerance_ms=80.0):
        super().__init__()
        self.spatial_res = spatial_resolution_m  # 3 cm
        self.tolerance_sec = time_tolerance_ms / 1000.0

        self.angle_buffer = []
        self.points_history = []
        
        # Dizionario spaziale: (grid_x, grid_y) -> [x, y, timestamp_ms, distance_cm]
        self.occupied_map = {}
        self.xy_coords = []
        self.current_interpolated_angle = 0.0

    def add_angle_sample(self, angle_deg):
        now = time.perf_counter()
        self.angle_buffer.append((now, angle_deg))
        self.current_interpolated_angle = angle_deg

        if len(self.angle_buffer) > 100:
            self.angle_buffer.pop(0)

    def add_distance_sample(self, distance_cm):
        if not (5.0 <= distance_cm <= 800.0) or len(self.angle_buffer) < 2:
            return

        t_lidar = time.perf_counter()

        # 1. Ricerca timestamp per interpolazione angolare precisa
        t0, a0 = None, None
        t1, a1 = None, None

        for i in range(len(self.angle_buffer) - 1, 0, -1):
            t_curr, a_curr = self.angle_buffer[i]
            t_prev, a_prev = self.angle_buffer[i - 1]
            if t_prev <= t_lidar <= t_curr:
                t0, a0 = t_prev, a_prev
                t1, a1 = t_curr, a_curr
                break

        if t0 is None:
            t0, a0 = self.angle_buffer[-2]
            t1, a1 = self.angle_buffer[-1]

        dt = abs(t1 - t0)
        if dt > self.tolerance_sec or dt == 0:
            interp_angle = a1
        else:
            da = a1 - a0
            if da > 180.0: da -= 360.0
            elif da < -180.0: da += 360.0
            factor = np.clip((t_lidar - t0) / dt, 0.0, 1.0)
            interp_angle = (a0 + factor * da) % 360.0

        self.current_interpolated_angle = interp_angle

        # 2. Coordinate Cartesiane del nuovo punto
        rad = np.deg2rad(interp_angle)
        r_m = distance_cm / 100.0
        x = r_m * np.sin(rad)
        y = r_m * np.cos(rad)

        # 3. Ray Clearing (Rimozione ostacoli rimossi lungo la linea di vista)
        # Campiona la traiettoria da 0 fino a (distanza - 10cm) per liberare lo spazio
        sin_a = np.sin(rad)
        cos_a = np.cos(rad)
        cleared_any = False
        
        # Passo di campionamento lungo il raggio (ogni 6 cm)
        sample_steps = np.arange(0.15, max(0.15, r_m - 0.10), 0.06)
        for d in sample_steps:
            chk_x = d * sin_a
            chk_y = d * cos_a
            chk_key = (round(chk_x / self.spatial_res), round(chk_y / self.spatial_res))
            if chk_key in self.occupied_map:
                del self.occupied_map[chk_key]
                cleared_any = True

        # 4. Registrazione del nuovo punto d'impatto sulla parete/ostacolo
        hit_key = (round(x / self.spatial_res), round(y / self.spatial_res))
        self.occupied_map[hit_key] = [x, y, interp_angle, distance_cm]

        # 5. Aggiornamento coordinate per il rendering
        self.xy_coords = [[pt[0], pt[1]] for pt in self.occupied_map.values()]
        self.points_history = [tuple(pt) for pt in self.occupied_map.values()]
        self.map_updated.emit()

    def clear(self):
        self.angle_buffer.clear()
        self.occupied_map.clear()
        self.xy_coords.clear()
        self.points_history.clear()
        self.map_updated.emit()