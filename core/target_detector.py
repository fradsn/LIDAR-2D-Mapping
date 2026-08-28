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
        self.radius_m = max(float(np.max(np.linalg.norm(self.points - self.centroid, axis=1))), 0.10)

class TargetDetector:
    @staticmethod
    def detect_targets_polar(polar_scan, background_map=None, min_pts=4, max_pts=70, max_diameter=0.85):
        if len(polar_scan) < min_pts:
            return []

        num_bg = len(background_map) if background_map is not None else 720

        # 1. Separazione Foreground Adattiva
        foreground_pts = []
        for ang, dist_cm, x, y in polar_scan:
            r_m = dist_cm / 100.0
            if background_map is not None:
                bg_idx = int((ang % 360.0) / (360.0 / num_bg)) % num_bg
                bg_dist = background_map[bg_idx]
                
                # Distacco netto rispetto al perimetro noto
                if bg_dist > 0.40 and (bg_dist - r_m) > 0.20 and (r_m / bg_dist) < 0.88:
                    foreground_pts.append((ang, r_m, x, y, bg_dist))
            else:
                foreground_pts.append((ang, r_m, x, y, r_m + 1.0))

        if len(foreground_pts) < min_pts:
            return []

        # 2. Adaptive Breakpoint Detector (Dietmayer)
        clusters = []
        current_cluster = [foreground_pts[0]]
        
        lambda_rad = np.deg2rad(10.0)
        c0 = 0.08

        for i in range(1, len(foreground_pts)):
            prev_ang, prev_r, prev_x, prev_y, _ = current_cluster[-1]
            curr_ang, curr_r, curr_x, curr_y, _ = foreground_pts[i]

            d_theta = np.deg2rad(abs(curr_ang - prev_ang) % 360.0)
            if d_theta == 0:
                d_theta = 0.005

            r_min = min(prev_r, curr_r)
            d_thresh = r_min * (np.sin(d_theta) / np.sin(max(0.01, lambda_rad - d_theta))) + c0
            eucl_dist = np.hypot(curr_x - prev_x, curr_y - prev_y)

            if eucl_dist <= d_thresh:
                current_cluster.append(foreground_pts[i])
            else:
                if len(current_cluster) >= min_pts:
                    clusters.append(current_cluster)
                current_cluster = [foreground_pts[i]]

        if len(current_cluster) >= min_pts:
            clusters.append(current_cluster)

        # 3. Classificazione Geometrica Istantanea (Senza ritardi)
        valid_targets = []
        target_id = 1

        for cl in clusters:
            if len(cl) > max_pts:
                continue

            pts_xy = np.array([[p[2], p[3]] for p in cl], dtype=np.float32)
            pts_r  = np.array([p[1] for p in cl], dtype=np.float32)
            pts_bg = np.array([p[4] for p in cl], dtype=np.float32)
            
            diff = pts_xy[:, np.newaxis, :] - pts_xy[np.newaxis, :, :]
            max_span = np.max(np.linalg.norm(diff, axis=-1))

            # Dimensioni valide del cluster
            if not (0.05 <= max_span <= max_diameter):
                continue

            # Distacco medio di almeno 20 cm dalla parete retrostante
            if np.mean(pts_bg - pts_r) < 0.20:
                continue

            # Scarto pareti lineari piatte (PCA)
            cov = np.cov(pts_xy, rowvar=False)
            if cov.shape == (2, 2):
                eigenvalues, _ = np.linalg.eig(cov)
                eigenvalues = np.sort(eigenvalues)[::-1]
                linearity = eigenvalues[0] / (eigenvalues[1] + 1e-6)
                
                if len(pts_xy) >= 6 and linearity > 25.0:
                    continue

            valid_targets.append(DetectedTarget(target_id, pts_xy))
            target_id += 1

        return valid_targets