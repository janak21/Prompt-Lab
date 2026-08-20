"""Opt-in smoke tests against the REAL Anthropic API.

Every other test in this project uses :class:`backend.app.llm.FakeLLM` -- no test
suite run ever exercised a real response from Claude until this file existed. That gap
is exactly what let two production bugs ship silently (see ``docs/API_CONTRACT.md``
cross-cutting rules 0b/0c and the ``llm.py`` module docstring): ``content[0].text``
crashing on Claude 5's adaptive-thinking responses, and `temperature` 400ing on
Claude 5 models. This file makes a handful of tiny, cheap, real calls to prove those
fixes hold against the actual API, not just a mocked transport.

**Opt-in, double-guarded:**
1. Every test is marked ``@pytest.mark.live``. ``pyproject.toml`` sets
   ``addopts = "-m 'not live'"``, so a plain ``pytest`` / ``uv run pytest`` invocation
   (including CI) deselects this entire file automatically.
2. The whole module additionally self-skips unless ``PROMPTLAB_LIVE_TESTS=1`` is set
   in the environment -- so even an explicit ``pytest -m live`` without that env var
   does nothing. This is a deliberate belt-and-suspenders: a marker alone is one flag
   away from an accidental CI run; the env var must be set on purpose.

To actually run these (costs a small amount of real API spend):

    PROMPTLAB_LIVE_TESTS=1 uv run pytest -m live backend/tests/test_live_api.py -v

Requires ``ANTHROPIC_API_KEY`` to be resolvable (see ``backend/app/config.py`` --
walks up from the project root looking for a ``.env``). Every call below uses a small
``max_tokens`` and a minimal prompt to keep cost negligible.
"""

from __future__ import annotations

import os

import pytest

from backend.app.config import settings
from backend.app.llm import AnthropicLLM, NoTextBlockError

pytestmark = pytest.mark.live

_LIVE_ENABLED = os.environ.get("PROMPTLAB_LIVE_TESTS") == "1"

if not _LIVE_ENABLED:
    pytest.skip(
        "Live API tests are opt-in -- set PROMPTLAB_LIVE_TESTS=1 to run them "
        "(see this file's module docstring). Skipping entire module.",
        allow_module_level=True,
    )
elif not settings.anthropic_api_key:
    pytest.skip(
        "PROMPTLAB_LIVE_TESTS=1 is set but no ANTHROPIC_API_KEY was resolved -- "
        "cannot make real API calls. Skipping entire module.",
        allow_module_level=True,
    )


ALL_MODELS = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]

_SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "score": {"type": "integer"},
    },
    "required": ["reasoning", "score"],
    "additionalProperties": False,
}


@pytest.fixture(scope="module")
def llm() -> AnthropicLLM:
    return AnthropicLLM(api_key=settings.anthropic_api_key)


class TestStructuredOutputsOnAllModels:
    """docs/API_CONTRACT.md rule 0: structured outputs must be the primary path for
    JSON, and must work uniformly across the whole roster -- including the two models
    that no longer support the prefill trick at all."""

    @pytest.mark.parametrize("model", ALL_MODELS)
    async def test_structured_output_returns_valid_json(self, llm: AnthropicLLM, model: str) -> None:
        result = await llm.json_complete(
            [
                {
                    "role": "user",
                    "content": (
                        "Rate the quality of this one-word answer to 'Say the word ok': "
                        "'ok'. Give a one-sentence reasoning and a score from 1-10."
                    ),
                }
            ],
            model=model,
            schema=_SCORE_SCHEMA,
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == {"reasoning", "score"}
        assert isinstance(result["score"], int)
        assert 1 <= result["score"] <= 10


class TestThinkingBlockParsingOnSonnet5:
    """docs/API_CONTRACT.md rule 0c: Claude 5 models run adaptive thinking by default,
    so response.content frequently starts with a ThinkingBlock. This must not crash --
    confirmed here against claude-sonnet-5 (the default judge model) with a prompt
    substantial enough to plausibly trigger thinking, not just a trivial one-word ask
    that would mask the bug."""

    async def test_grading_style_prompt_does_not_crash(self, llm: AnthropicLLM) -> None:
        result = await llm.json_complete(
            [
                {
                    "role": "user",
                    "content": (
                        "You are grading a solution. Task: write a Python function "
                        "that returns the nth Fibonacci number. Solution:\n"
                        "def fib(n):\n    if n <= 1: return n\n    return fib(n-1) + fib(n-2)\n\n"
                        "Evaluate correctness and efficiency. Give a one-sentence "
                        "reasoning and a score from 1-10."
                    ),
                }
            ],
            model="claude-sonnet-5",
            schema=_SCORE_SCHEMA,
        )
        assert isinstance(result["score"], int)

    async def test_first_text_block_never_raises_attribute_error(self, llm: AnthropicLLM) -> None:
        """Regression guard for the exact reported crash: 'ThinkingBlock' object has
        no attribute 'text'. If content[0] is ever indexed directly again, this will
        raise AttributeError instead of the clean NoTextBlockError contract."""
        try:
            result = await llm.complete(
                [{"role": "user", "content": "In one word, what is 2+2?"}],
                model="claude-sonnet-5",
            )
        except NoTextBlockError:
            # Acceptable (documented) outcome if thinking consumed the whole budget --
            # NOT acceptable is an AttributeError, which is what this test guards.
            pass
        else:
            assert isinstance(result.text, str)


class TestTemperatureCapabilityGatingLive:
    """docs/API_CONTRACT.md rule 0b: temperature must be silently omitted for models
    that no longer accept it, and the call must still succeed (not raise, not 400)."""

    async def test_temperature_omitted_succeeds_on_sonnet_5(self, llm: AnthropicLLM) -> None:
        result = await llm.complete(
            [{"role": "user", "content": "Say the word ok."}],
            model="claude-sonnet-5",
            temperature=0.3,  # would 400 if sent -- must be silently omitted
        )
        assert isinstance(result.text, str)

    async def test_temperature_omitted_succeeds_on_opus_5(self, llm: AnthropicLLM) -> None:
        result = await llm.complete(
            [{"role": "user", "content": "Say the word ok."}],
            model="claude-opus-5",
            temperature=0.3,
        )
        assert isinstance(result.text, str)

    async def test_temperature_sent_succeeds_on_haiku_4_5(self, llm: AnthropicLLM) -> None:
        result = await llm.complete(
            [{"role": "user", "content": "Say the word ok."}],
            model="claude-haiku-4-5",
            temperature=0.3,
        )
        assert isinstance(result.text, str)
