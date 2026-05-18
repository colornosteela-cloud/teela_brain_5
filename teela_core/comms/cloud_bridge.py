"""Cloud LLM bridge — Kimi REST API.

Sends prompt → Kimi → receives text reply.

Setup:
    export KIMI_API_KEY="your-key-here"

Or fallback: local vLLM endpoint.
"""

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class LLMResponse:
    text: str = ""
    latency_ms: float = 0.0
    tokens_used: int = 0
    finish_reason: str = "unknown"
    raw: Dict[str, Any] = field(default_factory=dict)


class CloudBridge:
    """Connect to Kimi or any OpenAI-compatible endpoint."""

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.provider = cfg.get("llm_provider", "kimi")
        self.model = cfg.get("llm_model", "kimi-k2.6")

        if self.provider == "ollama":
            self.api_base = cfg.get("api_base", "http://localhost:11434")
            self.api_key = ""
        else:
            self.api_base = cfg.get("api_base", "https://api.moonshot.cn/v1")
            self.api_key = os.getenv("KIMI_API_KEY") or cfg.get("api_key", "")

        self.temperature = cfg.get("temperature", 0.7)
        self.max_tokens = cfg.get("max_tokens", 1024)
        self.timeout_s = cfg.get("request_timeout_s", 30)

        self.system_prompt = self._load_system_prompt(cfg)
        self._last_context: List[Dict[str, str]] = []

    @staticmethod
    def _load_system_prompt(cfg: dict) -> str:
        sp_file = cfg.get("system_prompt_file", "docs/TEELA_SYSTEM_PROMPT.md")
        from pathlib import Path
        p = Path(sp_file)
        if p.exists():
            return p.read_text()
        return """You are Teela, a physical humanoid robot with a neck, eyes (camera),
and ears (microphone). You can see people, understand pointing gestures,
look at objects, and speak.
Respond briefly, warmly, and naturally — like a person, not an assistant.
Your body is a work in progress. Currently you only have a neck (pan/tilt).
"""

    def chat(self, user_message: str, extra_system: str = "", images: Optional[List[bytes]] = None) -> LLMResponse:
        """Send a message and get a reply.

        Args:
            user_message: the latest user utterance or scene description
            extra_system: additional context (e.g. emotion state, pointing info)
            images: optional base64-encoded images (not all models accept)

        Returns:
            LLMResponse with .text field
        """
        url = f"{self.api_base}/chat/completions"

        system = self.system_prompt
        if extra_system:
            system += f"\n\n[CURRENT CONTEXT]\n{extra_system}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]
        if images:
            # Vision: only if model supports it ( kimi-k2.6 does )
            content = [{"type": "text", "text": user_message}]
            for img_b64 in images:
                img_str = img_b64.decode() if isinstance(img_b64, bytes) else img_b64
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}})
            messages[1]["content"] = content

        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        t0 = time.time()
        try:
            if self.provider == "ollama":
                resp = self._chat_ollama(messages, t0)
            else:
                resp = self._chat_openai(req, t0)
            return resp
        except Exception as e:
            return LLMResponse(text=f"[LLM error: {e}]")

    def _chat_openai(self, req: urllib.request.Request, t0: float) -> LLMResponse:
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            body = json.loads(resp.read().decode())
        latency = (time.time() - t0) * 1000
        if "choices" in body and len(body["choices"]) > 0:
            reply = body["choices"][0]["message"]["content"]
            finish = body["choices"][0].get("finish_reason", "unknown")
            tokens = body.get("usage", {}).get("total_tokens", 0)
            return LLMResponse(
                text=reply.strip(),
                latency_ms=latency,
                tokens_used=tokens,
                finish_reason=finish,
                raw=body,
            )
        return LLMResponse(text="[No reply from LLM]", raw=body)

    def _chat_ollama(self, messages: List[dict], t0: float) -> LLMResponse:
        url = f"{self.api_base}/api/chat"
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            body = json.loads(resp.read().decode())
        latency = (time.time() - t0) * 1000
        if "message" in body:
            msg = body["message"]
            return LLMResponse(
                text=msg.get("content", "").strip(),
                latency_ms=latency,
                tokens_used=body.get("prompt_eval_count", 0) + body.get("eval_count", 0),
                finish_reason="stop" if not body.get("done_reason") else body["done_reason"],
                raw=body,
            )
        return LLMResponse(text="[No reply from Ollama]", raw=body)

    def quick_reply(self, prompt: str) -> str:
        """Simple interface: text in, text out."""
        return self.chat(prompt).text
