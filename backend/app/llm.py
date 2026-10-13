"""Async Anthropic client wrapper.

Provides :class:`LLMClient`, an ABC that both the real :class:`AnthropicLLM` and the
in-memory :class:`FakeLLM` implement, so callers (the eval runner, generation,
importers, routers) can depend on the abstract interface and tests can inject
:class:`FakeLLM` instead of hitting the network.

Structured JSON output (primary path)
--------------------------------------
:meth:`LLMClient.json_complete` gets validated JSON out of Claude via the Messages
API's structured-outputs feature: ``output_config={"format": {"type": "json_schema",
"schema": ...}}`` on ``messages.create()``. When ``schema`` is given (the expected,
primary usage), the API *guarantees* the first text block is valid JSON matching the
schema -- no prefill, no stop-sequence trick, no repair loop needed. This is required
because prefill support has been REMOVED on Claude Opus 5 and Claude Sonnet 5 (see
below), so it's the only path that works uniformly across the whole model roster.

The prefill trick (fallback path only, capability-gated)
-----------------------------------------------------------
An older technique for getting structured output out of Claude appends an
assistant-turn "prefill" (e.g. ```` ```json ````) and sets
``stop_sequences=["```"]``. Anthropic's API then returns only the *continuation* after
the prefill -- the prefill text itself is not echoed back. :meth:`LLMClient.complete`
reproduces this: pass ``prefill=...`` and it appends an assistant message with that
text before calling the API. By default the returned ``LLMResult.text`` is exactly
what the model generated (NOT including the prefill) -- pass ``prefill_in_result=True``
if the caller wants the full logical string (``prefill + completion``).

**As of the Claude 5 generation, assistant-turn prefill is no longer supported on every
model** -- Claude Opus 5 and Claude Sonnet 5 return HTTP 400 for a request whose last
message is an assistant-turn prefill. Claude Haiku 4.5 still supports it. This is NOT
hardcoded anywhere in this module: :func:`pricing.supports_prefill` is the single
source of truth (see ``docs/API_CONTRACT.md`` / the models table in ``pricing.py``),
and both :meth:`complete` implementations consult it before sending a prefill, raising
:class:`PrefillNotSupportedError` with an actionable message instead of letting a raw
400 surface. :meth:`json_complete` calls ``complete()`` for its fallback path, so it
inherits this guard automatically -- callers should prefer passing ``schema=`` and
never see the fallback path misfire on an unsupported model.

Sampling parameters (``temperature``) -- capability-gated, omit rather than clamp
--------------------------------------------------------------------------------
Claude Opus 5 and Claude Sonnet 5 have ALSO removed sampling parameters: sending any
``temperature`` (even the API's own former default) returns HTTP 400 ("temperature is
deprecated for this model"). :func:`pricing.supports_temperature` is the single source
of truth (mirrors :func:`supports_prefill` exactly). :meth:`AnthropicLLM.complete`
consults it and OMITS the ``temperature`` parameter entirely from the API call for
models that don't support it -- it does not clamp to 1.0 and does not raise, so a run
configured with a temperature slider still succeeds against those models; the value is
just not sent (the caller's ``temperature`` argument becomes a no-op for that model,
which is different from -- and safer than -- silently reinterpreting it).

Never index ``response.content[0]`` -- scan for the first text block
----------------------------------------------------------------------
Claude 5 models run adaptive thinking by default, so ``response.content`` frequently
starts with one or more ``ThinkingBlock`` / ``RedactedThinkingBlock`` entries before
any ``TextBlock``. Indexing ``content[0].text`` directly raises ``AttributeError`` on
any response where thinking fired -- and thinking is prompt-dependent, so this is
INTERMITTENT: a trivial prompt often returns a lone text block (masking the bug in a
smoke test) while a real grading/generation prompt triggers thinking and crashes. This
module never indexes ``content[0]`` -- :func:`_first_text_block` scans the whole list
for ``block.type == "text"`` and raises a clear, actionable error if none is found
(e.g. the response was cut off by ``max_tokens`` mid-thinking, before any text was
emitted). See :data:`DEFAULT_MAX_TOKENS` for the token-budget implication: thinking
tokens count toward ``max_tokens``, so a too-small budget can consume the whole cap on
thinking and leave no room for the answer.
"""

from __future__ import annotations

import asyncio
import json
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from copy import deepcopy
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from . import pricing
from .pricing import cost as compute_cost

Message = dict[str, Any]  # {"role": "user" | "assistant", "content": str}

