"""OpenAI Responses adapter for the existing evaluation and mock-tool engine."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from . import pricing
from .llm import DEFAULT_MAX_TOKENS, MAX_ATTEMPTS, LLMClient, LLMResult, Message, _backoff_delay


def _response_input(messages: list[Message]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.get("provider_content") is not None:
            # Replay encrypted reasoning and original call ids exactly; no server
            # response storage or previous_response_id is needed for the tool loop.
            items.extend(message["provider_content"])
            continue
        content = message["content"]
        if isinstance(content, str):
            items.append({"role": message["role"], "content": content})
            continue
        for block in content:
            if block["type"] == "text":
                items.append({"role": message["role"], "content": block["text"]})
            elif block["type"] == "tool_use":
                items.append({"type": "function_call", "call_id": block["id"], "name": block["name"], "arguments": json.dumps(block["input"])})
            elif block["type"] == "tool_result":
                items.append({"type": "function_call_output", "call_id": block["tool_use_id"], "output": block["content"]})
    return items


class OpenAILLM(LLMClient):
    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=120)

    async def _call_with_retry(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise ValueError("OpenAI is not configured. Set OPENAI_API_KEY on the server.")
        async with self.http_client() as client:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    response = await client.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {self._api_key}"}, json=params)
                    if response.is_success:
                        return response.json()
                    if response.status_code != 429 and response.status_code < 500:
                        raise ValueError(f"OpenAI request failed (HTTP {response.status_code}). Check the model, key permissions, and request settings.")
                except httpx.TransportError:
                    pass
                if attempt < MAX_ATTEMPTS:
                    await asyncio.sleep(_backoff_delay(attempt))
        raise ValueError("OpenAI request failed after retries. Check rate limits and connection.")

    async def complete(
        self, messages: list[Message], *, model: str, system: str | None = None,
        temperature: float = 1.0, max_tokens: int = DEFAULT_MAX_TOKENS,
        stop_sequences: list[str] | None = None, prefill: str | None = None,
        prefill_in_result: bool = False, tools: list[dict[str, Any]] | None = None,
        output_schema: dict[str, Any] | None = None, effort: str | None = None,
    ) -> LLMResult:
        if prefill is not None or stop_sequences:
            raise ValueError("OpenAI Responses uses structured outputs, without assistant prefill or stop sequences.")
        params: dict[str, Any] = {"model": model, "input": _response_input(messages), "max_output_tokens": max_tokens, "store": False, "include": ["reasoning.encrypted_content"]}
        if system:
            params["instructions"] = system
        # Model-list responses cannot certify sampling capabilities. Omit optional
        # tuning knobs unless supported; this also works for reasoning models.
        if pricing.supports_temperature(f"openai:{model}"):
            params["temperature"] = temperature
        if output_schema is not None:
            params["text"] = {"format": {"type": "json_schema", "name": "promptlab", "schema": output_schema, "strict": True}}
        if tools:
            params["tools"] = [{"type": "function", "name": tool["name"], "description": tool.get("description", ""), "parameters": tool["input_schema"], "strict": False} for tool in tools]
        started = asyncio.get_running_loop().time()
        response = await self._call_with_retry(params)
        content = []
        for item in response.get("output", []):
            if item["type"] == "message":
                for block in item.get("content", []):
                    if block["type"] == "refusal":
                        raise ValueError("OpenAI refused this evaluation response.")
                    if block["type"] == "output_text":
                        content.append({"type": "text", "text": block["text"]})
            elif item["type"] == "function_call":
                content.append({"type": "tool_use", "id": item["call_id"], "name": item["name"], "input": json.loads(item["arguments"])})
        if response.get("status") not in ("completed", "incomplete"):
            raise ValueError("OpenAI returned an unsuccessful evaluation response.")
        if not content:
            raise ValueError("OpenAI returned no text or tool calls; raise max tokens if reasoning consumed the budget.")
        usage = response.get("usage") or {}
        input_tokens, output_tokens = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        cost = pricing.cost(f"openai:{model}", input_tokens, output_tokens) if pricing.get_price(f"openai:{model}") else None
        stop_reason = "max_tokens" if response.get("status") == "incomplete" else ("tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn")
        return LLMResult(
            text="\n".join(b["text"] for b in content if b["type"] == "text"),
            input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost,
            latency_ms=int((asyncio.get_running_loop().time() - started) * 1000), model=model,
            content=content, stop_reason=stop_reason, provider_content=response.get("output", []),
        )
