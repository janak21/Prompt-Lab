"""Tests for backend.app.llm: FakeLLM behavior, json_complete + repair, and
AnthropicLLM's retry/backoff logic against a stubbed transport. No real network calls."""

from __future__ import annotations

import json

import anthropic
import httpx
import pytest

from backend.app.llm import (
    AnthropicLLM,
    DEFAULT_MAX_TOKENS,
    FakeLLM,
    MAX_ATTEMPTS,
    NoTextBlockError,
    PrefillNotSupportedError,
    _first_text_block,
)


def _status_error(status_code: int) -> anthropic.APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code, request=request, json={"error": {"message": "boom"}})
    return anthropic.APIStatusError(message="boom", response=response, body={"error": {"message": "boom"}})


class TestFakeLLMComplete:
    async def test_default_response(self) -> None:
        fake = FakeLLM()
        result = await fake.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5")
        assert result.text == "OK"
        assert result.model == "claude-haiku-4-5"
        assert result.cost_usd > 0

    async def test_queued_responses_consumed_fifo(self) -> None:
        fake = FakeLLM()
        fake.queue_response("first")
        fake.queue_response("second")
        r1 = await fake.complete([], model="m")
        r2 = await fake.complete([], model="m")
        r3 = await fake.complete([], model="m")
        assert (r1.text, r2.text, r3.text) == ("first", "second", "OK")

    async def test_records_calls(self) -> None:
        fake = FakeLLM()
        await fake.complete(
            [{"role": "user", "content": "hi"}],
            model="claude-haiku-4-5",
            system="be nice",
            temperature=0.5,
            max_tokens=50,
            stop_sequences=["```"],
            prefill="```json",
        )
        assert fake.call_count == 1
        call = fake.calls[0]
        assert call.model == "claude-haiku-4-5"
        assert call.system == "be nice"
        assert call.prefill == "```json"
        assert call.stop_sequences == ["```"]

    async def test_prefill_in_result_prepends(self) -> None:
        fake = FakeLLM()
        fake.queue_response('{"a": 1}')
        result = await fake.complete([], model="claude-haiku-4-5", prefill="```json", prefill_in_result=True)
        assert result.text == '```json{"a": 1}'

    async def test_prefill_not_prepended_by_default(self) -> None:
        fake = FakeLLM()
        fake.queue_response('{"a": 1}')
        result = await fake.complete([], model="claude-haiku-4-5", prefill="```json")
        assert result.text == '{"a": 1}'

    async def test_queued_failure_raised(self) -> None:
        fake = FakeLLM()
        fake.queue_failure(RuntimeError("simulated failure"))
        with pytest.raises(RuntimeError, match="simulated failure"):
            await fake.complete([], model="m")
        # the failed call is still recorded
        assert fake.call_count == 1


class TestJsonComplete:
    async def test_parses_valid_json(self) -> None:
        fake = FakeLLM()
        fake.queue_response('{"score": 8}')
        result = await fake.json_complete([{"role": "user", "content": "grade this"}], model="claude-haiku-4-5")
        assert result == {"score": 8}

    async def test_repairs_once_on_bad_json(self) -> None:
        fake = FakeLLM()
        fake.queue_response("not valid json")
        fake.queue_response('{"score": 9}')
        result = await fake.json_complete([{"role": "user", "content": "grade"}], model="claude-haiku-4-5")
        assert result == {"score": 9}
        assert fake.call_count == 2

    async def test_raises_after_repair_attempt_exhausted(self) -> None:
        fake = FakeLLM()
        fake.queue_response("still not json")
        fake.queue_response("still not json again")
        with pytest.raises(json.JSONDecodeError):
            await fake.json_complete([{"role": "user", "content": "grade"}], model="claude-haiku-4-5")
        assert fake.call_count == 2  # 1 initial + 1 repair attempt (default max_repair_attempts=1)