MAX_ATTEMPTS = 4
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 529}
_NON_RETRYABLE_STATUS_CODES = {400, 401, 403}

DEFAULT_MAX_TOKENS = 4096

# json_complete() gets a bigger ceiling than a plain completion: its callers (the
# llm_judge grader, dataset generation) send long rubrics and long solutions, and on
# Claude 5 the model may spend thousands of tokens thinking before emitting any JSON.
# The first live end-to-end run failed exactly here -- 2 of 3 judge calls came back as
# thinking-only responses at 4096 and silently scored 0.
JSON_MAX_TOKENS = 16000

# json_complete() also asks for LOW effort where the model supports it. We want a small
# well-formed JSON object, not deep deliberation; low effort cuts both the truncation
# risk and the cost, and the judge's rubric does the analytical work.
JSON_EFFORT = "low"

# Multiplier applied to max_tokens when retrying a thinking-truncated response.
_TRUNCATION_RETRY_FACTOR = 4
"""Default ``max_tokens`` floor for :meth:`LLMClient.complete` / :meth:`json_complete`.

Claude 5 models run adaptive thinking by default, and thinking tokens count toward
``max_tokens`` -- a too-low budget (the previous default of 1000) can be entirely
consumed by thinking, leaving no room for the actual answer and tripping
:class:`NoTextBlockError`. 4096 gives headroom for typical grading/generation-sized
JSON answers plus a reasonable amount of adaptive thinking. Callers doing larger
generation work should pass an explicit, larger ``max_tokens``.
"""


class NoTextBlockError(RuntimeError):
    """Raised when a Claude response contains no ``type == "text"`` content block at
    all -- e.g. the response was entirely thinking blocks because it was cut off by
    ``max_tokens`` before any answer text was generated. Raised instead of returning
    an empty string, which would be indistinguishable from a legitimate empty
    completion, and instead of the ``AttributeError`` that indexing ``content[0]``
    directly would raise on a response that starts with a ``ThinkingBlock``."""

    def __init__(self, model: str, block_types: list[str], stop_reason: str | None = None) -> None:
        types = ", ".join(block_types) if block_types else "(no content blocks)"
        if stop_reason == "max_tokens":
            why = (
                "The response hit the max_tokens ceiling while still thinking, so no "
                "answer text was ever produced. This is a token-budget problem, not a "
                "malformed response: raise max_tokens, or lower output_config.effort "
                "so the model thinks less."
            )
        else:
            why = (
                f"stop_reason={stop_reason!r}. Thinking tokens count toward max_tokens; "
                "if this recurs, raise max_tokens or lower output_config.effort."
            )
        super().__init__(
            f"Model {model!r} returned no text content block (content block types: "
            f"{types}). {why}"
        )
        self.model = model
        self.block_types = block_types
        self.stop_reason = stop_reason


def _first_text_block(content: list[Any], model: str, stop_reason: str | None = None) -> str:
    """Return the ``.text`` of the first ``type == "text"`` block in a response's
    content list.

    NEVER index ``content[0]`` directly -- Claude 5 models run adaptive thinking by
    default, so ``content[0]`` is frequently a ``ThinkingBlock``, not a ``TextBlock``
    (see module docstring). Raises :class:`NoTextBlockError` if no text block exists.
    """
    for block in content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise NoTextBlockError(model, [getattr(block, "type", "?") for block in content], stop_reason)


class PrefillNotSupportedError(ValueError):
    """Raised when ``complete(..., prefill=...)`` is called on a model that rejects
    assistant-turn prefill (Claude Opus 5, Claude Sonnet 5, and the 4.6+ family) --
    raised proactively instead of letting the API return a raw, confusing 400."""

    def __init__(self, model: str) -> None:
        super().__init__(
            f"Model {model!r} does not support assistant-turn prefill (removed on "
            "Claude Opus 5 / Sonnet 5 and the 4.6+ family). Use json_complete(..., "
            "schema=...) for structured JSON output instead, or call complete() "
            "without `prefill` and use output_config-based structured outputs."
        )
        self.model = model


def _require_prefill_supported(model: str, prefill: str | None) -> None:
    """Raise :class:`PrefillNotSupportedError` if ``prefill`` is set but ``model``
    doesn't support it, per :func:`pricing.supports_prefill` (never hardcoded here)."""
    if prefill is not None and not pricing.supports_prefill(model):
        raise PrefillNotSupportedError(model)


@dataclass
class LLMResult:
    """The outcome of one completion call."""

    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    model: str
    content: list[dict[str, Any]] | None = None
    stop_reason: str | None = None


