"""Serial communication to Teensy 4.1.

Sends NECK commands. Receives STATUS.
Uses pyserial. Thread-safe.
"""

import threading
import time
from typing import Callable, Dict, Optional

import serial


class SerialLink:
    """Talk to Teensy over USB Serial (CDC).

    Protocol line-based:
        → NECK <pan_deg> <tilt_deg> <speed_dps>
        ← ACK NECK pan=... tilt=...
        ← STATUS pan=... tilt=... uptime=...

    Thread-safe: call send_neck() from any thread.
    """

    NEUTRAL_PAN = 0.0
    NEUTRAL_TILT = 5.0

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baud: int = 921600,
        on_status: Optional[Callable[[dict], None]] = None,
    ):
        self.port = port
        self.baud = baud
        self.on_status = on_status

        self._ser: Optional[serial.Serial] = None
        self._connected = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._last_status: Dict[str, float] = {}
        self._last_neck_command = (self.NEUTRAL_PAN, self.NEUTRAL_TILT)

    # ── Lifecycle ────────────────────────────────────────────
    def connect(self) -> bool:
        try:
            self._ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.5,
                write_timeout=1.0,
            )
            time.sleep(0.05)  # let USB serial settle
            if self._ser.is_open:
                self._connected = True
                self._running = True
                self._thread = threading.Thread(target=self._read_loop, daemon=True)
                self._thread.start()
                print(f"[SerialLink] Opened {self.port} @ {self.baud}")
                return True
        except serial.SerialException as e:
            print(f"[SerialLink] Could not open {self.port}: {e}")
        return False

    def disconnect(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
        self._connected = False
        print("[SerialLink] Disconnected.")

    # ── Commands ───────────────────────────────────────────────
    def send_neck(self, pan_deg: float, tilt_deg: float, speed_dps: float = 30.0, hold_ms: int = 500) -> bool:
        """Send a neck pan/tilt command. Thread-safe."""
        if not self._connected or not self._ser:
            return False
        cmd = f"NECK {pan_deg:.1f} {tilt_deg:.1f} {speed_dps:.1f} {hold_ms}\r\n"
        with self._lock:
            try:
                self._ser.write(cmd.encode())
                self._ser.flush()
                self._last_neck_command = (pan_deg, tilt_deg)
                return True
            except serial.SerialException as e:
                print(f"[SerialLink] Write error: {e}")
                self._connected = False
        return False

    def send_halt(self) -> bool:
        return self.send_neck(
            self._last_neck_command[0],
            self._last_neck_command[1],
            speed_dps=5.0,
            hold_ms=2000,
        )

    def send_ping(self) -> bool:
        if not self._connected or not self._ser:
            return False
        with self._lock:
            try:
                self._ser.write(b"PING\r\n")
                self._ser.flush()
                return True
            except serial.SerialException:
                self._connected = False
        return False

    def get_status(self) -> Dict[str, float]:
        """Latest STATUS from Teensy."""
        return self._last_status.copy()

    # ── Internal read loop ───────────────────────────────────
    def _read_loop(self) -> None:
        buffer = bytearray()
        while self._running and self._ser:
            try:
                data = self._ser.read(256)
                if data:
                    buffer.extend(data)
                    while b"\n" in buffer or b"\r" in buffer:
                        line, _, buffer = buffer.partition(b"\n")
                        if not line:
                            line, _, buffer = buffer.partition(b"\r")
                        if line:
                            self._parse_line(line.decode("ascii", errors="replace").strip())
            except serial.SerialException:
                time.sleep(0.5)
            time.sleep(0.001)

    def _parse_line(self, line: str) -> None:
        if line.startswith("STATUS "):
            # STATUS pan=0.0 tilt=5.0 uptime=12345
            parts = line[7:].split()
            status = {}
            for p in parts:
                if "=" in p:
                    k, v = p.split("=", 1)
                    try:
                        status[k] = float(v)
                    except ValueError:
                        status[k] = v
            self._last_status = status
            if self.on_status:
                try:
                    self.on_status(status)
                except Exception:
                    pass
        elif line.startswith("ACK "):
            # ACK NECK pan=... tilt=...
            pass
        elif line.startswith("BOOT ") or line == "READY":
            print(f"[SerialLink] Teensy: {line}")
