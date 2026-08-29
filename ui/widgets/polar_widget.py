import math
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PyQt6.QtCore import Qt, QPointF

class PolarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self._angle_deg = 0.0
        self._distance_cm = 0.0

    def set_telemetry(self, angle_deg, distance_cm):
        self._angle_deg = angle_deg
        self._distance_cm = distance_cm
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        side = min(width, height)
        
        # Trasla l'origine al centro del widget
        painter.translate(width / 2, height / 2)
        radius = (side / 2) - 20

        # 1. Sfondo circolare scuro (Radar Style)
        painter.setBrush(QBrush(QColor(25, 28, 36)))
        painter.setPen(QPen(QColor(60, 70, 90), 2))
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        # 2. Cerchi concentrici interni
        painter.setPen(QPen(QColor(45, 55, 75), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), radius * 0.33, radius * 0.33)
        painter.drawEllipse(QPointF(0, 0), radius * 0.66, radius * 0.66)

        # 3. Linee degli assi (Croce 0°-180° e 90°-270°)
        painter.setPen(QPen(QColor(50, 60, 80), 1))
        painter.drawLine(0, int(-radius), 0, int(radius))
        painter.drawLine(int(-radius), 0, int(radius), 0)

        # 4. Tacche dei gradi e punti cardinali (Inversione orizzontale coerente con il LiDAR)
        painter.setPen(QPen(QColor(120, 140, 170), 1))
        font = QFont("Arial", 8)
        painter.setFont(font)
        
        for deg in range(0, 360, 30):
            rad = math.radians(deg)
            # Inversione asse X coerente
            x_outer = -radius * math.sin(rad)
            y_outer = -radius * math.cos(rad)
            x_inner = -(radius - 8) * math.sin(rad)
            y_inner = -(radius - 8) * math.cos(rad)
            painter.drawLine(int(x_inner), int(y_inner), int(x_outer), int(y_outer))

        # 5. Lancetta di orientamento istantaneo (punta nella direzione reale del laser)
        target_rad = math.radians(self._angle_deg)
        needle_x = -radius * 0.9 * math.sin(target_rad)
        needle_y = -radius * 0.9 * math.cos(target_rad)

        painter.setPen(QPen(QColor(255, 60, 80), 3))
        painter.drawLine(0, 0, int(needle_x), int(needle_y))

        # Centro indicatore
        painter.setBrush(QBrush(QColor(255, 60, 80)))
        painter.drawEllipse(QPointF(0, 0), 4, 4)

        # 6. Testo Telemetria
        painter.setPen(QColor(220, 230, 245))
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        text_str = f"{self._angle_deg:.1f}°\n{int(self._distance_cm)} cm"
        painter.drawText(-60, int(radius * 0.35), 120, 40, Qt.AlignmentFlag.AlignCenter, text_str)