class LLMClient(ABC):
    """Abstract interface for a chat-completion backend.

    Implementations: :class:`AnthropicLLM` (real) and :class:`FakeLLM` (test double).
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        system: str | None = None,
        temperature: float = 1.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        stop_sequences: list[str] | None = None,
        prefill: str | None = None,
        prefill_in_result: bool = False,
        tools: list[dict[str, Any]] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        """Run one chat completion.

        If ``prefill`` is given, an assistant message with that text is appended to
        ``messages`` before the call (the prefill trick). The returned
        ``text`` is the model's continuation only, unless ``prefill_in_result=True``,
        in which case ``prefill`` is prepended to it. Implementations must raise
        :class:`PrefillNotSupportedError` (via :func:`_require_prefill_supported`)
        rather than sending a doomed request when ``model`` doesn't support prefill.

        If ``output_schema`` is given, the completion uses the Messages API's
        structured-outputs feature (``output_config={"format": {"type":
        "json_schema", "schema": output_schema}}``) -- the returned ``text`` is
        guaranteed valid JSON matching the schema. ``prefill`` and ``output_schema``
        are mutually exclusive; passing both is a caller error.
        """
        raise NotImplementedError

    async def json_complete(
        self,
        messages: list[Message],
        *,
        model: str,
        schema: dict[str, Any] | None = None,
        system: str | None = None,
        temperature: float = 1.0,
        max_tokens: int = JSON_MAX_TOKENS,
        max_repair_attempts: int = 1,
    ) -> Any:
        """Complete expecting a JSON value, preferring the structured-outputs API.

        **Primary path** (used whenever ``schema`` is given -- the recommended usage
        for all new callers, and the only path that works on every current model):
        passes ``schema`` to :meth:`complete` as ``output_schema``, which sets
        ``output_config={"format": {"type": "json_schema", "schema": schema}}`` on
        the underlying API call. The response is guaranteed valid JSON matching the
        schema -- no prefill, no repair retry needed.

        **Fallback path** (used only when ``schema`` is omitted): uses the
        ```` ```json ```` prefill + stop-sequence trick. This path is
        capability-gated -- :meth:`complete` raises :class:`PrefillNotSupportedError`
        if ``model`` doesn't support prefill (see module docstring). If the response
        isn't valid JSON, retries up to ``max_repair_attempts`` times (default 1) by
        appending the bad response plus a repair instruction and asking again, before
        finally raising the last :class:`json.JSONDecodeError`.
        """
        if schema is not None:
            result = await self.complete(
                messages,
                model=model,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                output_schema=schema,
                effort=JSON_EFFORT,
            )
            return json.loads(result.text.strip())

        stop_sequences = ["```"]
        result = await self.complete(
            messages,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            prefill="```json",
        )
        try:
            return json.loads(result.text.strip())
        except json.JSONDecodeError as exc:
            last_error = exc
            last_text = result.text
            working_messages = list(messages)
            for _ in range(max_repair_attempts):
                working_messages = [
                    *working_messages,
                    {"role": "assistant", "content": "```json" + last_text},
                    {
                        "role": "user",
                        "content": (
                            "That response was not valid JSON "
                            f"(parse error: {last_error}). Respond again with ONLY a "
                            "single valid JSON value -- no commentary, no markdown "
                            "fences beyond what is already started."
                        ),
                    },
                ]
                result = await self.complete(
                    working_messages,
                    model=model,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stop_sequences=stop_sequences,
                    prefill="```json",
                )
                try:
                    return json.loads(result.text.strip())
                except json.JSONDecodeError as exc2:
                    last_error = exc2
                    last_text = result.text
            raise last_error


