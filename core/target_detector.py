import numpy as np

class DetectedTarget:
    def __init__(self, target_id, points):
        self.id = target_id
        self.points = np.array(points, dtype=np.float32)
        
        # Centroide (X, Y)
        self.centroid = np.mean(self.points, axis=0)
        self.x = float(self.centroid[0])
        self.y = float(self.centroid[1])
        
        self.distance_m = float(np.hypot(self.x, self.y))
        self.azimuth_deg = float(np.rad2deg(np.arctan2(self.x, self.y)) % 360.0)
        self.radius_m = max(float(np.max(np.linalg.norm(self.points - self.centroid, axis=1))), 0.08)

class TargetDetector:
    @staticmethod
    def detect_targets_polar(polar_scan, background_map=None, min_pts=4, max_pts=80, max_diameter=0.85):
        """
        Algoritmo di Segmentazione Adattiva Dietmayer (ABD) su scansione polare ordinata.
        polar_scan: lista di tuple (angolo_deg, dist_cm, x_m, y_m) ordinate per angolo.
        background_map: array opzionale di 360 float contenente la distanza del muro per ogni grado.
        """
        if len(polar_scan) < min_pts:
            return []

        # 1. Background Subtraction (se disponibile)
        foreground_pts = []
        for ang, dist_cm, x, y in polar_scan:
            r_m = dist_cm / 100.0
            if background_map is not None:
                deg_idx = int(ang) % 360
                bg_dist = background_map[deg_idx]
                # Se il punto è più vicino del muro di almeno 18 cm, è un oggetto in primo piano
                if bg_dist > 0.3 and (bg_dist - r_m) > 0.18:
                    foreground_pts.append((ang, r_m, x, y))
            else:
                foreground_pts.append((ang, r_m, x, y))

        if len(foreground_pts) < min_pts:
            return []

        # 2. Adaptive Breakpoint Detector (Dietmayer)
        clusters = []
        current_cluster = [foreground_pts[0]]
        
        lambda_deg = 10.0 # Angolo limite di incidenza
        lambda_rad = np.deg2rad(lambda_deg)
        c0 = 0.08         # Incertezza base sensore (8 cm)

        for i in range(1, len(foreground_pts)):
            prev_ang, prev_r, prev_x, prev_y = current_cluster[-1]
            curr_ang, curr_r, curr_x, curr_y = foreground_pts[i]

            d_theta = np.deg2rad(abs(curr_ang - prev_ang) % 360.0)
            if d_theta == 0:
                d_theta = 0.005

            # Soglia di Dietmayer adattiva alla distanza r
            r_min = min(prev_r, curr_r)
            d_thresh = r_min * (np.sin(d_theta) / np.sin(max(0.01, lambda_rad - d_theta))) + c0

            # Distanza euclidea tra campioni consecutivi
            eucl_dist = np.hypot(curr_x - prev_x, curr_y - prev_y)

            if eucl_dist <= d_thresh:
                current_cluster.append(foreground_pts[i])
            else:
                if len(current_cluster) >= min_pts:
                    clusters.append(current_cluster)
                current_cluster = [foreground_pts[i]]

        if len(current_cluster) >= min_pts:
            clusters.append(current_cluster)

        # 3. Classificazione Geometrica dei Cluster (PCA / Dimensioni)
        valid_targets = []
        target_id = 1

        for cl in clusters:
            if len(cl) > max_pts:
                continue

            pts_xy = np.array([[p[2], p[3]] for p in cl], dtype=np.float32)
            
            # Diametro massimo del cluster
            diff = pts_xy[:, np.newaxis, :] - pts_xy[np.newaxis, :, :]
            max_span = np.max(np.linalg.norm(diff, axis=-1))

            if 0.05 <= max_span <= max_diameter:
                # Analisi PCA per linearità (scarta segmenti piatti di muro residui)
                cov = np.cov(pts_xy, rowvar=False)
                if cov.shape == (2, 2):
                    eigenvalues, _ = np.linalg.eig(cov)
                    eigenvalues = np.sort(eigenvalues)[::-1]
                    # Se il cluster ha solo 1 dimensione (linea retta pura lunga), ha un rapporto di eccentricità altissimo
                    linearity = eigenvalues[0] / (eigenvalues[1] + 1e-6)
                    
                    # Un target (persona, palo, sedia) ha uno spessore proprio, quindi linearity non deve essere infinito su cluster grandi
                    if len(pts_xy) > 10 and linearity > 45.0 and max_span > 0.5:
                        continue

                valid_targets.append(DetectedTarget(target_id, pts_xy))
                target_id += 1

        return valid_targets