"""Scripted user turns and client-side mock tools; no external tool is executed."""

from __future__ import annotations

import json
from typing import Any

import jsonschema

from .. import models
from ..llm import LLMClient, LLMResult

MAX_TOOL_ROUNDS = 8


async def run_conversation(
    run_case_id: int,
    run: dict[str, Any],
    prompt_version: dict[str, Any],
    test_case: dict[str, Any],
    rendered: str,
    llm: LLMClient,
) -> LLMResult:
    """Persist each response and attempted call, including on an incomplete case.

    The rendered template prefixes the first user turn. Subsequent turns are literal
    strings. Assistant content is replayed intact (including thinking signatures),
    followed by one user message containing every pending tool_result.
    """
    tools = run.get("tools_snapshot") or []
    definitions = [{k: tool[k] for k in ("name", "description", "input_schema") if k in tool} for tool in tools]
    tools_by_name = {tool["name"]: tool for tool in tools}
    messages: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    replies: list[str] = []
    input_tokens = output_tokens = latency_ms = 0
    cost = 0.0

    def persist() -> None:
        models.update_run_case(
            run_case_id, transcript=messages, tool_calls=calls, output="\n".join(replies),
            input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=latency_ms, cost=cost,
        )

    for turn_idx, turn in enumerate(test_case["conversation"]):
        user_text = f"{rendered}\n\n{turn}" if turn_idx == 0 and rendered else turn
        messages.append({"role": "user", "content": user_text})
        persist()
        for round_idx in range(MAX_TOOL_ROUNDS + 1):
            result = await llm.complete(
                messages, model=run["model"], system=prompt_version.get("system_prompt"),
                temperature=run["temperature"], max_tokens=run["max_tokens"], tools=definitions,
            )
            input_tokens += result.input_tokens
            output_tokens += result.output_tokens
            latency_ms += result.latency_ms
            cost += result.cost_usd
            content = result.content or [{"type": "text", "text": result.text}]
            messages.append({"role": "assistant", "content": content})
            replies.extend(block["text"] for block in content if block["type"] == "text")
            pending = [block for block in content if block["type"] == "tool_use"]
            attempts = [{"id": block["id"], "name": block["name"], "input": block["input"], "turn": turn_idx + 1} for block in pending]
            calls.extend(attempts)
            persist()
            if result.stop_reason == "max_tokens":
                raise ValueError("Conversation response was truncated by max_tokens.")
            if not pending:
                if result.stop_reason not in (None, "end_turn", "stop_sequence"):
                    raise ValueError(f"Unsupported conversation stop_reason: {result.stop_reason!r}.")
                break
            if result.stop_reason != "tool_use":
                raise ValueError("Tool calls require stop_reason tool_use.")
            if round_idx == MAX_TOOL_ROUNDS:
                raise ValueError(f"Exceeded {MAX_TOOL_ROUNDS} tool rounds in user turn {turn_idx + 1}.")
            results = []
            for call in attempts:
                tool = tools_by_name.get(call["name"])
                try:
                    if tool is None:
                        raise ValueError(f"Unknown mock tool: {call['name']}.")
                    jsonschema.validate(call["input"], tool["input_schema"])
                except (ValueError, jsonschema.ValidationError) as exc:
                    call["error"] = str(exc)
                    persist()
                    raise ValueError(f"Mock tool {call['name']}: {exc}") from exc
                call["response"] = tool.get("response")
                results.append({"type": "tool_result", "tool_use_id": call["id"], "content": json.dumps(call["response"])})
            messages.append({"role": "user", "content": results})
            persist()

    return LLMResult(
        text="\n".join(replies), input_tokens=input_tokens, output_tokens=output_tokens,
        latency_ms=latency_ms, cost_usd=cost, model=run["model"],
    )
