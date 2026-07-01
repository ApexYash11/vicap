from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from vicap.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class CompletionResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    latency_ms: float = 0


@dataclass
class UsageLedger:
    kimi_calls: int = 0
    minimax_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def record(self, result: CompletionResult, model_kind: str) -> None:
        if model_kind == "kimi":
            self.kimi_calls += 1
        else:
            self.minimax_calls += 1
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "kimi_calls": self.kimi_calls,
            "minimax_calls": self.minimax_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_calls": self.kimi_calls + self.minimax_calls,
        }


class FireworksClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.fireworks_api_key
        self.base_url = (base_url or settings.fireworks_base_url).rstrip("/")
        self.ledger = UsageLedger()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        model_kind: str = "minimax",
        max_tokens: int = 2048,
        temperature: float = 0.3,
        extra_body: dict[str, Any] | None = None,
    ) -> CompletionResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if extra_body:
            payload.update(extra_body)

        import time

        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=120.0) as client:
            for attempt in range(3):
                try:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    )
                    if resp.status_code == 429:
                        import asyncio

                        await asyncio.sleep(2**attempt)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except httpx.HTTPStatusError:
                    if attempt == 2:
                        raise
                    import asyncio

                    await asyncio.sleep(2**attempt)
            else:
                raise RuntimeError("Fireworks request failed after retries")

        latency_ms = (time.perf_counter() - start) * 1000
        choice = data["choices"][0]["message"]
        content = choice.get("content") or ""
        usage = data.get("usage") or {}
        result = CompletionResult(
            content=content,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=model,
            latency_ms=latency_ms,
        )
        self.ledger.record(result, model_kind)
        return result

    @staticmethod
    def parse_json_response(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            text = text.removeprefix("json").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise
