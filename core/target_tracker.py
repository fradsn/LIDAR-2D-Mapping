import time
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

class TrackerState:
    SEARCHING = "SEARCHING"
    LOCKED = "LOCKED"
    REACQUIRING = "REACQUIRING"

class TargetTracker(QObject):
    state_changed = pyqtSignal(str)
    tracking_sector_updated = pyqtSignal(float, float, float)
    cone_cleared = pyqtSignal()

    def __init__(self, ble_manager, base_rpm=12, tracking_rpm=14):
        super().__init__()
        self.ble = ble_manager
        self.base_rpm = base_rpm
        self.tracking_rpm = tracking_rpm

        self.enabled = False
        self.state = TrackerState.SEARCHING

        self.active_target_id = None
        self.target_azimuth = 0.0
        self.target_distance = 0.0
        self.locked_center_azimuth = 0.0

        self.cone_half_width_deg = 18.0
        self.last_seen_time = 0.0
        self.lock_confirmations = 0

        self._last_cmd_time = 0.0
        self._last_sent_sector = (0.0, 360.0)

    def set_enabled(self, enabled: bool):
        """Attiva o disattiva la modalità di inseguimento automatico."""
        self.enabled = enabled
        if not self.enabled:
            self.reset_to_full_scan()
        else:
            self.state = TrackerState.SEARCHING
            self.lock_confirmations = 0
            self.state_changed.emit("🎯 Auto-Tracking Attivo: Ricerca Bersagli a 360°...")

    def reset_to_full_scan(self):
        """Ripristina istantaneamente la scansione continua a 360° sulla base."""
        self.state = TrackerState.SEARCHING
        self.active_target_id = None
        self.lock_confirmations = 0
        self._last_sent_sector = (0.0, 360.0)
        self.cone_cleared.emit()
        self.state_changed.emit("Tracking Disattivato: Ripristino Scansione 360°")
        
        if self.ble:
            self.ble.start_scan(speed_rpm=self.base_rpm, min_deg=0.0, max_deg=360.0)

    def process_targets(self, targets):
        if not self.enabled:
            return

        now = time.perf_counter()

        # -------------------------------------------------------------
        # STATO 1: SEARCHING (Ricerca bersagli a 360°)
        # -------------------------------------------------------------
        if self.state == TrackerState.SEARCHING:
            valid_candidates = [t for t in targets if t.distance_m > 0.25 and t.radius_m <= 0.70]

            if valid_candidates:
                primary = min(valid_candidates, key=lambda t: t.distance_m)
                self.lock_confirmations += 1

                if self.lock_confirmations >= 2:
                    self.active_target_id = primary.id
                    self.target_azimuth = primary.azimuth_deg
                    self.locked_center_azimuth = primary.azimuth_deg
                    self.target_distance = primary.distance_m
                    self.last_seen_time = now
                    self.state = TrackerState.LOCKED
                    self.state_changed.emit(f"🎯 AGGANCIATO: Target {primary.id} ({primary.distance_m:.2f}m, {primary.azimuth_deg:.1f}°)")
                    self._update_cone(now, force=True)
            else:
                self.lock_confirmations = 0

        # -------------------------------------------------------------
        # STATO 2: LOCKED (Inseguimento a Cono con Deadband)
        # -------------------------------------------------------------
        elif self.state == TrackerState.LOCKED:
            matched_target = None
            if targets:
                for t in targets:
                    az_diff = abs(t.azimuth_deg - self.locked_center_azimuth)
                    if az_diff > 180.0:
                        az_diff = 360.0 - az_diff
                    if az_diff <= (self.cone_half_width_deg + 12.0) and abs(t.distance_m - self.target_distance) < 0.60:
                        matched_target = t
                        break

            if matched_target:
                self.last_seen_time = now
                self.target_distance = 0.8 * self.target_distance + 0.2 * matched_target.distance_m
                self.target_azimuth = matched_target.azimuth_deg

                shift = abs(matched_target.azimuth_deg - self.locked_center_azimuth)
                if shift > 180.0:
                    shift = 360.0 - shift

                # Sposta il cono solo se il target si muove di oltre 4.5° e dopo 1.2s
                if shift >= 4.5 and (now - self._last_cmd_time > 1.2):
                    self.locked_center_azimuth = matched_target.azimuth_deg
                    self._update_cone(now, force=False)
                else:
                    min_deg = (self.locked_center_azimuth - self.cone_half_width_deg) % 360.0
                    max_deg = (self.locked_center_azimuth + self.cone_half_width_deg) % 360.0
                    self.tracking_sector_updated.emit(min_deg, max_deg, self.locked_center_azimuth)
            else:
                if (now - self.last_seen_time) > 4.5:
                    self.state = TrackerState.REACQUIRING
                    self.state_changed.emit("⚠️ Target Perso: Allargamento cono...")
                    self._widen_cone(now)

        # -------------------------------------------------------------
        # STATO 3: REACQUIRING (Allargamento Cono)
        # -------------------------------------------------------------
        elif self.state == TrackerState.REACQUIRING:
            matched_target = None
            if targets:
                matched_target = min(targets, key=lambda t: t.distance_m)

            if matched_target:
                self.active_target_id = matched_target.id
                self.target_azimuth = matched_target.azimuth_deg
                self.locked_center_azimuth = matched_target.azimuth_deg
                self.target_distance = matched_target.distance_m
                self.last_seen_time = now
                self.state = TrackerState.LOCKED
                self.state_changed.emit(f"🎯 RIAGGANCIATO: Target ({matched_target.distance_m:.2f}m)")
                self._update_cone(now, force=True)
            else:
                if (now - self.last_seen_time) > 7.0:
                    self.reset_to_full_scan()

    def _update_cone(self, now_time, force=False):
        if self.target_distance < 1.2:
            self.cone_half_width_deg = 22.0
        elif self.target_distance < 2.5:
            self.cone_half_width_deg = 18.0
        else:
            self.cone_half_width_deg = 15.0

        min_deg = (self.locked_center_azimuth - self.cone_half_width_deg) % 360.0
        max_deg = (self.locked_center_azimuth + self.cone_half_width_deg) % 360.0

        self.tracking_sector_updated.emit(min_deg, max_deg, self.locked_center_azimuth)

        if force or (now_time - self._last_cmd_time > 1.0):
            self._last_sent_sector = (min_deg, max_deg)
            self._last_cmd_time = now_time
            if self.ble:
                self.ble.set_scan_sector(min_deg, max_deg, speed_rpm=self.tracking_rpm)

    def _widen_cone(self, now_time):
        w_half = 35.0
        min_deg = (self.locked_center_azimuth - w_half) % 360.0
        max_deg = (self.locked_center_azimuth + w_half) % 360.0

        self.tracking_sector_updated.emit(min_deg, max_deg, self.locked_center_azimuth)
        self._last_sent_sector = (min_deg, max_deg)
        self._last_cmd_time = now_time
        if self.ble:
            self.ble.set_scan_sector(min_deg, max_deg, speed_rpm=self.tracking_rpm)