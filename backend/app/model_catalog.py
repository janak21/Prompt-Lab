"""Discover account-visible models without storing keys or provider error bodies."""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from . import pricing
from .config import settings
from .schemas import ModelInfo, ModelsResponse, ProviderInfo

CACHE_SECONDS = 300
_cache: tuple[str, float, ModelsResponse] | None = None


def provider_model(model: str) -> tuple[str, str]:
    if ":" in model:
        provider, name = model.split(":", 1)
        if provider not in ("anthropic", "openai") or not name:
            raise ValueError("Use an anthropic: or openai: model identifier.")
        return provider, name
    if model.startswith("claude-"):
        return "anthropic", model
    if model.startswith(("gpt-", "chatgpt-")) or re.match(r"^o\d", model):
        return "openai", model
    raise ValueError("Unknown provider; use an anthropic: or openai: model identifier.")


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15)


async def _list_models(provider: str, key: str) -> list[dict[str, Any]]:
    url = "https://api.anthropic.com/v1/models" if provider == "anthropic" else "https://api.openai.com/v1/models"
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"} if provider == "anthropic" else {"Authorization": f"Bearer {key}"}
    rows: list[dict[str, Any]] = []
    params: dict[str, Any] = {"limit": 1000} if provider == "anthropic" else {}
    async with http_client() as client:
        while True:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            page = response.json()
            rows.extend(page["data"])
            if provider != "anthropic" or not page.get("has_more"):
                break
            cursor = page.get("last_id")
            if not cursor or cursor == params.get("after_id"):
                raise ValueError("Invalid model pagination.")
            params["after_id"] = cursor
    return rows


def _created(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return value if isinstance(value, str) else None


def _text_model(name: str) -> bool:
    # The list endpoint has no endpoint-capability metadata. Exclude known non-text
    # families; listed text candidates can still have endpoint/account restrictions.
    return name != "gpt-4" and not name.startswith(("gpt-3.", "gpt-4-")) and bool(re.match(r"^(gpt-|chatgpt-|o\d)", name)) and not any(
        part in name for part in ("audio", "realtime", "transcribe", "tts", "image", "instruct", "search", "deep-research")
    )


async def _provider_catalog(provider: str, key: str | None) -> tuple[list[ModelInfo], ProviderInfo]:
    if not key:
        return [], ProviderInfo(id=provider, key_present=False, status="missing_key")
    try:
        rows = await _list_models(provider, key)
        models = []
        for row in rows:
            name = row["id"]
            shutdown = row.get("shutdown_date")
            if shutdown and shutdown[:10] <= datetime.now(timezone.utc).date().isoformat():
                continue
            if provider == "openai" and not _text_model(name):
                continue
            id = name if provider == "anthropic" and name.startswith("claude-") else f"{provider}:{name}"
            price = pricing.get_price(id)
            capabilities = row.get("capabilities") or {}
            temperature = (capabilities.get("temperature") or {}).get("supported", pricing.supports_temperature(id))
            effort = (capabilities.get("effort") or {}).get("supported", pricing.supports_effort(id))
            pricing.DISCOVERED_CAPABILITIES[id] = {"temperature": bool(temperature), "effort": bool(effort)}
            models.append(ModelInfo(
                id=id, provider=provider, label=f"{'Anthropic' if provider == 'anthropic' else 'OpenAI'} · {row.get('display_name') or name}",
                created_at=_created(row.get("created_at", row.get("created"))), shutdown_date=shutdown,
                input_price_per_mtok=price.input_per_mtok if price else None,
                output_price_per_mtok=price.output_per_mtok if price else None,
                context_window=row.get("max_input_tokens") or (price.context_window if price else None),
                supports_prefill=pricing.supports_prefill(id), supports_temperature=bool(temperature),
                supports_effort=bool(effort),
            ))
        return models, ProviderInfo(id=provider, key_present=True, status="available")
    except (httpx.HTTPError, ValueError, KeyError, TypeError, OverflowError):
        # Do not return upstream error messages: some echo request/authentication data.
        return [], ProviderInfo(id=provider, key_present=True, status="error", error="Could not list models. Check the provider key, permissions, and connection, then refresh.")


async def discover_models(*, refresh: bool = False) -> ModelsResponse:
    global _cache
    keys = (settings.anthropic_api_key, settings.openai_api_key)
    fingerprint = hashlib.sha256(repr(keys).encode()).hexdigest()
    if not refresh and _cache and _cache[0] == fingerprint and time.monotonic() - _cache[1] < CACHE_SECONDS:
        return _cache[2]
    results = await asyncio.gather(*(_provider_catalog(provider, key) for provider, key in zip(("anthropic", "openai"), keys)))
    models = sorted((m for items, _ in results for m in items), key=lambda m: (m.created_at or "", m.id), reverse=True)
    ids = {m.id for m in models}

    def default(configured: str) -> str:
        if configured in ids:
            return configured
        preferred = next((m.id for m in models if m.provider == "anthropic"), None)
        return preferred or (models[0].id if models else "")

    result = ModelsResponse(models=models, providers=[p for _, p in results], default_model=default(settings.default_model), default_judge_model=default(settings.default_judge_model))
    _cache = (fingerprint, time.monotonic(), result)
    return result
