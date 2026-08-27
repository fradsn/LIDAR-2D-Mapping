import struct
import asyncio
import threading
from PyQt6.QtCore import QObject, pyqtSignal
from bleak import BleakScanner, BleakClient

STEPPER_CHAR_UUID     = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
STEPPER_CMD_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a9"
LIDAR_CHAR_UUID       = "19b10001-e8f2-537e-4f6c-d104768a1214"

class BLEManager(QObject):
    angle_received = pyqtSignal(float)
    distance_received = pyqtSignal(float)
    status_changed = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)
    rssi_updated = pyqtSignal(int, int)  # (stepper_rssi, lidar_rssi)

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

    def send_speed_command(self, speed_rpm: int):
        if self._loop and self._loop.is_running() and self._cmd_queue:
            payload = bytearray([0x01, int(speed_rpm)])
            self._loop.call_soon_threadsafe(self._cmd_queue.put_nowait, payload)

    def send_zero_calibration(self):
        if self._loop and self._loop.is_running() and self._cmd_queue:
            payload = bytearray([0x02, 0x00])
            self._loop.call_soon_threadsafe(self._cmd_queue.put_nowait, payload)

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

        stepper_dev = None
        lidar_dev = None

        # Rilevamento continuo iniziale con lettura diretta del valore RSSI
        def on_device_found(device, adv_data):
            nonlocal stepper_dev, lidar_dev
            if device.name == "ESP32_RotaryPlate":
                stepper_dev = device
                self._stepper_rssi = adv_data.rssi
            elif device.name == "ESP32_LidarNode":
                lidar_dev = device
                self._lidar_rssi = adv_data.rssi

        scanner = BleakScanner(detection_callback=on_device_found)
        await scanner.start()
        
        # Attende fino a 5 secondi il rilevamento di entrambi
        for _ in range(50):
            if stepper_dev and lidar_dev:
                break
            await asyncio.sleep(0.1)
        
        await scanner.stop()

        if not self._running or not stepper_dev or not lidar_dev:
            self.status_changed.emit("Errore: Dispositivi non trovati.")
            self.connection_changed.emit(False)
            self._running = False
            return

        # Emette il primo valore RSSI valido ottenuto in scansione
        self.rssi_updated.emit(self._stepper_rssi, self._lidar_rssi)

        self.status_changed.emit("Connessione ai nodi...")

        def on_disconnect(_):
            self.status_changed.emit("Dispositivo disconnesso!")
            self._running = False

        self._client_stepper = BleakClient(stepper_dev, disconnected_callback=on_disconnect)
        self._client_lidar   = BleakClient(lidar_dev, disconnected_callback=on_disconnect)

        try:
            await asyncio.gather(self._client_stepper.connect(), self._client_lidar.connect())
            self.status_changed.emit("Dispositivi Connessi e Sincronizzati")
            self.connection_changed.emit(True)

            def on_stepper(_, data):
                if len(data) == 8:
                    _, angle = struct.unpack('<If', data)
                    self.angle_received.emit(angle)

            def on_lidar(_, data):
                if len(data) == 6:
                    _, dist_cm = struct.unpack('<IH', data)
                    self.distance_received.emit(float(dist_cm))

            await self._client_stepper.start_notify(STEPPER_CHAR_UUID, on_stepper)
            await self._client_lidar.start_notify(LIDAR_CHAR_UUID, on_lidar)

            rssi_counter = 0
            while self._running and self._client_stepper.is_connected and self._client_lidar.is_connected:
                # Gestione comandi da interfaccia
                while not self._cmd_queue.empty():
                    cmd_payload = self._cmd_queue.get_nowait()
                    try:
                        await self._client_stepper.write_gatt_char(STEPPER_CMD_CHAR_UUID, cmd_payload, response=False)
                    except Exception as err:
                        print(f"Errore invio comando: {err}")

                # Tentativo di polling RSSI con fallback sicuro
                rssi_counter += 1
                if rssi_counter >= 40:
                    rssi_counter = 0
                    try:
                        r1 = await self._client_stepper.get_rssi()
                        r2 = await self._client_lidar.get_rssi()
                        if r1 is not None and r2 is not None:
                            self._stepper_rssi = r1
                            self._lidar_rssi = r2
                    except Exception:
                        pass
                    
                    self.rssi_updated.emit(self._stepper_rssi, self._lidar_rssi)

                await asyncio.sleep(0.05)

        except Exception as e:
            self.status_changed.emit(f"Errore BLE: {str(e)}")
        finally:
            self._running = False
            async def disconnect_safe(client, uuid):
                if client and client.is_connected:
                    try: await client.stop_notify(uuid)
                    except Exception: pass
                    try: await client.disconnect()
                    except Exception: pass

            await asyncio.gather(
                disconnect_safe(self._client_stepper, STEPPER_CHAR_UUID),
                disconnect_safe(self._client_lidar, LIDAR_CHAR_UUID)
            )
            self.connection_changed.emit(False)
            self.status_changed.emit("Disconnesso")