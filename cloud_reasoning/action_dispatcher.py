"""Action Dispatcher: receives structured action commands, routes to the right subsystem.

Runs on Jetson OR in the cloud. Converts action commands into:
- GaitTarget (to send to Teensy via Serial)
- CloudAction (to send to TTS / emotive face)
"""

import json
import time
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class DispatchResult:
    serial_cmd: Optional[str]      # raw string to send to Teensy
    websocket_msg: Optional[dict]  # dict to send to cloud TTS/face
    local_action: Optional[str]     # e.g., "speak", "led_red"


class ActionDispatcher:
    """Routes ActionCommand -> hardware commands."""

    def __init__(
        self,
        on_serial: Optional[Callable[[str], None]] = None,
        on_websocket: Optional[Callable[[dict], None]] = None,
    ):
        self.on_serial = on_serial
        self.on_websocket = on_websocket

    def dispatch(self, cmd: dict) -
        DispatchResult:
        """Dispatch an action command to the right handler."""
        action_type = cmd.get("action_type", "none")
        params = cmd.get("parameters", {})
        result = DispatchResult(serial_cmd=None, websocket_msg=None, local_action=None)

        if action_type == "move":
            x = params.get("target_x", 0.0)
            y = params.get("target_y", 0.0)
            yaw = params.get("target_yaw", 0.0)
            speed = params.get("speed", 0.5)
            gait = params.get("gait", "walk")
            result.serial_cmd = f"TARGET {x:.4f} {y:.4f} {yaw:.4f} {speed:.3f} {gait}
"

        elif action_type == "halt":
            result.serial_cmd = "HALT
"

        elif action_type == "speak":
            text = params.get("text", "")
            result.websocket_msg = {"type": "tts", "text": text, "t": time.time()}

        elif action_type == "emote":
            emotion = params.get("emotion", "neutral")
            result.websocket_msg = {"type": "emote", "emotion": emotion, "t": time.time()}

        # Send if callbacks registered
        if result.serial_cmd and self.on_serial:
            self.on_serial(result.serial_cmd)
        if result.websocket_msg and self.on_websocket:
            self.on_websocket(result.websocket_msg)

        return result
