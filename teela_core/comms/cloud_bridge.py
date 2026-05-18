"""WebSocket bridge to cloud reasoning node.

Runs on Jetson. Opens persistent WebSocket to cloud.
Sends: scene_state.json, Teensy status, sensor telemetry
Receives: action commands (MOVE, SPEAK, EMOTE, etc.)

"

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Optional, Callable

import websockets  # type: ignore[import]


@dataclass
class CloudAction:
    action_type: str  # move | speak | emote | halt | resume
    parameters: dict
    priority: int
    timestamp: float


class CloudBridge:
    """Persistent WebSocket client to cloud reasoning."""

    def __init__(
        self,
        uri: str = "ws://localhost:8080/teela",
        robot_id: str = "teela-001",
        on_action: Optional[Callable[[CloudAction], None]] = None,
        reconnect_interval: float = 5.0,
    ):
        self.uri = uri
        self.robot_id = robot_id
        self.on_action = on_action
        self.reconnect_interval = reconnect_interval
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._send_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self) -> bool:
        try:
            self._ws = await websockets.connect(self.uri)
            await self._ws.send(json.dumps({"type": "register", "id": self.robot_id}))
            return True
        except Exception:
            return False

    async def disconnect(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send_scene_state(self, scene_state: dict) -> None:
        payload = {"type": "scene_state", "data": scene_state, "t": time.time()}
        await self._send_queue.put(json.dumps(payload))

    async def send_telemetry(self, telemetry: dict) -> None:
        payload = {"type": "telemetry", "data": telemetry, "t": time.time()}
        await self._send_queue.put(json.dumps(payload))

    async def _sender(self) -> None:
        while self._running:
            try:
                msg = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
                if self._ws:
                    await self._ws.send(msg)
            except asyncio.TimeoutError:
                # Send heartbeat if idle
                if self._ws:
                    await self._ws.send(json.dumps({"type": "heartbeat", "t": time.time()}))

    async def _receiver(self) -> None:
        while self._running:
            try:
                if not self._ws:
                    connected = await self.connect()
                    if not connected:
                        await asyncio.sleep(self.reconnect_interval)
                        continue

                raw = await asyncio.wait_for(self._ws.recv(), timeout=30.0)
                data = json.loads(raw)
                if data.get("type") == "action" and self.on_action:
                    self.on_action(CloudAction(
                        action_type=data["action_type"],
                        parameters=data.get("parameters", {}),
                        priority=data.get("priority", 0),
                        timestamp=data.get("t", time.time()),
                    ))
            except asyncio.TimeoutError:
                # Connection idle, send heartbeat
                if self._ws:
                    try:
                        await self._ws.send(json.dumps({"type": "heartbeat"}))
                    except Exception:
                        self._ws = None
            except Exception:
                self._ws = None
                await asyncio.sleep(self.reconnect_interval)

    async def run(self) -> None:
        self._running = True
        await asyncio.gather(self._sender(), self._receiver())
