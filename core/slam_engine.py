import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

class SLAMEngine(QObject):
    map_updated = pyqtSignal()
    
    # 1 giro completo (~720 campioni a 0.5° di risoluzione)
    # 1.5 giri = 720 * 1.5 = ~1080 -> impostiamo 1200 per sicurezza
    def __init__(self, max_points=3000, grid_size_m=16.0, cell_size_m=0.04):
        super().__init__()
        self.max_points = max_points
        self.points_history = []  # Per export completo (CSV/DXF)
        self.xy_coords = []       # Buffer per il render su mappa
        self.last_angle = 0.0

        self.grid_size = grid_size_m
        self.cell_size = cell_size_m
        self.dim = int(grid_size_m / cell_size_m)
        self.grid = np.zeros((self.dim, self.dim), dtype=np.float32)

    def update_angle(self, angle_deg):
        self.last_angle = angle_deg

    def add_reading(self, distance_cm):
        if not (5.0 <= distance_cm <= 800.0):
            return

        rad = np.deg2rad(self.last_angle)
        r_m = distance_cm / 100.0
        
        x = r_m * np.sin(rad)
        y = r_m * np.cos(rad)

        self.xy_coords.append([x, y])
        self.points_history.append((x, y, self.last_angle, distance_cm))

        # Mantiene i punti per esattamente 1 giro e mezzo
        if len(self.xy_coords) > self.max_points:
            self.xy_coords.pop(0)

        self.map_updated.emit()

    def clear(self):
        self.xy_coords.clear()
        self.points_history.clear()
        self.grid.fill(0)
        self.map_updated.emit()