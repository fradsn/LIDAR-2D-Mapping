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
    connection_changed = pyqtSignal(bool)  # True = Connesso, False = Disconnesso

    def __init__(self):
        super().__init__()
        self._running = False
        self._thread = None
        self._loop = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Richiede la disconnessione pulita dei dispositivi."""
        if not self._running:
            return
        self.status_changed.emit("Disconnessione in corso...")
        self._running = False

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._worker())
        finally:
            self._loop.close()

    async def _worker(self):
        self.status_changed.emit("Scansione dispositivi BLE...")
        
        stepper_dev = await BleakScanner.find_device_by_name("ESP32_RotaryPlate", timeout=6.0)
        lidar_dev   = await BleakScanner.find_device_by_name("ESP32_LidarNode", timeout=6.0)

        if not self._running:
            self.status_changed.emit("Connessione annullata.")
            self.connection_changed.emit(False)
            return

        if not stepper_dev or not lidar_dev:
            self.status_changed.emit("Errore: Dispositivi BLE non trovati.")
            self.connection_changed.emit(False)
            self._running = False
            return

        self.status_changed.emit("Connessione ai nodi...")
        try:
            async with BleakClient(stepper_dev) as client_stepper, BleakClient(lidar_dev) as client_lidar:
                self.status_changed.emit("Dispositivi Connessi e Sincronizzati")
                self.connection_changed.emit(True)

                def on_stepper(_, data):
                    try:
                        self.angle_received.emit(float(data.decode().strip()))
                    except ValueError: pass

                def on_lidar(_, data):
                    try:
                        self.distance_received.emit(float(data.decode().strip()))
                    except ValueError: pass

                await client_stepper.start_notify(STEPPER_CHAR_UUID, on_stepper)
                await client_lidar.start_notify(LIDAR_CHAR_UUID, lidar_handler := on_lidar)

                # Loop di mantenimento attivo fino a richiesta di stop
                while self._running:
                    await asyncio.sleep(0.1)

                # Chiusura notifiche prima dell'uscita dal context manager
                try:
                    await client_stepper.stop_notify(STEPPER_CHAR_UUID)
                    await client_lidar.stop_notify(LIDAR_CHAR_UUID)
                except Exception:
                    pass

        except Exception as e:
            self.status_changed.emit(f"Disconnesso / Errore: {str(e)}")
        finally:
            self._running = False
            self.connection_changed.emit(False)
            self.status_changed.emit("Disconnesso")