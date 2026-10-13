"""Route each generation/judge call independently to its selected provider."""

from typing import Any

import anthropic

from . import models
from .config import settings
from .llm import AnthropicLLM, LLMClient, LLMResult
from .model_catalog import discover_models, provider_model
from .openai_llm import OpenAILLM
from .schemas import RunCreate


class ProviderLLM(LLMClient):
    def __init__(self) -> None:
        self._clients: dict[str, LLMClient] = {}

    async def complete(self, messages, *, model: str, **kwargs: Any) -> LLMResult:
        provider, name = provider_model(model)
        if provider not in self._clients:
            if provider == "anthropic":
                if not settings.anthropic_api_key:
                    raise ValueError("Anthropic is not configured. Set ANTHROPIC_API_KEY on the server.")
                self._clients[provider] = AnthropicLLM(settings.anthropic_api_key)
            else:
                self._clients[provider] = OpenAILLM(settings.openai_api_key)
        try:
            result = await self._clients[provider].complete(messages, model=name, **kwargs)
        except anthropic.APIError as exc:
            status = getattr(exc, "status_code", "connection")
            raise ValueError(f"Anthropic request failed ({status}). Check model access, credentials, and connection.") from None
        result.model = model
        return result


async def resolve_run_models(body: RunCreate) -> RunCreate:
    version = models.get_prompt_version(body.prompt_version_id) or {}
    catalog = await discover_models()
    model = body.model or version.get("model") or catalog.default_model
    judge = body.judge_model or catalog.default_judge_model
    if not model or not judge:
        raise ValueError("No models available. Configure a provider key and refresh Models in Settings.")
    return body.model_copy(update={"model": model, "judge_model": judge})
