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
        self.occupied_map = {}      # (cx, cy) -> [x, y, angle, dist, confidence]
        self.xy_coords = []
        self.current_interpolated_angle = 0.0

        # Background Map ad alta risoluzione: 720 slot (0.5°)
        self.NUM_BG_SLOTS = 720
        self.background_map = np.zeros(self.NUM_BG_SLOTS, dtype=np.float32)

        # Coda FIFO continua per il Target Detector
        self.recent_scan_samples = []
        self.scan_retention_sec = 2.0
        
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

        # 2. Lookup Background Map con smoothing sui vicini (+- 1 slot)
        bg_idx = int((interp_angle % 360.0) / (360.0 / self.NUM_BG_SLOTS)) % self.NUM_BG_SLOTS
        
        # Prendi il valore stimato locale robusto (massimo tra vicini per evitare falsi muri ravvicinati)
        prev_idx = (bg_idx - 1) % self.NUM_BG_SLOTS
        next_idx = (bg_idx + 1) % self.NUM_BG_SLOTS
        local_bg = max(self.background_map[prev_idx], self.background_map[bg_idx], self.background_map[next_idx])

        # 3. Classificazione Target di Primo Piano
        # Richiede distacco netto di almeno 20 cm rispetto al muro stimato
        is_foreground_target = (local_bg > 0.35) and ((local_bg - r_m) > 0.20)

        # 4. Aggiornamento Dinamico del Background (solo perimetri reali)
        if self.background_map[bg_idx] == 0.0:
            self.background_map[bg_idx] = r_m
        elif r_m > self.background_map[bg_idx] + 0.06:
            # Il raggio penetra oltre: il muro reale è più lontano
            self.background_map[bg_idx] = r_m
        elif not is_foreground_target:
            # Assestamento continuo del perimetro stabile
            self.background_map[bg_idx] = 0.98 * self.background_map[bg_idx] + 0.02 * r_m

        # 5. Accumulo per Target Detector
        self.recent_scan_samples.append((now, interp_angle, distance_cm, x, y))
        cutoff = now - self.scan_retention_sec
        while self.recent_scan_samples and self.recent_scan_samples[0][0] < cutoff:
            self.recent_scan_samples.pop(0)

        # 6. Ray-Clearing Rigoroso (Algoritmo Bresenham / DDA lungo il raggio)
        # Svuota ogni singola cella attraversata dalla linea di vista fino a r_m - 6 cm
        target_grid_x = int(round(x / self.spatial_res))
        target_grid_y = int(round(y / self.spatial_res))
        
        self._bresenham_ray_clear(target_grid_x, target_grid_y, max_clear_ratio=max(0.0, (r_m - 0.06) / r_m))

        # 7. Aggiornamento Occupancy Grid con Confidenza
        if not is_foreground_target:
            hit_key = (target_grid_x, target_grid_y)
            if hit_key in self.occupied_map:
                # Incrementa la confidenza del muro (max 5)
                self.occupied_map[hit_key][4] = min(5, self.occupied_map[hit_key][4] + 1)
                self.occupied_map[hit_key][0] = x
                self.occupied_map[hit_key][1] = y
                self.occupied_map[hit_key][2] = interp_angle
                self.occupied_map[hit_key][3] = distance_cm
            else:
                # Nuovo punto: parte con confidenza 1
                self.occupied_map[hit_key] = [x, y, interp_angle, distance_cm, 1]

        # 8. Refresh GUI (mostra solo i punti con confidenza >= 2 per escludere glitch e transitori)
        if now - self._last_gui_update > 0.033:
            self.xy_coords = [[pt[0], pt[1]] for pt in self.occupied_map.values() if pt[4] >= 2]
            self.points_history = [tuple(pt[:4]) for pt in self.occupied_map.values() if pt[4] >= 2]
            self.map_updated.emit()
            self._last_gui_update = now

    def _bresenham_ray_clear(self, x1, y1, max_clear_ratio=0.90):
        """Svuota tutte le celle raster attraversate dal laser da (0,0) a (x1, y1)."""
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
            if cur_step > 3:  # Non cancellare la cella centrale dove poggia lo scanner
                if (cx, cy) in self.occupied_map:
                    # Se il laser attraversa una cella occupata, ne degrada la confidenza
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