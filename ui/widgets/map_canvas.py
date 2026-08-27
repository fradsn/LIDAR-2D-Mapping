import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt

class MapCanvas(QWidget):
    def __init__(self, grid_size_m=16.0, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size_m
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Configurazione Canvas PyQtGraph
        self.plot_widget = pg.PlotWidget(title="Mappa 2D della Stanza (Metri)")
        self.plot_widget.setBackground('#111318')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setAspectLocked(True)
        self.plot_widget.setRange(xRange=[-8.5, 8.5], yRange=[-8.5, 8.5])
        self.plot_widget.setLabel('bottom', "X", units='m')
        self.plot_widget.setLabel('left', "Y", units='m')
        layout.addWidget(self.plot_widget)

        # Cerchi metrici di riferimento (2m, 4m, 6m, 8m)
        self._draw_distance_circles()

        # 1. PUNTI OSTACOLO (Scatter ad alta visibilità)
        self.scatter_points = pg.ScatterPlotItem(
            size=6,
            pen=pg.mkPen(None),
            brush=pg.mkBrush(255, 50, 75, 230), # Rosso brillante semitrasparente
            symbol='o'
        )
        self.plot_widget.addItem(self.scatter_points)

        # 2. Raggio Laser Istantaneo
        self.laser_beam = self.plot_widget.plot(
            [0, 0], [0, 0],
            pen=pg.mkPen('#00ff88', width=2, style=Qt.PenStyle.DashLine)
        )
        
        # 3. Punto di impatto istantaneo del laser (pallino ciano brillante)
        self.hit_marker = self.plot_widget.plot(
            [0], [0],
            symbol='o', symbolSize=8, symbolBrush='#00ffff', symbolPen='w'
        )

        # 4. Posizione Scanner Centrale
        self.plot_widget.plot(
            [0], [0],
            symbol='t', symbolSize=10, symbolBrush='#ffff00', symbolPen='w'
        )

    def _draw_distance_circles(self):
        theta = np.linspace(0, 2 * np.pi, 120)
        for r in [2.0, 4.0, 6.0, 8.0]:
            x = r * np.cos(theta)
            y = r * np.sin(theta)
            self.plot_widget.plot(x, y, pen=pg.mkPen('#2b3345', width=1, style=Qt.PenStyle.DotLine))
            txt = pg.TextItem(f"{int(r)}m", color='#607085', anchor=(0.5, 0.5))
            txt.setPos(0, r)
            self.plot_widget.addItem(txt)

    def update_points(self, points_xy):
        """Aggiorna la nuvola di punti (riceve lista di tuple o array Nx2)."""
        if len(points_xy) > 0:
            arr = np.array(points_xy)
            self.scatter_points.setData(pos=arr)
        else:
            self.scatter_points.clear()

    def update_laser(self, angle_deg, distance_cm):
        """Aggiorna il fascio laser e l'impatto istantaneo."""
        if distance_cm < 5.0:
            self.laser_beam.setData([0, 0], [0, 0])
            self.hit_marker.setData([], [])
            return

        rad = np.deg2rad(angle_deg)
        r_m = distance_cm / 100.0
        
        # Orientamento standard polare: X = r*sin, Y = r*cos (0° in alto, orario)
        x = r_m * np.sin(rad)
        y = r_m * np.cos(rad)

        self.laser_beam.setData([0, x], [0, y])
        self.hit_marker.setData([x], [y])

    def reset_view(self):
        self.plot_widget.setRange(xRange=[-8.5, 8.5], yRange=[-8.5, 8.5])