class TestAnthropicLLMRetry:
    def test_sdk_internal_retries_are_disabled(self) -> None:
        # The SDK's own default max_retries=2 would retry each messages.create() call
        # internally BEFORE _call_with_retry ever sees a failure -- stacking with our
        # own MAX_ATTEMPTS retry loop and silently exceeding the "max 4 attempts"
        # contract (API_CONTRACT.md rule 2) by up to 3x, with two independent backoff
        # schedules. AnthropicLLM must construct its client with max_retries=0 so
        # _call_with_retry is the sole source of retry/backoff behavior.
        llm = AnthropicLLM(api_key="fake-key")
        assert llm._client.max_retries == 0

    async def test_retries_on_429_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        calls = {"n": 0}

        class FakeUsage:
            input_tokens = 5
            output_tokens = 7

        class FakeContentBlock:
            type = "text"
            text = "hello"

        class FakeResponse:
            content = [FakeContentBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            calls["n"] += 1
            if calls["n"] < 3:
                raise _status_error(429)
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)
        monkeypatch.setattr("backend.app.llm._backoff_delay", lambda attempt: 0.0)

        result = await llm.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5")
        assert result.text == "hello"
        assert calls["n"] == 3

    async def test_gives_up_after_max_attempts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        calls = {"n": 0}

        async def fake_create(**kwargs: object) -> None:
            calls["n"] += 1
            raise _status_error(503)

        monkeypatch.setattr(llm._client.messages, "create", fake_create)
        monkeypatch.setattr("backend.app.llm._backoff_delay", lambda attempt: 0.0)

        with pytest.raises(anthropic.APIStatusError):
            await llm.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5")
        assert calls["n"] == MAX_ATTEMPTS

    async def test_never_retries_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        calls = {"n": 0}

        async def fake_create(**kwargs: object) -> None:
            calls["n"] += 1
            raise _status_error(401)

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        with pytest.raises(anthropic.APIStatusError):
            await llm.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5")
        assert calls["n"] == 1

    async def test_never_retries_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        calls = {"n": 0}

        async def fake_create(**kwargs: object) -> None:
            calls["n"] += 1
            raise _status_error(400)

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        with pytest.raises(anthropic.APIStatusError):
            await llm.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5")
        assert calls["n"] == 1

    async def test_retries_on_connection_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        calls = {"n": 0}

        class FakeUsage:
            input_tokens = 1
            output_tokens = 1

        class FakeContentBlock:
            type = "text"
            text = "ok"

        class FakeResponse:
            content = [FakeContentBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            calls["n"] += 1
            if calls["n"] < 2:
                raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)
        monkeypatch.setattr("backend.app.llm._backoff_delay", lambda attempt: 0.0)

        result = await llm.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5")
        assert result.text == "ok"
        assert calls["n"] == 2

    async def test_prefill_appended_and_stripped_from_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        seen_messages = {}

        class FakeUsage:
            input_tokens = 1
            output_tokens = 1

        class FakeContentBlock:
            type = "text"
            text = '{"a": 1}'

        class FakeResponse:
            content = [FakeContentBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            seen_messages["messages"] = kwargs["messages"]
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        result = await llm.complete(
            [{"role": "user", "content": "grade"}], model="claude-haiku-4-5", prefill="```json", stop_sequences=["```"]
        )
        assert seen_messages["messages"][-1] == {"role": "assistant", "content": "```json"}
        assert result.text == '{"a": 1}'  # prefill NOT re-prepended by default


class TestStructuredOutputVsPrefillCapabilityGating:
    """Claude Opus 5 / Sonnet 5 reject assistant-turn prefill (400) -- json_complete must
    use the structured-outputs path (output_config) for them, and only fall back to the
    prefill trick on models that still support it (e.g. Haiku 4.5)."""

    async def test_structured_output_path_used_for_claude_5_model(self) -> None:
        fake = FakeLLM()
        fake.queue_response('{"score": 9}')
        schema = {
            "type": "object",
            "properties": {"score": {"type": "integer"}},
            "required": ["score"],
            "additionalProperties": False,
        }
        result = await fake.json_complete(
            [{"role": "user", "content": "grade this"}], model="claude-sonnet-5", schema=schema
        )
        assert result == {"score": 9}
        assert fake.call_count == 1
        call = fake.calls[0]
        assert call.output_schema == schema
        assert call.prefill is None  # structured-output path never sends a prefill

    async def test_structured_output_path_never_sends_prefill_for_opus_5(self) -> None:
        fake = FakeLLM()
        fake.queue_response('{"ok": true}')
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
        # Would raise PrefillNotSupportedError if json_complete mistakenly tried the
        # prefill path for opus-5 -- it must not, since a schema was supplied.
        result = await fake.json_complete(
            [{"role": "user", "content": "check"}], model="claude-opus-5", schema=schema
        )
        assert result == {"ok": True}

    async def test_prefill_fallback_path_used_for_haiku_4_5_when_no_schema(self) -> None:
        fake = FakeLLM()
        fake.queue_response('{"score": 7}')
        result = await fake.json_complete(
            [{"role": "user", "content": "grade this"}], model="claude-haiku-4-5"
        )
        assert result == {"score": 7}
        call = fake.calls[0]
        assert call.prefill == "```json"
        assert call.output_schema is None

    async def test_prefill_directly_on_opus_5_raises_clear_error(self) -> None:
        fake = FakeLLM()
        with pytest.raises(PrefillNotSupportedError, match="claude-opus-5"):
            await fake.complete([{"role": "user", "content": "hi"}], model="claude-opus-5", prefill="```json")

    async def test_prefill_directly_on_sonnet_5_raises_clear_error(self) -> None:
        fake = FakeLLM()
        with pytest.raises(PrefillNotSupportedError, match="claude-sonnet-5"):
            await fake.complete([{"role": "user", "content": "hi"}], model="claude-sonnet-5", prefill="```json")

    async def test_json_complete_without_schema_on_opus_5_raises_clear_error(self) -> None:
        """No schema -> falls back to the prefill trick -- which must raise cleanly on opus-5."""
        fake = FakeLLM()
        with pytest.raises(PrefillNotSupportedError):
            await fake.json_complete([{"role": "user", "content": "grade"}], model="claude-opus-5")

    async def test_unknown_model_defaults_to_prefill_unsupported(self) -> None:
        """Locks down the deliberate safety default in pricing.supports_prefill(): an
        unknown/future model is assumed NOT to support prefill (restrictive default),
        because prefill is being removed across the Claude lineup and an opaque runtime
        400 is worse than routing through structured outputs. Do not flip this back to
        an optimistic default without updating this test deliberately."""
        fake = FakeLLM()
        with pytest.raises(PrefillNotSupportedError, match="'some-unreleased-model'"):
            await fake.complete([{"role": "user", "content": "hi"}], model="some-unreleased-model", prefill="```json")

    async def test_unknown_model_routes_through_structured_outputs_successfully(self) -> None:
        """The flip side of the restrictive default: an unknown model works fine as long
        as the caller uses the (recommended, uniformly-supported) schema= path instead
        of prefill."""
        fake = FakeLLM()
        fake.queue_response('{"ok": true}')
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
        result = await fake.json_complete(
            [{"role": "user", "content": "check"}], model="some-unreleased-model", schema=schema
        )
        assert result == {"ok": True}
        assert fake.calls[0].prefill is None
        assert fake.calls[0].output_schema == schema

    async def test_prefill_still_works_on_haiku_4_5(self) -> None:
        fake = FakeLLM()
        fake.queue_response("hello")
        result = await fake.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5", prefill="pre")
        assert result.text == "hello"

    async def test_complete_rejects_prefill_and_output_schema_together(self) -> None:
        fake = FakeLLM()
        with pytest.raises(ValueError, match="both"):
            await fake.complete(
                [{"role": "user", "content": "hi"}],
                model="claude-haiku-4-5",
                prefill="```json",
                output_schema={"type": "object"},
            )

    async def test_anthropic_llm_structured_output_sends_output_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        seen_params: dict[str, object] = {}

        class FakeUsage:
            input_tokens = 3
            output_tokens = 4

        class FakeContentBlock:
            type = "text"
            text = '{"score": 10}'

        class FakeResponse:
            content = [FakeContentBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            seen_params.update(kwargs)
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
        result = await llm.complete(
            [{"role": "user", "content": "grade"}], model="claude-sonnet-5", output_schema=schema
        )
        assert seen_params["output_config"] == {"format": {"type": "json_schema", "schema": schema}}
        assert "stop_sequences" not in seen_params or seen_params.get("stop_sequences") is None
        assert result.text == '{"score": 10}'

    async def test_anthropic_llm_raises_before_calling_api_when_prefill_unsupported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        called = {"n": 0}

        async def fake_create(**kwargs: object) -> None:
            called["n"] += 1
            raise AssertionError("should never reach the API")

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        with pytest.raises(PrefillNotSupportedError):
            await llm.complete([{"role": "user", "content": "hi"}], model="claude-opus-5", prefill="```json")
        assert called["n"] == 0


class TestThinkingBlockTextExtraction:
    """Claude 5 models run adaptive thinking by default, so response.content often
    starts with a ThinkingBlock before any TextBlock. AnthropicLLM.complete must never
    index content[0] directly -- it must scan for the first type == "text" block, and
    raise a clear NoTextBlockError (not an AttributeError) if none exists."""

    async def test_skips_leading_thinking_block(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")

        class FakeUsage:
            input_tokens = 20
            output_tokens = 30

        class FakeThinkingBlock:
            type = "thinking"
            # No `.text` attribute at all -- indexing content[0].text on this block
            # would raise AttributeError, which is exactly the bug being fixed.

        class FakeTextBlock:
            type = "text"
            text = '{"score": 7}'

        class FakeResponse:
            content = [FakeThinkingBlock(), FakeTextBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        result = await llm.complete(
            [{"role": "user", "content": "grade this"}], model="claude-sonnet-5", output_schema={"type": "object"}
        )
        assert result.text == '{"score": 7}'

    async def test_skips_multiple_leading_thinking_blocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")

        class FakeUsage:
            input_tokens = 20
            output_tokens = 30

        class FakeThinkingBlock:
            type = "thinking"

        class FakeRedactedThinkingBlock:
            type = "redacted_thinking"

        class FakeTextBlock:
            type = "text"
            text = "final answer"

        class FakeResponse:
            content = [FakeThinkingBlock(), FakeRedactedThinkingBlock(), FakeTextBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        result = await llm.complete([{"role": "user", "content": "hi"}], model="claude-opus-5")
        assert result.text == "final answer"

    async def test_no_text_block_raises_clear_error_not_attribute_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Response entirely made of thinking blocks (e.g. cut off by max_tokens
        mid-thinking, before any answer text) -- must raise NoTextBlockError, never a
        raw AttributeError from indexing content[0]."""
        llm = AnthropicLLM(api_key="fake-key")

        class FakeUsage:
            input_tokens = 5
            output_tokens = 5

        class FakeThinkingBlock:
            type = "thinking"

        class FakeResponse:
            content = [FakeThinkingBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        with pytest.raises(NoTextBlockError, match="claude-sonnet-5"):
            await llm.complete([{"role": "user", "content": "hi"}], model="claude-sonnet-5")

    async def test_empty_content_list_raises_clear_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")

        class FakeUsage:
            input_tokens = 0
            output_tokens = 0

        class FakeResponse:
            content: list[object] = []
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        with pytest.raises(NoTextBlockError):
            await llm.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5")

    def test_first_text_block_helper_directly(self) -> None:
        class Block:
            def __init__(self, type_: str, text: str | None = None) -> None:
                self.type = type_
                if text is not None:
                    self.text = text

        assert _first_text_block([Block("thinking"), Block("text", "hi")], "m") == "hi"
        with pytest.raises(NoTextBlockError):
            _first_text_block([Block("thinking")], "m")


class TestTemperatureCapabilityGating:
    """Claude Opus 5 / Sonnet 5 removed sampling parameters -- sending any `temperature`
    returns HTTP 400. AnthropicLLM.complete must OMIT the parameter entirely for models
    where pricing.supports_temperature() is false, never clamp it and never raise."""

    async def test_temperature_omitted_for_sonnet_5(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        seen_params: dict[str, object] = {}

        class FakeUsage:
            input_tokens = 1
            output_tokens = 1

        class FakeContentBlock:
            type = "text"
            text = "ok"

        class FakeResponse:
            content = [FakeContentBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            seen_params.update(kwargs)
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        result = await llm.complete(
            [{"role": "user", "content": "hi"}], model="claude-sonnet-5", temperature=0.3
        )
        assert "temperature" not in seen_params
        assert result.text == "ok"  # succeeds -- does not raise, does not clamp

    async def test_temperature_omitted_for_opus_5(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        seen_params: dict[str, object] = {}

        class FakeUsage:
            input_tokens = 1
            output_tokens = 1

        class FakeContentBlock:
            type = "text"
            text = "ok"

        class FakeResponse:
            content = [FakeContentBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            seen_params.update(kwargs)
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        await llm.complete([{"role": "user", "content": "hi"}], model="claude-opus-5", temperature=0.9)
        assert "temperature" not in seen_params

    async def test_temperature_sent_for_haiku_4_5(self, monkeypatch: pytest.MonkeyPatch) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        seen_params: dict[str, object] = {}

        class FakeUsage:
            input_tokens = 1
            output_tokens = 1

        class FakeContentBlock:
            type = "text"
            text = "ok"

        class FakeResponse:
            content = [FakeContentBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            seen_params.update(kwargs)
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        await llm.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5", temperature=0.3)
        assert seen_params["temperature"] == 0.3

    async def test_temperature_omitted_for_unknown_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unknown/future models default to supports_temperature=False (restrictive,
        same safe direction as supports_prefill) -- omit rather than risk a 400."""
        llm = AnthropicLLM(api_key="fake-key")
        seen_params: dict[str, object] = {}

        class FakeUsage:
            input_tokens = 1
            output_tokens = 1

        class FakeContentBlock:
            type = "text"
            text = "ok"

        class FakeResponse:
            content = [FakeContentBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            seen_params.update(kwargs)
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        await llm.complete(
            [{"role": "user", "content": "hi"}], model="some-unreleased-model", temperature=0.5
        )
        assert "temperature" not in seen_params


class TestDefaultMaxTokensFloor:
    """DEFAULT_MAX_TOKENS replaces the old 1000-token default -- too low a budget lets
    adaptive thinking consume the whole cap and leave no room for the answer."""

    def test_default_max_tokens_is_a_sensible_floor(self) -> None:
        assert DEFAULT_MAX_TOKENS >= 4096

    async def test_fake_llm_uses_default_max_tokens_when_unspecified(self) -> None:
        fake = FakeLLM()
        await fake.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5")
        assert fake.calls[0].max_tokens == DEFAULT_MAX_TOKENS

    async def test_anthropic_llm_sends_default_max_tokens_when_unspecified(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        llm = AnthropicLLM(api_key="fake-key")
        seen_params: dict[str, object] = {}

        class FakeUsage:
            input_tokens = 1
            output_tokens = 1

        class FakeContentBlock:
            type = "text"
            text = "ok"

        class FakeResponse:
            content = [FakeContentBlock()]
            usage = FakeUsage()

        async def fake_create(**kwargs: object) -> FakeResponse:
            seen_params.update(kwargs)
            return FakeResponse()

        monkeypatch.setattr(llm._client.messages, "create", fake_create)

        await llm.complete([{"role": "user", "content": "hi"}], model="claude-haiku-4-5")
        assert seen_params["max_tokens"] == DEFAULT_MAX_TOKENS
