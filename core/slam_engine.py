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

        # Background Map: distanza massima registrata per ogni grado (0-359)
        self.background_map = np.zeros(360, dtype=np.float32)

        # Buffer a 360° con risoluzione 0.5° (720 slot): (ang, dist_cm, x, y)
        self.NUM_SLOTS = 720
        self.polar_slots = [None] * self.NUM_SLOTS

    def add_angle_sample(self, angle_deg):
        now = time.perf_counter()
        self.angle_buffer.append((now, angle_deg))
        self.current_interpolated_angle = angle_deg

        if len(self.angle_buffer) > 100:
            self.angle_buffer.pop(0)

    def add_distance_sample(self, distance_cm):
        if not (5.0 <= distance_cm <= 800.0) or len(self.angle_buffer) < 2:
            return

        now = time.perf_counter()

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
        x = r_m * np.sin(rad)
        y = r_m * np.cos(rad)

        # 1. Aggiornamento Background Map
        deg_idx = int(interp_angle) % 360
        if self.background_map[deg_idx] == 0.0:
            self.background_map[deg_idx] = r_m
        else:
            self.background_map[deg_idx] = 0.95 * self.background_map[deg_idx] + 0.05 * max(self.background_map[deg_idx], r_m)

        # 2. Aggiornamento dello slot angolare corrispondente (si sovrascrive solo al nuovo giro)
        slot_idx = int((interp_angle % 360.0) / (360.0 / self.NUM_SLOTS)) % self.NUM_SLOTS
        self.polar_slots[slot_idx] = (interp_angle, distance_cm, x, y)

        # 3. Ray Clearing per spazio libero
        sin_a = np.sin(rad)
        cos_a = np.cos(rad)
        sample_steps = np.arange(0.12, max(0.12, r_m - 0.08), 0.05)
        for d in sample_steps:
            chk_x = d * sin_a
            chk_y = d * cos_a
            chk_key = (round(chk_x / self.spatial_res), round(chk_y / self.spatial_res))
            if chk_key in self.occupied_map:
                del self.occupied_map[chk_key]

        hit_key = (round(x / self.spatial_res), round(y / self.spatial_res))
        self.occupied_map[hit_key] = [x, y, interp_angle, distance_cm]

        self.xy_coords = [[pt[0], pt[1]] for pt in self.occupied_map.values()]
        self.points_history = [tuple(pt) for pt in self.occupied_map.values()]
        self.map_updated.emit()

    def get_sorted_scan(self):
        """Restituisce la scansione a 360° completa ordinata polarmente."""
        valid_samples = [s for s in self.polar_slots if s is not None]
        return sorted(valid_samples, key=lambda p: p[0])

    def clear(self):
        self.angle_buffer.clear()
        self.occupied_map.clear()
        self.xy_coords.clear()
        self.points_history.clear()
        self.polar_slots = [None] * self.NUM_SLOTS
        self.background_map.fill(0)
        self.map_updated.emit()