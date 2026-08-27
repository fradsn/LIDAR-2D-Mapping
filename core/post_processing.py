import csv
import numpy as np

class PostProcessor:
    @staticmethod
    def export_csv(filepath, points):
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["X_m", "Y_m", "Angle_deg", "Distance_cm"])
            writer.writerows(points)

    @staticmethod
    def export_dxf(filepath, points):
        """Esporta la nuvola di punti in formato CAD DXF standard."""
        with open(filepath, 'w') as f:
            f.write("0\nSECTION\n2\nENTITIES\n")
            for p in points:
                f.write(f"0\nPOINT\n8\nLIDAR_SCAN\n10\n{p[0]:.4f}\n20\n{p[1]:.4f}\n30\n0.0\n")
            f.write("0\nENDSEC\n0\nEOF\n")