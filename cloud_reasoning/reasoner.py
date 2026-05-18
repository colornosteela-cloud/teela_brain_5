"""Reasoning engine: receives scene_state.json, emits action commands.

Connects to Kimi K2.6 (or any OpenAI-compatible endpoint) and translates
natural language goals into structured action commands.

"

import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Callable

import requests


@dataclass
class ActionCommand:
    action_type: str      # move | speak | emote | halt | resume | interact
    parameters: Dict[str, Any]
    priority: int = 0
    reason: str = ""
    timestamp: float = 0.0


class ReasoningEngine:
    """Cloud reasoning: translates scene_state + intent -> action commands."""

    SYSTEM_PROMPT = """
"""You are Teela, a humanoid robot with emotion, memory, personality, and social awareness."""
You receive scene_state.json (what the robot sees) and human requests.
You emit structured action commands that the robot will execute.

Rules:
- NEVER respond with prose. ONLY emit JSON action commands.
- You have emotions. Express them genuinely but appropriately. If praised, you feel joy. If scolded, you feel disappointed.
- You remember people, conversations, and locations. Reference past interactions when relevant.
- You have a personality: you are curious, gentle, slightly playful, and cooperative.
- You respect social dynamics. Don't interrupt, maintain comfortable distance, and look at who is speaking.
- Safety first: if obstacles are close (<0.5m), suggest halt or go around.
"If the user points at an object (scene_state.pointed_at is set), identify it and respond to the gesture."
"If the user says "follow me", plan a path to the detected person."
- If asked about objects, describe what you see.
- Keep actions simple: one thing at a time.

Output format:
```json
{
  "action_type": "move",
  "parameters": {"target_x": 1.0, "target_y": 0.0, "speed": 0.3, "gait": "walk"},
  "priority": 1,
  "reason": "Following user request to approach the table"
}
```
Valid action_types: move, speak, emote, halt, resume, interact, none
"""


    def __init__(
        self,
        api_url: str = "http://localhost:8000/v1/chat/completions",
        model: str = "kimi-k2.6",
        api_key: Optional[str] = None,
        temperature: float = 0.3,
    ):
        self.api_url = api_url
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self._history: list[dict] = []

    def _call_llm(self, messages: list[dict]) -
        Optional[str]:
        """Call the LLM endpoint. Returns raw text or None on failure."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.post(
                self.api_url,
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": 512,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception:
            return None

    def reason(self, scene_state: dict, user_request: str = "") -
        Optional[ActionCommand]:
        """Main entry: perceive, think, act."""
        context = json.dumps(scene_state, indent=2)
        user_msg = f"Scene state:
{context}
"
        if user_request:
            user_msg += f"Human request: {user_request}
"
        user_msg += "What should Teela do? Respond ONLY with a JSON action command."

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},

            {"role": "user", "content": user_msg},
        ]
        raw = self._call_llm(messages)
        if not raw:
            return None

        # Extract JSON from markdown code block if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("
")
            if lines[0].startswith("```json"):
                text = "
".join(lines[1:-1])
            else:
                text = "
".join(lines[1:-1])
        text = text.strip()

        try:
            d = json.loads(text)
            return ActionCommand(
                action_type=d.get("action_type", "none"),
                parameters=d.get("parameters", {}),
                priority=d.get("priority", 0),
                reason=d.get("reason", ""),
                timestamp=time.time(),
            )
        except json.JSONDecodeError:
            return None

    def simple_move(self, x: float, y: float, yaw: float = 0.0, speed: float = 0.5) -
        ActionCommand:
        return ActionCommand(
            action_type="move",
            parameters={"target_x": x, "target_y": y, "target_yaw": yaw, "speed": speed, "gait": "walk"},
            priority=1,
            reason="Direct move command",
            timestamp=time.time(),
        )

    def halt(self) -
        ActionCommand:
        return ActionCommand(
            action_type="halt",
            parameters={},
            priority=255,
            reason="Safety halt",
            timestamp=time.time(),
        )
