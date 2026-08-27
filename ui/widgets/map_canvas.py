import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt

class MapCanvas(QWidget):
    def __init__(self, grid_size_m=16.0, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size_m
        self.target_items = []
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.plot_widget = pg.PlotWidget(title="Mappa 2D della Stanza (Metri)")
        self.plot_widget.setBackground('#0d1117')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setAspectLocked(True)
        self.plot_widget.setRange(xRange=[-8.5, 8.5], yRange=[-8.5, 8.5])
        self.plot_widget.setLabel('bottom', "X", units='m')
        self.plot_widget.setLabel('left', "Y", units='m')
        layout.addWidget(self.plot_widget)

        self._draw_distance_circles()

        # Nuvola Punti Ciano
        self.scatter_points = pg.ScatterPlotItem(
            size=4,
            pen=pg.mkPen('#00e5ff', width=0.5),
            brush=pg.mkBrush(0, 229, 255, 210),
            symbol='o'
        )
        self.plot_widget.addItem(self.scatter_points)

        # Fascio Laser e cursore d'impatto
        self.laser_beam = self.plot_widget.plot(
            [0, 0], [0, 0],
            pen=pg.mkPen('#00ff88', width=1.5, style=Qt.PenStyle.DashLine)
        )
        self.hit_marker = self.plot_widget.plot(
            [0], [0],
            symbol='o', symbolSize=7, symbolBrush='#ffffff', symbolPen=pg.mkPen('#00ff88', width=2)
        )

        # Centro Scanner
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
        if len(points_xy) > 0:
            arr = np.array(points_xy, dtype=np.float32)
            self.scatter_points.setData(pos=arr)
        else:
            self.scatter_points.setData(pos=np.empty((0, 2)))
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

    def draw_targets(self, targets):
        """Disegna anelli e marker sui target rilevati."""
        self.clear_targets()
        theta = np.linspace(0, 2 * np.pi, 30)

        for t in targets:
            cx = t.x + t.radius_m * np.cos(theta)
            cy = t.y + t.radius_m * np.sin(theta)
            
            # Anello Giallo tratteggiato
            ring = self.plot_widget.plot(cx, cy, pen=pg.mkPen('#ffd600', width=1.5, style=Qt.PenStyle.DashLine))
            # Crocetta centrale
            mark = self.plot_widget.plot([t.x], [t.y], symbol='x', symbolSize=8, symbolPen=pg.mkPen('#ffd600', width=2))
            # Etichetta ID + Distanza
            lbl = pg.TextItem(f"Target {t.id} ({t.distance_m:.2f}m)", color='#ffd600', anchor=(0.5, -0.5))
            lbl.setPos(t.x, t.y)
            self.plot_widget.addItem(lbl)

            self.target_items.extend([ring, mark, lbl])

    def clear_targets(self):
        for item in self.target_items:
            self.plot_widget.removeItem(item)
        self.target_items.clear()

    def reset_view(self):
        self.plot_widget.setRange(xRange=[-8.5, 8.5], yRange=[-8.5, 8.5])