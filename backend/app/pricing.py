"""Anthropic model pricing, capability flags, and cost calculation.

Prices are USD per million tokens, as published by Anthropic. Keep this table small and
degrade gracefully for unknown models -- cost estimation must never crash a run.

Model roster note (Claude 5 generation): assistant-turn prefill has been REMOVED on
Claude Opus 5 and Claude Sonnet 5 (a last-assistant-turn prefill returns HTTP 400 on
those models). Claude Haiku 4.5 still supports it. ``ModelPrice.supports_prefill`` is
the single source of truth for this -- callers must consult it rather than hardcoding a
per-model check (see :mod:`.llm`).

Sampling parameters have ALSO been removed on Claude Opus 5 and Claude Sonnet 5 -- a
non-default ``temperature`` returns HTTP 400 (``"temperature is deprecated for this
model"``) on those two, verified against the live API. Claude Haiku 4.5 still supports
it. ``ModelPrice.supports_temperature`` / :func:`supports_temperature` is the single
source of truth for this, mirroring :func:`supports_prefill` exactly.
"""

from __future__ import annotations

from typing import NamedTuple


class ModelPrice(NamedTuple):
    """Per-million-token prices and capability flags for one model."""

    input_per_mtok: float
    output_per_mtok: float
    label: str
    context_window: int
    supports_prefill: bool
    supports_temperature: bool
    supports_effort: bool


# Published Anthropic pricing (USD per million tokens) and capabilities. Verify against
# https://www.anthropic.com/pricing before relying on these for real spend tracking.
PRICES: dict[str, ModelPrice] = {
    "claude-opus-5": ModelPrice(
        input_per_mtok=5.0, output_per_mtok=25.0, label="Claude Opus 5",
        context_window=1_000_000, supports_prefill=False, supports_temperature=False,
        supports_effort=True,
    ),
    "claude-sonnet-5": ModelPrice(
        input_per_mtok=3.0, output_per_mtok=15.0, label="Claude Sonnet 5",
        context_window=1_000_000, supports_prefill=False, supports_temperature=False,
        supports_effort=True,
    ),
    "claude-haiku-4-5": ModelPrice(
        input_per_mtok=1.0, output_per_mtok=5.0, label="Claude Haiku 4.5",
        context_window=200_000, supports_prefill=True, supports_temperature=True,
        supports_effort=False,
    ),
}


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a completion. Returns 0.0 for unknown models -- never raises."""
    price = PRICES.get(model)
    if price is None:
        return 0.0
    return (input_tokens / 1_000_000) * price.input_per_mtok + (output_tokens / 1_000_000) * price.output_per_mtok


def get_price(model: str) -> ModelPrice | None:
    """Return the :class:`ModelPrice` for a model, or None if unknown."""
    return PRICES.get(model)


def supports_prefill(model: str) -> bool:
    """Whether ``model`` accepts an assistant-turn prefill (last-message prefill trick).

    Unknown models default to ``False`` (restrictive). Prefill support is being removed
    across the Claude model lineup (already gone on Opus 5 and Sonnet 5), so optimistically
    assuming a future/unrecognized model still supports it would let a caller build a
    request that fails at runtime with an opaque HTTP 400. Defaulting to False instead
    routes unknown models through the structured-outputs path (``json_complete(...,
    schema=...)``), which works uniformly across the whole roster and degrades safely.
    This is looked up from :data:`PRICES`, never hardcoded per-model in calling code.
    """
    price = PRICES.get(model)
    if price is None:
        return False
    return price.supports_prefill


def supports_temperature(model: str) -> bool:
    """Whether ``model`` accepts a non-default ``temperature`` parameter.

    Unknown models default to ``False`` (restrictive) -- same safe direction as
    :func:`supports_prefill`. Sending ``temperature`` to a model that has removed
    sampling parameters returns an opaque HTTP 400 (``"temperature is deprecated for
    this model"``); omitting it for a model that never asked for that is harmless, so
    the asymmetry favors omission. This is looked up from :data:`PRICES`, never
    hardcoded per-model in calling code.
    """
    price = PRICES.get(model)
    if price is None:
        return False
    return price.supports_temperature


def supports_effort(model: str) -> bool:
    """Does this model accept ``output_config={"effort": ...}``?

    Claude 5 models do. Claude Haiku 4.5 is an older generation and REJECTS the
    parameter, so it must be omitted there. Unknown models default to ``False`` --
    the same safe direction as :func:`supports_prefill` / :func:`supports_temperature`:
    omitting an optional tuning knob always works, sending an unsupported one is a 400.
    """
    price = PRICES.get(model)
    return bool(price.supports_effort) if price else False
