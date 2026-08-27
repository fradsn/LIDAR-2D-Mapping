import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

class SLAMEngine(QObject):
    map_updated = pyqtSignal()
    
    def __init__(self, max_points=2500, grid_size_m=16.0, cell_size_m=0.04):
        super().__init__()
        self.max_points = max_points
        self.points_history = []  # Dati estesi (x, y, angle, dist) per export CSV
        self.xy_coords = []       # Dati rapidi [x, y] per il rendering su canvas
        self.last_angle = 0.0

        # Retrocompatibilità se l'interfaccia si aspetta ancora l'oggetto grid
        self.grid_size = grid_size_m
        self.cell_size = cell_size_m
        self.dim = int(grid_size_m / cell_size_m)
        self.grid = np.zeros((self.dim, self.dim), dtype=np.float32)

    def update_angle(self, angle_deg):
        self.last_angle = angle_deg

    def add_reading(self, distance_cm):
        # Range operativo LiDAR TF-Luna (esclude errori o letture nulle)
        if not (5.0 <= distance_cm <= 800.0):
            return

        rad = np.deg2rad(self.last_angle)
        r_m = distance_cm / 100.0
        
        # Coordinate Cartesiane
        x = r_m * np.sin(rad)
        y = r_m * np.cos(rad)

        self.xy_coords.append([x, y])
        self.points_history.append((x, y, self.last_angle, distance_cm))

        # Mantieni la memoria entro i max_points per fluidità della UI
        if len(self.xy_coords) > self.max_points:
            self.xy_coords.pop(0)
            self.points_history.pop(0)

        self.map_updated.emit()

    def clear(self):
        self.xy_coords.clear()
        self.points_history.clear()
        self.grid.fill(0)
        self.map_updated.emit()