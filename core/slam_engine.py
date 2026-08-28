import time
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

class SLAMEngine(QObject):
    map_updated = pyqtSignal()

    def __init__(self, spatial_resolution_m=0.03, time_tolerance_ms=100.0):
        super().__init__()
        self.spatial_res = spatial_resolution_m
        self.tolerance_sec = time_tolerance_ms / 1000.0

        self.angle_buffer = []
        self.points_history = []
        self.occupied_map = {}
        self.xy_coords = []
        self.current_interpolated_angle = 0.0

        # Background Map ad alta risoluzione: 720 slot (0.5 gradi)
        self.NUM_BG_SLOTS = 720
        self.background_map = np.zeros(self.NUM_BG_SLOTS, dtype=np.float32)

        # Coda di campionamento polare continua per il Target Detector
        self.recent_scan_samples = []
        self.scan_retention_sec = 2.0  # Finestra temporale ottimale (2.0s)
        
        self._last_gui_update = 0.0

    def add_angle_sample(self, angle_deg):
        now = time.perf_counter()
        self.angle_buffer.append((now, angle_deg))
        self.current_interpolated_angle = angle_deg

        if len(self.angle_buffer) > 60:
            self.angle_buffer.pop(0)

    def add_distance_sample(self, distance_cm):
        if not (5.0 <= distance_cm <= 800.0) or len(self.angle_buffer) < 2:
            return

        now = time.perf_counter()

        # Interpolazione temporale precisa
        t0, a0 = None, None
        t1, a1 = None, None
        for i in range(len(self.angle_buffer) - 1, 0, -1):
            t_curr, a_curr = self.angle_buffer[i]
            t_prev, a_prev = self.angle_buffer[i - 1]
            if t_prev <= now <= t_curr:
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
            factor = np.clip((now - t0) / dt, 0.0, 1.0)
            interp_angle = (a0 + factor * da) % 360.0

        self.current_interpolated_angle = interp_angle

        rad = np.deg2rad(interp_angle)
        r_m = distance_cm / 100.0
        sin_a = float(np.sin(rad))
        cos_a = float(np.cos(rad))
        x = r_m * sin_a
        y = r_m * cos_a

        # Calcolo slot a 0.5°
        bg_idx = int((interp_angle % 360.0) / (360.0 / self.NUM_BG_SLOTS)) % self.NUM_BG_SLOTS
        bg_dist = self.background_map[bg_idx]

        # 1. Discriminazione: distacco netto di almeno 22 cm dalla parete nota
        is_foreground_target = (bg_dist > 0.35) and ((bg_dist - r_m) > 0.22)

        # 2. Aggiornamento protetto del Background Map
        if bg_dist == 0.0:
            self.background_map[bg_idx] = r_m
            bg_dist = r_m
        elif r_m > bg_dist + 0.08:
            # Parete reale più lontana
            self.background_map[bg_idx] = r_m
            bg_dist = r_m
        elif not is_foreground_target:
            # Assestamento solo su superfici perimetrali
            self.background_map[bg_idx] = 0.98 * bg_dist + 0.02 * r_m

        # 3. Accumulo cronologico per il Detector
        self.recent_scan_samples.append((now, interp_angle, distance_cm, x, y))

        cutoff_time = now - self.scan_retention_sec
        while self.recent_scan_samples and self.recent_scan_samples[0][0] < cutoff_time:
            self.recent_scan_samples.pop(0)

        # 4. Ray-Clearing libero
        max_clear = r_m - 0.08
        if max_clear > 0.15:
            for d in np.arange(0.12, max_clear, 0.08):
                cx = round((d * sin_a) / self.spatial_res)
                cy = round((d * cos_a) / self.spatial_res)
                self.occupied_map.pop((cx, cy), None)

        # 5. Salva sulla mappa ciano fissa solo le pareti stabili
        if not is_foreground_target:
            hit_key = (round(x / self.spatial_res), round(y / self.spatial_res))
            self.occupied_map[hit_key] = [x, y, interp_angle, distance_cm]

        # 6. Aggiornamento GUI a 30 FPS
        if now - self._last_gui_update > 0.033:
            self.xy_coords = [[pt[0], pt[1]] for pt in self.occupied_map.values()]
            self.points_history = [tuple(pt) for pt in self.occupied_map.values()]
            self.map_updated.emit()
            self._last_gui_update = now

    def get_sorted_scan(self):
        """Restituisce le letture recenti ordinate per angolo."""
        return sorted([(p[1], p[2], p[3], p[4]) for p in self.recent_scan_samples], key=lambda item: item[0])

    def clear(self):
        self.angle_buffer.clear()
        self.occupied_map.clear()
        self.xy_coords.clear()
        self.points_history.clear()
        self.recent_scan_samples.clear()
        self.background_map.fill(0)
        self.map_updated.emit()