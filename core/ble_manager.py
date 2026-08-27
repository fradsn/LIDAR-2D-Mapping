import struct
import asyncio
import threading
from PyQt6.QtCore import QObject, pyqtSignal
from bleak import BleakScanner, BleakClient

STEPPER_CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
LIDAR_CHAR_UUID   = "19b10001-e8f2-537e-4f6c-d104768a1214"

class BLEManager(QObject):
    angle_received = pyqtSignal(float)
    distance_received = pyqtSignal(float)
    status_changed = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._running = False
        self._thread = None
        self._loop = None

    def start(self):
        if self._running or (self._thread and self._thread.is_alive()):
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Richiede l'arresto immediato del thread asincrono."""
        if not self._running:
            return
        self.status_changed.emit("Disconnessione in corso...")
        self._running = False

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._worker())
        except asyncio.CancelledError:
            pass
        finally:
            self._loop.close()

    async def _worker(self):
        self.status_changed.emit("Scansione dispositivi BLE...")

        # Scansione parallela simultanea (max 5s)
        scan_stepper = BleakScanner.find_device_by_name("ESP32_RotaryPlate", timeout=5.0)
        scan_lidar   = BleakScanner.find_device_by_name("ESP32_LidarNode", timeout=5.0)
        
        stepper_dev, lidar_dev = await asyncio.gather(scan_stepper, scan_lidar)

        if not self._running:
            self.status_changed.emit("Connessione annullata.")
            self.connection_changed.emit(False)
            return

        if not stepper_dev or not lidar_dev:
            missing = []
            if not stepper_dev: missing.append("ESP32_RotaryPlate")
            if not lidar_dev: missing.append("ESP32_LidarNode")
            self.status_changed.emit(f"Non trovati: {', '.join(missing)}")
            self.connection_changed.emit(False)
            self._running = False
            return

        self.status_changed.emit("Connessione ai nodi...")

        def on_disconnect_stepper(client):
            self.status_changed.emit("ESP32 Motore disconnesso!")
            self._running = False

        def on_disconnect_lidar(client):
            self.status_changed.emit("ESP32 LiDAR disconnesso!")
            self._running = False

        client_stepper = BleakClient(stepper_dev, disconnected_callback=on_disconnect_stepper)
        client_lidar   = BleakClient(lidar_dev, disconnected_callback=on_disconnect_lidar)

        try:
            await asyncio.gather(client_stepper.connect(), client_lidar.connect())

            if not (client_stepper.is_connected and client_lidar.is_connected):
                raise ConnectionError("Impossibile stabilire la sessione con entrambi i nodi.")

            self.status_changed.emit("Dispositivi Connessi e Sincronizzati")
            self.connection_changed.emit(True)

            # --- Decodifica Pacchetti Binari ---

            def on_stepper(_, data):
                # Pacchetto: [uint32_t (4B)] + [float (4B)] = 8 Byte
                if len(data) == 8:
                    try:
                        timestamp_ms, angle = struct.unpack('<If', data)
                        self.angle_received.emit(angle)
                    except struct.error:
                        pass

            def on_lidar(_, data):
                # Pacchetto: [uint32_t (4B)] + [uint16_t (2B)] = 6 Byte
                if len(data) == 6:
                    try:
                        timestamp_ms, dist_cm = struct.unpack('<IH', data)
                        self.distance_received.emit(float(dist_cm))
                    except struct.error:
                        pass

            await client_stepper.start_notify(STEPPER_CHAR_UUID, on_stepper)
            await client_lidar.start_notify(LIDAR_CHAR_UUID, on_lidar)

            # Monitoraggio connessione
            while self._running and client_stepper.is_connected and client_lidar.is_connected:
                await asyncio.sleep(0.05)

        except Exception as e:
            self.status_changed.emit(f"Errore BLE: {str(e)}")
        finally:
            self._running = False
            
            async def disconnect_safe(client, uuid):
                if client and client.is_connected:
                    try:
                        await client.stop_notify(uuid)
                    except Exception:
                        pass
                    try:
                        await client.disconnect()
                    except Exception:
                        pass

            await asyncio.gather(
                disconnect_safe(client_stepper, STEPPER_CHAR_UUID),
                disconnect_safe(client_lidar, LIDAR_CHAR_UUID)
            )

            self.connection_changed.emit(False)
            self.status_changed.emit("Disconnesso")