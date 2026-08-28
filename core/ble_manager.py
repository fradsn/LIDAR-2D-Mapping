import struct
import asyncio
import threading
from PyQt6.QtCore import QObject, pyqtSignal
from bleak import BleakScanner, BleakClient

# UUID standard unificati
BASE_SERVICE_UUID      = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
BASE_AZIMUTH_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
BASE_CONTROL_CHAR_UUID = "beb5483f-36e1-4688-b7f5-ea07361b26a8"

PAYLOAD_SERVICE_UUID   = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
PAYLOAD_DATA_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
PAYLOAD_CTRL_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

SERVO_HORIZON_DEG = 135  # Quota orizzontale neutra
GEAR_RATIO = 6.0         # Riduzione 6:1 (6 giri motore = 1 giro piatto)

class BLEManager(QObject):
    angle_received = pyqtSignal(float)
    distance_received = pyqtSignal(float)
    status_changed = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)
    rssi_updated = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self._running = False
        self._thread = None
        self._loop = None
        self._client_stepper = None
        self._client_lidar = None
        self._cmd_queue = None
        self._stepper_rssi = 0
        self._lidar_rssi = 0

        # Tracciamento riduzione 6:1
        self._motor_rev_count = 0
        self._prev_motor_angle = 0.0

    def start(self):
        if self._running or (self._thread and self._thread.is_alive()):
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        if not self._running:
            return
        self.status_changed.emit("Disconnessione in corso...")
        self._running = False

    def start_scan(self, speed_rpm: int = 12):
        if self._loop and self._loop.is_running() and self._cmd_queue:
            payload = bytearray([0x01, int(speed_rpm)])
            self._loop.call_soon_threadsafe(self._cmd_queue.put_nowait, ("BASE", payload))

    def stop_scan(self):
        if self._loop and self._loop.is_running() and self._cmd_queue:
            payload = bytearray([0x00])
            self._loop.call_soon_threadsafe(self._cmd_queue.put_nowait, ("BASE", payload))

    def send_speed_command(self, speed_rpm: int):
        if self._loop and self._loop.is_running() and self._cmd_queue:
            payload = bytearray([0x01, int(speed_rpm)])
            self._loop.call_soon_threadsafe(self._cmd_queue.put_nowait, ("BASE", payload))

    def send_zero_calibration(self):
        self._motor_rev_count = 0
        self._prev_motor_angle = 0.0
        if self._loop and self._loop.is_running() and self._cmd_queue:
            payload = bytearray([0x02])
            self._loop.call_soon_threadsafe(self._cmd_queue.put_nowait, ("BASE", payload))

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._cmd_queue = asyncio.Queue()
        try:
            self._loop.run_until_complete(self._worker())
        except asyncio.CancelledError:
            pass
        finally:
            self._loop.close()

    async def _worker(self):
        self.status_changed.emit("Scansione dispositivi BLE...")
        self._motor_rev_count = 0
        self._prev_motor_angle = 0.0

        stepper_dev = None
        lidar_dev = None

        def on_device_found(device, adv_data):
            nonlocal stepper_dev, lidar_dev
            name = (device.name or "").strip()
            uuids = [str(u).lower() for u in (adv_data.service_uuids or [])]

            if name == "ESP32-Stepper-Base" or BASE_SERVICE_UUID.lower() in uuids:
                stepper_dev = device
                self._stepper_rssi = adv_data.rssi
            elif name == "ESP32-LiDAR-Tilt" or PAYLOAD_SERVICE_UUID.lower() in uuids:
                lidar_dev = device
                self._lidar_rssi = adv_data.rssi

        scanner = BleakScanner(detection_callback=on_device_found)
        await scanner.start()

        for _ in range(60):
            if stepper_dev and lidar_dev:
                break
            await asyncio.sleep(0.1)

        await scanner.stop()

        if not self._running or not stepper_dev or not lidar_dev:
            missing = []
            if not stepper_dev: missing.append("Base Stepper ('ESP32-Stepper-Base')")
            if not lidar_dev: missing.append("Payload LiDAR ('ESP32-LiDAR-Tilt')")
            self.status_changed.emit(f"Errore: Non trovati -> {', '.join(missing)}")
            self.connection_changed.emit(False)
            self._running = False
            return

        self.rssi_updated.emit(self._stepper_rssi, self._lidar_rssi)

        def on_disconnect_stepper(_):
            self.status_changed.emit("Base Stepper disconnessa!")
            self._running = False

        def on_disconnect_lidar(_):
            self.status_changed.emit("Payload LiDAR disconnesso!")
            self._running = False

        self._client_stepper = BleakClient(stepper_dev.address, disconnected_callback=on_disconnect_stepper, timeout=15.0)
        self._client_lidar   = BleakClient(lidar_dev.address, disconnected_callback=on_disconnect_lidar, timeout=15.0)

        try:
            self.status_changed.emit("Connessione ai nodi...")
            await self._client_stepper.connect()
            await asyncio.sleep(0.3)

            await self._client_lidar.connect()
            await asyncio.sleep(0.3)

            # Avvia stream LiDAR
            try:
                await self._client_lidar.write_gatt_char(PAYLOAD_CTRL_CHAR_UUID, bytearray([0x01]), response=False)
            except Exception as e:
                print(f"[BLE 2D] Errore start payload: {e}")

            await asyncio.sleep(0.2)

            # Allinea il servo a 135° (orizzonte)
            try:
                await self._client_lidar.write_gatt_char(PAYLOAD_CTRL_CHAR_UUID, bytearray([0x02, SERVO_HORIZON_DEG]), response=False)
                print(f"[BLE 2D] Servo allineato a {SERVO_HORIZON_DEG}°")
            except Exception as e:
                print(f"[BLE 2D] Errore posizionamento servo: {e}")

            self.status_changed.emit("Dispositivi Connessi. Pronto all'avvio.")
            self.connection_changed.emit(True)

            # Callback Azimuth (6 byte Big-Endian, riduzione 6:1)
            def on_stepper(_, data):
                if len(data) >= 6:
                    theta_raw, _ = struct.unpack('>HI', data[:6])
                    motor_angle = theta_raw / 10.0

                    if self._prev_motor_angle > 300.0 and motor_angle < 60.0:
                        self._motor_rev_count += 1
                    elif self._prev_motor_angle < 60.0 and motor_angle > 300.0:
                        self._motor_rev_count = max(0, self._motor_rev_count - 1)

                    self._prev_motor_angle = motor_angle
                    total_motor_deg = (self._motor_rev_count * 360.0) + motor_angle
                    plate_angle = (total_motor_deg / GEAR_RATIO) % 360.0
                    self.angle_received.emit(plate_angle)

            # Callback LiDAR
            def on_lidar(_, data):
                if len(data) >= 2:
                    dist_cm = (data[0] << 8) | data[1]
                    self.distance_received.emit(float(dist_cm))

            await self._client_stepper.start_notify(BASE_AZIMUTH_CHAR_UUID, on_stepper)
            await self._client_lidar.start_notify(PAYLOAD_DATA_CHAR_UUID, on_lidar)

            rssi_counter = 0
            while self._running and self._client_stepper.is_connected and self._client_lidar.is_connected:
                while not self._cmd_queue.empty():
                    target, cmd_payload = self._cmd_queue.get_nowait()
                    try:
                        if target == "BASE":
                            await self._client_stepper.write_gatt_char(BASE_CONTROL_CHAR_UUID, cmd_payload, response=False)
                        elif target == "PAYLOAD":
                            await self._client_lidar.write_gatt_char(PAYLOAD_CTRL_CHAR_UUID, cmd_payload, response=False)
                    except Exception as err:
                        print(f"Errore invio comando: {err}")

                rssi_counter += 1
                if rssi_counter >= 40:
                    rssi_counter = 0
                    try:
                        r1 = await self._client_stepper.get_rssi()
                        r2 = await self._client_lidar.get_rssi()
                        if r1 is not None and r2 is not None:
                            self._stepper_rssi = r1
                            self._lidar_rssi = r2
                            self.rssi_updated.emit(self._stepper_rssi, self._lidar_rssi)
                    except Exception:
                        pass

                await asyncio.sleep(0.05)

        except Exception as e:
            self.status_changed.emit(f"Errore BLE: {str(e)}")
        finally:
            self._running = False

            if self._client_stepper and self._client_stepper.is_connected:
                try:
                    await self._client_stepper.write_gatt_char(BASE_CONTROL_CHAR_UUID, bytearray([0x00]), response=False)
                except Exception:
                    pass

            if self._client_lidar and self._client_lidar.is_connected:
                try:
                    await self._client_lidar.write_gatt_char(PAYLOAD_CTRL_CHAR_UUID, bytearray([0x00]), response=False)
                except Exception:
                    pass

            async def disconnect_safe(client, uuid):
                if client and client.is_connected:
                    try: await client.stop_notify(uuid)
                    except Exception: pass
                    try: await client.disconnect()
                    except Exception: pass

            await asyncio.gather(
                disconnect_safe(self._client_stepper, BASE_AZIMUTH_CHAR_UUID),
                disconnect_safe(self._client_lidar, PAYLOAD_DATA_CHAR_UUID)
            )
            self.connection_changed.emit(False)
            self.status_changed.emit("Disconnesso")