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

        # Canvas PyQtGraph ad alto contrasto
        self.plot_widget = pg.PlotWidget(title="Mappa 2D della Stanza (Metri)")
        self.plot_widget.setBackground('#0d1117')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setAspectLocked(True)
        self.plot_widget.setRange(xRange=[-8.5, 8.5], yRange=[-8.5, 8.5])
        self.plot_widget.setLabel('bottom', "X", units='m')
        self.plot_widget.setLabel('left', "Y", units='m')
        layout.addWidget(self.plot_widget)

        # Cerchi metrici di riferimento
        self._draw_distance_circles()

        # NUOVA ESTETICA PUNTI OSTACOLO (Ciano Fosforescente / Neon Cyan)
        self.scatter_points = pg.ScatterPlotItem(
            size=5,
            pen=pg.mkPen('#00e5ff', width=0.8),
            brush=pg.mkBrush(0, 229, 255, 180), # Ciano neon semitrasparente
            symbol='o'
        )
        self.plot_widget.addItem(self.scatter_points)

        # Raggio Laser Istantaneo (Verde Smeraldo)
        self.laser_beam = self.plot_widget.plot(
            [0, 0], [0, 0],
            pen=pg.mkPen('#00ff88', width=1.5, style=Qt.PenStyle.DashLine)
        )
        
        # Punto di impatto istantaneo (Giallo/Bianco brillante per tracciare la testa del fascio)
        self.hit_marker = self.plot_widget.plot(
            [0], [0],
            symbol='o', symbolSize=8, symbolBrush='#ffffff', symbolPen=pg.mkPen('#00e5ff', width=2)
        )

        # Posizione Scanner Centrale (Croce / Triangolo arancione)
        self.plot_widget.plot(
            [0], [0],
            symbol='+', symbolSize=12, symbolBrush='#ff9800', symbolPen=pg.mkPen('#ff9800', width=2)
        )

    def _draw_distance_circles(self):
        theta = np.linspace(0, 2 * np.pi, 120)
        for r in [2.0, 4.0, 6.0, 8.0]:
            x = r * np.cos(theta)
            y = r * np.sin(theta)
            self.plot_widget.plot(x, y, pen=pg.mkPen('#21262d', width=1, style=Qt.PenStyle.DotLine))
            txt = pg.TextItem(f"{int(r)}m", color='#484f58', anchor=(0.5, 0.5))
            txt.setPos(0, r)
            self.plot_widget.addItem(txt)

    def update_points(self, points_xy):
        """Aggiorna la nuvola di punti con refresh forzato immediato."""
        if len(points_xy) > 0:
            arr = np.array(points_xy, dtype=np.float32)
            self.scatter_points.setData(pos=arr)
        else:
            # Forza uno svuotamento esplicito delle coordinate
            self.scatter_points.setData(pos=np.empty((0, 2)))
        
        # Forza il ridisegno immediato del canvas senza attendere eventi mouse
        self.plot_widget.getViewBox().updateAutoRange()
        self.plot_widget.update()

    def update_laser(self, angle_deg, distance_cm):
        if distance_cm < 5.0:
            self.laser_beam.setData([0, 0], [0, 0])
            self.hit_marker.setData([], [])
            return

        rad = np.deg2rad(angle_deg)
        r_m = distance_cm / 100.0
        x = r_m * np.sin(rad)
        y = r_m * np.cos(rad)

        self.laser_beam.setData([0, x], [0, y])
        self.hit_marker.setData([x], [y])

    def reset_view(self):
        self.plot_widget.setRange(xRange=[-8.5, 8.5], yRange=[-8.5, 8.5])