class AnthropicLLM(LLMClient):
    """Real Anthropic-backed implementation, with retry/backoff and cost accounting."""

    def __init__(self, api_key: str | None) -> None:
        # max_retries=0: the SDK's own default (max_retries=2) would silently retry
        # each `messages.create()` call internally on 429/5xx BEFORE ever returning
        # control to `_call_with_retry` below -- so without this, a single logical
        # attempt from our retry loop's perspective is actually up to 3 real HTTP
        # requests, and MAX_ATTEMPTS (contractually "max 4 attempts", per
        # API_CONTRACT.md rule 2) would silently balloon to up to 4 * 3 = 12 real
        # requests with two independent, stacked backoff schedules. Disabling the
        # SDK's built-in retry makes `_call_with_retry` the single source of truth
        # for attempt count and backoff, matching the documented contract exactly.
        self._client = AsyncAnthropic(api_key=api_key, max_retries=0)

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        system: str | None = None,
        temperature: float = 1.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        stop_sequences: list[str] | None = None,
        prefill: str | None = None,
        prefill_in_result: bool = False,
        tools: list[dict[str, Any]] | None = None,
        output_schema: dict[str, Any] | None = None,
        effort: str | None = None,
    ) -> LLMResult:
        if prefill is not None and output_schema is not None:
            raise ValueError("complete() cannot take both `prefill` and `output_schema` -- pick one.")
        _require_prefill_supported(model, prefill)

        call_messages = list(messages)
        if prefill:
            call_messages.append({"role": "assistant", "content": prefill})

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": call_messages,
        }
        # Claude Opus 5 / Sonnet 5 removed sampling parameters entirely -- sending
        # `temperature` (even the former API default of 1.0) returns HTTP 400
        # ("temperature is deprecated for this model"). Per pricing.supports_temperature
        # (never hardcoded here), omit the parameter rather than clamping it -- the
        # caller's requested temperature just becomes a no-op for those models instead
        # of failing the whole call.
        if pricing.supports_temperature(model):
            params["temperature"] = temperature
        if tools:
            params["tools"] = tools
        if system:
            params["system"] = system
        if stop_sequences:
            params["stop_sequences"] = stop_sequences
        # `output_config` carries BOTH the structured-output format and the effort
        # knob, so build it once and merge -- assigning either one alone would drop the
        # other. `effort` is rejected outright by Claude Haiku 4.5 (an older generation),
        # so it is gated on pricing.supports_effort rather than sent unconditionally.
        output_config: dict[str, Any] = {}
        if output_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": output_schema}
        if effort is not None and pricing.supports_effort(model):
            output_config["effort"] = effort
        if output_config:
            params["output_config"] = output_config

        loop = asyncio.get_event_loop()
        start = loop.time()
        response = await self._call_with_retry(**params)
        latency_ms = int((loop.time() - start) * 1000)

        try:
            if tools is not None and getattr(response, "stop_reason", None) == "tool_use":
                # Tool-only responses are valid; keep every text block alongside calls.
                text = "\n".join(block.text for block in response.content if block.type == "text")
            else:
                text = _first_text_block(response.content, model, getattr(response, "stop_reason", None))
        except NoTextBlockError as exc:
            # Adaptive thinking ate the whole budget before producing an answer. A judge
            # grade is expensive to lose to a budget hiccup, so buy a bigger budget once
            # rather than surfacing a zero. Only retry the truncation case -- any other
            # empty response is a real error and must stay loud.
            if exc.stop_reason != "max_tokens":
                raise
            retry_params = dict(params)
            retry_params["max_tokens"] = max_tokens * _TRUNCATION_RETRY_FACTOR
            start = loop.time()
            response = await self._call_with_retry(**retry_params)
            latency_ms = int((loop.time() - start) * 1000)
            text = _first_text_block(response.content, model, getattr(response, "stop_reason", None))
        if prefill_in_result and prefill:
            text = prefill + text

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost_usd = compute_cost(model, input_tokens, output_tokens)

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            model=model,
            content=[block.model_dump(mode="json", exclude_none=True) for block in response.content] if tools is not None else None,
            stop_reason=getattr(response, "stop_reason", None),
        )

    async def _call_with_retry(self, **params: Any) -> Any:
        """Call the Messages API, retrying on 429 / 5xx / overloaded / connection errors.

        Exponential backoff with jitter, up to :data:`MAX_ATTEMPTS` total attempts.
        400 / 401 / 403 are never retried -- they indicate a request the retry can't fix.
        """
        last_exc: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await self._client.messages.create(**params)
            except anthropic.APIStatusError as exc:
                status = exc.status_code
                if status in _NON_RETRYABLE_STATUS_CODES:
                    raise
                if status not in _RETRYABLE_STATUS_CODES and status < 500:
                    raise
                last_exc = exc
            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
                last_exc = exc

            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(_backoff_delay(attempt))

        assert last_exc is not None
        raise last_exc


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: base doubles each attempt, plus up to 50% jitter."""
    base = 0.5 * (2 ** (attempt - 1))
    jitter = random.uniform(0, base * 0.5)
    return base + jitter


# --------------------------------------------------------------------------
# Test double
# --------------------------------------------------------------------------


@dataclass
class RecordedCall:
    """A record of one :meth:`FakeLLM.complete` invocation, for test assertions."""

    messages: list[Message]
    model: str
    system: str | None
    temperature: float
    max_tokens: int
    stop_sequences: list[str] | None
    prefill: str | None
    prefill_in_result: bool
    output_schema: dict[str, Any] | None
    tools: list[dict[str, Any]] | None = None


class FakeLLM(LLMClient):
    """Deterministic, network-free :class:`LLMClient` for tests and local development.

    Usage::

        fake = FakeLLM()
        fake.queue_response('{"score": 8}')
        result = await fake.complete([...], model="claude-haiku-4-5")
        assert result.text == '{"score": 8}'
        assert fake.calls[0].model == "claude-haiku-4-5"

    - :meth:`queue_response` / :attr:`default_response` control what ``complete``
      returns. Responses are consumed FIFO; once exhausted, ``default_response`` is
      used indefinitely. This applies uniformly whether the call came from a plain
      ``complete()``, the prefill fallback path, or the ``output_schema`` structured
      path in ``json_complete`` -- queue whatever JSON/text string the test needs.
    - :meth:`queue_failure` schedules an exception to be raised on a future call
      instead of returning a response (FIFO, one exception per queued call) --
      useful for exercising :class:`AnthropicLLM`-style retry logic against
      whatever grader/runner code depends on this client, or to simulate a call
      that fails without retries applying (this class does not itself retry).
    - Every call is recorded in :attr:`calls` in order, capturing every argument,
      including ``output_schema`` -- assert on it to verify the structured-output
      path (vs. the prefill path) was actually used.
    - Like :class:`AnthropicLLM`, raises :class:`PrefillNotSupportedError` when
      ``prefill`` is passed for a model :func:`pricing.supports_prefill` says
      doesn't support it -- so tests can exercise the same capability gate without
      a real client.
    """

    def __init__(
        self,
        *,
        default_response: str = "OK",
        default_input_tokens: int = 10,
        default_output_tokens: int = 10,
        default_latency_ms: int = 1,
    ) -> None:
        self.default_response = default_response
        self.default_input_tokens = default_input_tokens
        self.default_output_tokens = default_output_tokens
        self.default_latency_ms = default_latency_ms

        self._queued_responses: list[str | tuple[list[dict[str, Any]], str]] = []
        self._queued_failures: list[Exception] = []
        self.calls: list[RecordedCall] = []

    def queue_response(self, text: str) -> None:
        """Enqueue a response to be returned by the next ``complete`` call (FIFO)."""
        self._queued_responses.append(text)

    def queue_message(self, content: list[dict[str, Any]], *, stop_reason: str = "end_turn") -> None:
        """Queue structured Messages API content, including tool-use blocks."""
        self._queued_responses.append((deepcopy(content), stop_reason))

    def queue_failure(self, exc: Exception) -> None:
        """Enqueue an exception to be raised by the next ``complete`` call (FIFO)."""
        self._queued_failures.append(exc)

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        system: str | None = None,
        temperature: float = 1.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        stop_sequences: list[str] | None = None,
        prefill: str | None = None,
        prefill_in_result: bool = False,
        tools: list[dict[str, Any]] | None = None,
        output_schema: dict[str, Any] | None = None,
        effort: str | None = None,
    ) -> LLMResult:
        if prefill is not None and output_schema is not None:
            raise ValueError("complete() cannot take both `prefill` and `output_schema` -- pick one.")
        _require_prefill_supported(model, prefill)

        self.calls.append(
            RecordedCall(
                messages=deepcopy(messages),
                model=model,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                stop_sequences=stop_sequences,
                prefill=prefill,
                prefill_in_result=prefill_in_result,
                output_schema=output_schema,
                tools=deepcopy(tools),
            )
        )

        if self._queued_failures:
            raise self._queued_failures.pop(0)

        response = self._queued_responses.pop(0) if self._queued_responses else self.default_response
        if isinstance(response, tuple):
            content, stop_reason = response
            text = "\n".join(block["text"] for block in content if block["type"] == "text")
        else:
            text = response
            content = [{"type": "text", "text": text}]
            stop_reason = "end_turn"
        if prefill_in_result and prefill:
            text = prefill + text

        return LLMResult(
            text=text,
            input_tokens=self.default_input_tokens,
            output_tokens=self.default_output_tokens,
            cost_usd=compute_cost(model, self.default_input_tokens, self.default_output_tokens),
            latency_ms=self.default_latency_ms,
            model=model,
            content=content,
            stop_reason=stop_reason,
        )
