import time
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

class SLAMEngine(QObject):
    map_updated = pyqtSignal()

    def __init__(self, spatial_resolution_m=0.03, time_tolerance_ms=80.0):
        super().__init__()
        self.spatial_res = spatial_resolution_m
        self.tolerance_sec = time_tolerance_ms / 1000.0

        self.angle_buffer = []
        self.points_history = []
        self.occupied_map = {}
        self.xy_coords = []
        self.current_interpolated_angle = 0.0

        # Background Map: distanza stimata della parete statica (0-359 gradi)
        self.background_map = np.zeros(360, dtype=np.float32)

        # Buffer a 720 slot (0.5°): salva (timestamp, ang, dist_cm, x, y)
        self.NUM_SLOTS = 720
        self.polar_slots = [None] * self.NUM_SLOTS
        
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

        # Interpolazione temporale
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

        deg_idx = int(interp_angle) % 360
        bg_dist = self.background_map[deg_idx]

        # 1. Aggiornamento Background Map
        if bg_dist == 0.0:
            self.background_map[deg_idx] = r_m
            bg_dist = r_m
        elif r_m > bg_dist + 0.10:
            # Il raggio va oltre: il muro reale è più lontano
            self.background_map[deg_idx] = r_m
            bg_dist = r_m
        else:
            self.background_map[deg_idx] = 0.98 * bg_dist + 0.02 * r_m

        # 2. Aggiornamento Buffer Polare (per Target Detection a 360°)
        slot_idx = int((interp_angle % 360.0) / (360.0 / self.NUM_SLOTS)) % self.NUM_SLOTS
        self.polar_slots[slot_idx] = (now, interp_angle, distance_cm, x, y)

        # 3. Discriminazione: Parete Statica vs Target Dinamico
        is_foreground_target = (bg_dist > 0.3) and ((bg_dist - r_m) > 0.18)

        # 4. Ray-Clearing leggero
        max_clear = r_m - 0.08
        if max_clear > 0.15:
            for d in np.arange(0.12, max_clear, 0.08):
                cx = round((d * sin_a) / self.spatial_res)
                cy = round((d * cos_a) / self.spatial_res)
                self.occupied_map.pop((cx, cy), None)

        # 5. Registra nella mappa solo i muri/ostacoli stabili (non i target volatili)
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
        """Restituisce solo i punti dell'ultimo giro (~1.2s max), eliminando target spariti."""
        now = time.perf_counter()
        valid_samples = []
        for s in self.polar_slots:
            if s is not None:
                ts, ang, dist_cm, x, y = s
                # Se il punto ha più di 1.2 secondi, è scaduto e viene ignorato
                if (now - ts) <= 1.2:
                    valid_samples.append((ang, dist_cm, x, y))
        return sorted(valid_samples, key=lambda p: p[0])

    def clear(self):
        self.angle_buffer.clear()
        self.occupied_map.clear()
        self.xy_coords.clear()
        self.points_history.clear()
        self.polar_slots = [None] * self.NUM_SLOTS
        self.background_map.fill(0)
        self.map_updated.emit()