import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal

class MapCanvas(QWidget):
    cursor_position_changed = pyqtSignal(float, float, float, float)

    def __init__(self, grid_size_m=16.0, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size_m
        self.target_items = []
        
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Stato Strumento Misura
        self.measure_mode = False
        self.measure_start_pt = None
        self.start_marker_item = None
        self.measure_groups = []
        self.temp_measure_line = None
        self.temp_measure_label = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.plot_widget = pg.PlotWidget(title="Mappa 2D della Stanza (Metri)")
        self.plot_widget.setBackground('#0d1117')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setAspectLocked(True)
        self.plot_widget.setRange(xRange=[-8.5, 8.5], yRange=[-8.5, 8.5])
        self.plot_widget.setLabel('bottom', "X", units='m')
        self.plot_widget.setLabel('left', "Y", units='m')
        layout.addWidget(self.plot_widget)

        self.lbl_cursor_coords = QLabel("Cursore: X=0.00m, Y=0.00m | R=0.00m, θ=0.0°")
        self.lbl_cursor_coords.setStyleSheet("color: #8b949e; font-size: 11px; padding: 2px 6px; background-color: #0d1117;")
        layout.addWidget(self.lbl_cursor_coords)

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

        self.vb = self.plot_widget.getViewBox()
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_clicked)

    def _draw_distance_circles(self):
        theta = np.linspace(0, 2 * np.pi, 120)
        for r in [2.0, 4.0, 6.0, 8.0]:
            x = r * np.cos(theta)
            y = r * np.sin(theta)
            self.plot_widget.plot(x, y, pen=pg.mkPen('#21262d', width=1, style=Qt.PenStyle.DotLine))
            txt = pg.TextItem(f"{int(r)}m", color='#484f58', anchor=(0.5, 0.5))
            txt.setPos(0, r)
            self.plot_widget.addItem(txt)

    def draw_tracking_cone(self, min_deg: float, max_deg: float, center_deg: float):
        """Disegna il cono visivo dinamico con coordinate speculari X coerenti."""
        self.clear_tracking_cone()
        cone_len = 7.5

        rad_min = np.deg2rad(min_deg)
        rad_max = np.deg2rad(max_deg)

        x_min, y_min = -cone_len * np.sin(rad_min), cone_len * np.cos(rad_min)
        x_max, y_max = -cone_len * np.sin(rad_max), cone_len * np.cos(rad_max)

        l1 = self.plot_widget.plot([0, x_min], [0, y_min], pen=pg.mkPen('#ff6d00', width=1.5, style=Qt.PenStyle.DashLine))
        l2 = self.plot_widget.plot([0, x_max], [0, y_max], pen=pg.mkPen('#ff6d00', width=1.5, style=Qt.PenStyle.DashLine))

        l1.setZValue(8)
        l2.setZValue(8)
        
        if not hasattr(self, 'cone_items'):
            self.cone_items = []
        self.cone_items.extend([l1, l2])

    def clear_tracking_cone(self):
        if hasattr(self, 'cone_items'):
            for itm in self.cone_items:
                try:
                    self.plot_widget.removeItem(itm)
                except Exception:
                    pass
            self.cone_items.clear()

    def set_measure_mode(self, enabled: bool):
        self.measure_mode = enabled
        self._cancel_current_measurement()
        if enabled:
            self.setFocus()
            self.plot_widget.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.plot_widget.setCursor(Qt.CursorShape.ArrowCursor)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
            if self.measure_start_pt is not None:
                self._cancel_current_measurement()
            elif self.measure_groups:
                last_group = self.measure_groups.pop()
                for itm in last_group:
                    self.plot_widget.removeItem(itm)
            event.accept()
        else:
            super().keyPressEvent(event)

    def _on_mouse_moved(self, pos):
        if not self.plot_widget.sceneBoundingRect().contains(pos):
            return

        mouse_point = self.vb.mapSceneToView(pos)
        mx, my = mouse_point.x(), mouse_point.y()
        r_m = float(np.hypot(mx, my))
        # Angolo corretto rispetto al piano cartesiano speculare
        ang_deg = float(np.rad2deg(np.arctan2(-mx, my)) % 360.0)

        self.lbl_cursor_coords.setText(f"Cursore: X={mx:+.2f}m, Y={my:+.2f}m | R={r_m:.2f}m, θ={ang_deg:5.1f}°")
        self.cursor_position_changed.emit(mx, my, r_m, ang_deg)

        if self.measure_mode and self.measure_start_pt is not None:
            p1 = self.measure_start_pt
            dist = np.hypot(mx - p1[0], my - p1[1])

            if self.temp_measure_line is None:
                self.temp_measure_line = self.plot_widget.plot(
                    [p1[0], mx], [p1[1], my],
                    pen=pg.mkPen('#ff9100', width=2, style=Qt.PenStyle.DashLine)
                )
                self.temp_measure_label = pg.TextItem(f"{dist:.2f} m ({dist*100:.0f} cm)", color='#ff9100', anchor=(0.5, -0.5))
                self.plot_widget.addItem(self.temp_measure_label)
            else:
                self.temp_measure_line.setData([p1[0], mx], [p1[1], my])
                self.temp_measure_label.setText(f"{dist:.2f} m ({dist*100:.0f} cm)")
                self.temp_measure_label.setPos((p1[0] + mx) / 2, (p1[1] + my) / 2)

    def _on_mouse_clicked(self, event):
        if not self.measure_mode:
            return

        self.setFocus()
        pos = event.scenePos()
        if not self.plot_widget.sceneBoundingRect().contains(pos):
            return

        if event.button() == Qt.MouseButton.LeftButton:
            pt = self.vb.mapSceneToView(pos)
            mx, my = pt.x(), pt.y()

            if self.measure_start_pt is None:
                self.measure_start_pt = (mx, my)
                self.start_marker_item = self.plot_widget.plot(
                    [mx], [my],
                    symbol='o', symbolSize=8, symbolBrush='#ff9100', symbolPen=pg.mkPen('#ffffff', width=1.5)
                )
            else:
                p1 = self.measure_start_pt
                p2 = (mx, my)
                dist = np.hypot(p2[0] - p1[0], p2[1] - p1[1])

                line = self.plot_widget.plot([p1[0], p2[0]], [p1[1], p2[1]], pen=pg.mkPen('#ff9100', width=2.2))
                end_marker = self.plot_widget.plot([p2[0]], [p2[1]], symbol='o', symbolSize=8, symbolBrush='#ff9100', symbolPen=pg.mkPen('#ffffff', width=1.5))
                
                lbl = pg.TextItem(f"{dist:.2f} m ({dist*100:.0f} cm)", color='#ffffff', anchor=(0.5, -0.5))
                lbl.setPos((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
                self.plot_widget.addItem(lbl)

                self.measure_groups.append([self.start_marker_item, line, end_marker, lbl])

                self.start_marker_item = None
                self._remove_temp_measure()
                self.measure_start_pt = None

    def _remove_temp_measure(self):
        if self.temp_measure_line is not None:
            self.plot_widget.removeItem(self.temp_measure_line)
            self.temp_measure_line = None
        if self.temp_measure_label is not None:
            self.plot_widget.removeItem(self.temp_measure_label)
            self.temp_measure_label = None

    def _cancel_current_measurement(self):
        self._remove_temp_measure()
        if self.start_marker_item is not None:
            self.plot_widget.removeItem(self.start_marker_item)
            self.start_marker_item = None
        self.measure_start_pt = None

    def clear_measurements(self):
        self._cancel_current_measurement()
        for group in self.measure_groups:
            for itm in group:
                self.plot_widget.removeItem(itm)
        self.measure_groups.clear()

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
        x = -r_m * np.sin(rad)
        y =  r_m * np.cos(rad)

        self.laser_beam.setData([0, x], [0, y])
        self.hit_marker.setData([x], [y])

    def draw_targets(self, targets):
        self.clear_targets()
        theta = np.linspace(0, 2 * np.pi, 30)

        for t in targets:
            cx = t.x + t.radius_m * np.cos(theta)
            cy = t.y + t.radius_m * np.sin(theta)
            
            ring = self.plot_widget.plot(cx, cy, pen=pg.mkPen('#ffd600', width=1.5, style=Qt.PenStyle.DashLine))
            mark = self.plot_widget.plot([t.x], [t.y], symbol='x', symbolSize=8, symbolPen=pg.mkPen('#ffd600', width=2))
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