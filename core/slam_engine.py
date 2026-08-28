import time
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal
from core.target_detector import TargetDetector

class SLAMEngine(QObject):
    map_updated = pyqtSignal()
    targets_detected = pyqtSignal(list)

    def __init__(self, spatial_resolution_m=0.03, time_tolerance_ms=100.0):
        super().__init__()
        self.spatial_res = spatial_resolution_m
        self.tolerance_sec = time_tolerance_ms / 1000.0

        self.angle_buffer = []
        self.points_history = []
        self.occupied_map = {}      # (cx, cy) -> [x, y, angle, dist, hits]
        self.xy_coords = []
        self.current_interpolated_angle = 0.0

        # Background Map: 720 slot (0.5°)
        self.NUM_BG_SLOTS = 720
        self.background_map = np.zeros(self.NUM_BG_SLOTS, dtype=np.float32)

        # Buffer FIFO continuo per il Target Detector
        self.recent_scan_samples = []
        self.scan_retention_sec = 2.0
        
        self._last_gui_update = 0.0
        self._last_target_update = 0.0

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

        # 1. Interpolazione temporale dell'angolo
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

        # 2. Aggiornamento Background Map
        bg_idx = int((interp_angle % 360.0) / (360.0 / self.NUM_BG_SLOTS)) % self.NUM_BG_SLOTS
        current_bg = self.background_map[bg_idx]

        if current_bg == 0.0:
            self.background_map[bg_idx] = r_m
        elif r_m > current_bg:
            self.background_map[bg_idx] = 0.80 * current_bg + 0.20 * r_m
        else:
            self.background_map[bg_idx] = 0.998 * current_bg + 0.002 * r_m

        # 3. Classificazione Punto Foreground
        bg_dist = self.background_map[bg_idx]
        is_foreground = (bg_dist > 0.40) and ((bg_dist - r_m) > 0.20) and ((r_m / bg_dist) < 0.88)

        # 4. Buffer per Detector
        self.recent_scan_samples.append((now, interp_angle, distance_cm, x, y))
        cutoff = now - self.scan_retention_sec
        while self.recent_scan_samples and self.recent_scan_samples[0][0] < cutoff:
            self.recent_scan_samples.pop(0)

        # 5. Ray-Clearing sicuro lungo il raggio (senza erodere l'impatto)
        target_grid_x = int(round(x / self.spatial_res))
        target_grid_y = int(round(y / self.spatial_res))
        self._bresenham_ray_clear(target_grid_x, target_grid_y, max_clear_ratio=max(0.0, (r_m - 0.06) / r_m))

        # 6. Salva solo se è perimetro stabile
        if not is_foreground:
            hit_key = (target_grid_x, target_grid_y)
            if hit_key in self.occupied_map:
                self.occupied_map[hit_key][4] = min(10, self.occupied_map[hit_key][4] + 1)
                self.occupied_map[hit_key][0] = x
                self.occupied_map[hit_key][1] = y
                self.occupied_map[hit_key][2] = interp_angle
                self.occupied_map[hit_key][3] = distance_cm
            else:
                self.occupied_map[hit_key] = [x, y, interp_angle, distance_cm, 1]

        # 7. Pipeline Automatica di Target Detection (~15 Hz)
        if now - self._last_target_update > 0.066:
            self._process_targets_internal()
            self._last_target_update = now

        # 8. Refresh GUI Mappa (~30 FPS)
        if now - self._last_gui_update > 0.033:
            self.xy_coords = [[pt[0], pt[1]] for pt in self.occupied_map.values()]
            self.points_history = [tuple(pt[:4]) for pt in self.occupied_map.values()]
            self.map_updated.emit()
            self._last_gui_update = now

    def _process_targets_internal(self):
        scan_data = self.get_sorted_scan()
        if len(scan_data) < 8:
            self.targets_detected.emit([])
            return

        targets = TargetDetector.detect_targets_polar(
            scan_data,
            background_map=self.background_map,
            min_pts=4,
            max_pts=70,
            max_diameter=0.85
        )

        self.targets_detected.emit(targets)

    def _bresenham_ray_clear(self, x1, y1, max_clear_ratio=0.92):
        x0, y0 = 0, 0
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        total_steps = max(dx, dy)
        if total_steps == 0:
            return

        clear_steps = int(total_steps * max_clear_ratio)
        cur_step = 0
        cx, cy = x0, y0

        while cur_step < clear_steps:
            if cur_step > 3:
                if (cx, cy) in self.occupied_map:
                    self.occupied_map[(cx, cy)][4] -= 1
                    if self.occupied_map[(cx, cy)][4] <= 0:
                        del self.occupied_map[(cx, cy)]

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                cx += sx
            if e2 < dx:
                err += dx
                cy += sy

            cur_step += 1

    def get_sorted_scan(self):
        return sorted([(p[1], p[2], p[3], p[4]) for p in self.recent_scan_samples], key=lambda item: item[0])

    def clear(self):
        self.angle_buffer.clear()
        self.occupied_map.clear()
        self.xy_coords.clear()
        self.points_history.clear()
        self.recent_scan_samples.clear()
        self.background_map.fill(0)
        self.map_updated.emit()
        self.targets_detected.emit([])