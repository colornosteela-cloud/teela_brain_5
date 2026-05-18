"""Serial link to Teensy 4.1 gait controller.

Protocol:
    Jetson tx:   TARGET <x_m> <y_m> <yaw_rad> <max_speed> <gait>

    Teensy rx:   STATUS <x> <y> <theta> <pitch> <roll> <fallen>

    Reflex tx:   HALT
   (immediate, no args)
    Reflex tx:   EMERGENCY_PARK

    Teensy rx:   ACK<cmd>

Baud rate: 921600 (Teensy can handle this easily)
Runs: async loop on Jetson, dedicated parse on Teensy.
"""

import asyncio
import serial  # type: ignore[import]
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class TeensyStatus:
    x_m: float
    y_m: float
    yaw_rad: float
    pitch_deg: float
    roll_deg: float
    fallen: bool


class SerialLink:
    """Non-blocking serial link to Teensy 4.1."""

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baud: int = 921600,
        on_status: Optional[Callable[[TeensyStatus], None]] = None,
    ):
        self.port = port
        self.baud = baud
        self.on_status = on_status
        self._ser: Optional[serial.Serial] = None
        self._running = False

    def connect(self) -> bool:
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.05)
            return True
        except serial.SerialException:
            return False

    def disconnect(self) -> None:
        if self._ser:
            self._ser.close()
            self._ser = None
        self._running = False

    def send_target(self, x_m: float, y_m: float, yaw_rad: float, max_speed: float, gait: str) -> None:
        if self._ser and self._ser.is_open:
            msg = f"TARGET {x_m:.4f} {y_m:.4f} {yaw_rad:.4f} {max_speed:.3f} {gait}
"
            self._ser.write(msg.encode())

    def send_halt(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.write(b"HALT
")

    def send_emergency_park(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.write(b"EMERGENCY_PARK
")

    def read_status(self) -> Optional[TeensyStatus]:
        if not self._ser or not self._ser.is_open:
            return None
        raw = self._ser.readline()
        if not raw:
            return None
        try:
            parts = raw.decode().strip().split()
            if len(parts) >= 6 and parts[0] == "STATUS":
                return TeensyStatus(
                    x_m=float(parts[1]),
                    y_m=float(parts[2]),
                    yaw_rad=float(parts[3]),
                    pitch_deg=float(parts[4]),
                    roll_deg=float(parts[5]),
                    fallen=parts[6].lower() == "true" if len(parts) > 6 else False,
                )
        except (ValueError, IndexError):
            pass
        return None

    async def status_loop(self) -> None:
        """Async coroutine that reads status lines and fires callback."""
        self._running = True
        while self._running:
            status = self.read_status()
            if status and self.on_status:
                self.on_status(status)
            await asyncio.sleep(0.01)  # 100 Hz read

    async def send_heartbeat(self) -> None:
        """Periodic heartbeat to detect Teensy disconnect."""
        while self._running:
            if self._ser and self._ser.is_open:
                self._ser.write(b"PING
")
            await asyncio.sleep(1.0)
