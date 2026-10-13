"""Scripted conversations exercise the shared engine with structured FakeLLM replies."""

from types import SimpleNamespace

import httpx
import pytest
from anthropic.types import Message

from backend.app import cli, models
from backend.app.eval.conversation import MAX_TOOL_ROUNDS
from backend.app.eval.runner import run_evaluation
from backend.app.llm import AnthropicLLM, FakeLLM
from backend.app.main import app
from backend.app.routers.runs import get_llm_client, get_run_detail, prepare_run
from backend.app.schemas import RunCreate

TOOL = {"name": "refund", "description": "Mock refund", "input_schema": {"type": "object", "properties": {"amount": {"type": "integer"}}, "required": ["amount"], "additionalProperties": False}, "response": {"ok": True}}


def setup(*, mode="never_called", conversation=None):
    prompt = models.create_prompt("Support")
    version = models.create_prompt_version(prompt["id"], "Handle {{tier}} tickets.", system_prompt="Be helpful.")
    dataset = models.create_dataset("Tickets", tools=[TOOL])
    models.create_test_case(dataset["id"], {"tier": "standard"}, conversation=conversation or ["I paid yesterday.", "Actually I never paid."], category="contradictory")
    models.create_grader(prompt["id"], "tool_calls", "refund rule", {"tool": "refund", "mode": mode, "arguments": {"amount": 10}}, gating=True)
    return prepare_run(RunCreate(prompt_version_id=version["id"], dataset_id=dataset["id"]))


def tool_call(id="call1", name="refund", amount=10):
    return {"type": "tool_use", "id": id, "name": name, "input": {"amount": amount}}


async def test_multi_turn_tool_loop_preserves_text_and_every_call_snapshot(tmp_db):
    run = setup()
    models.update_dataset(run["dataset_id"], tools=[])
    fake = FakeLLM()
    fake.queue_message([{"type": "text", "text": "Checking eligibility."}, tool_call(), tool_call("call2")], stop_reason="tool_use")
    fake.queue_response("Refund complete.")
    fake.queue_response("Thanks for clarifying.")
    await run_evaluation(run["id"], fake)
    report = get_run_detail(run["id"])
    case = report.cases[0]
    assert case.passed is False
    assert case.final_score == 0
    assert len(case.tool_calls) == 2
    assert case.tool_calls[1]["response"] == {"ok": True}
    assert case.output == "Checking eligibility.\nRefund complete.\nThanks for clarifying."
    assert len(case.transcript) == 6
    assert fake.calls[0].messages == [{"role": "user", "content": "Handle standard tickets.\n\nI paid yesterday."}]
    assert fake.calls[1].messages[1]["content"][0]["text"] == "Checking eligibility."
    results = fake.calls[1].messages[-1]["content"]
    assert [result["tool_use_id"] for result in results] == ["call1", "call2"]
    assert all(result["type"] == "tool_result" for result in results)
    assert fake.calls[2].messages[-1]["content"] == "Actually I never paid."
    assert all(call.system == "Be helpful." and call.prefill is None for call in fake.calls)
    assert fake.calls[0].tools[0]["name"] == "refund"
    assert "response" not in fake.calls[0].tools[0]
    assert case.input_tokens == 30 and case.output_tokens == 30
    assert case.cost == pytest.approx(sum(0.00006 for _ in fake.calls))
    # Deleting the dataset still leaves the transcript and calls inspectable.
    models.delete_dataset(run["dataset_id"])
    assert len(get_run_detail(run["id"]).cases[0].transcript) == 6


@pytest.mark.parametrize("amount,passed", [(10, True), (5, False)])
async def test_argument_assertion_and_tool_only_reply(tmp_db, amount, passed):
    run = setup(mode="called_with_arguments", conversation=["Refund please."])
    fake = FakeLLM()
    fake.queue_message([tool_call(amount=amount)], stop_reason="tool_use")
    fake.queue_response("Done.")
    await run_evaluation(run["id"], fake)
    assert get_run_detail(run["id"]).cases[0].passed is passed


async def test_no_call_passes_never_called_gate(tmp_db):
    run = setup()
    await run_evaluation(run["id"], FakeLLM(default_response="Please contact support."))
    report = get_run_detail(run["id"])
    assert report.stats.pass_rate == 1
    assert report.cases[0].tool_calls == []


@pytest.mark.parametrize("call,error", [(tool_call(name="unknown"), "Unknown mock tool"), (tool_call(amount="ten"), "not of type 'integer'")])
async def test_bad_tool_call_fails_and_retains_partial_transcript(tmp_db, call, error):
    run = setup()
    fake = FakeLLM()
    fake.queue_message([{"type": "text", "text": "Attempting refund."}, call], stop_reason="tool_use")
    await run_evaluation(run["id"], fake)
    case = get_run_detail(run["id"]).cases[0]
    assert case.status == "failed" and case.passed is False
    assert error in case.error
    assert error in case.tool_calls[0]["error"]
    assert len(case.transcript) == 2
    assert case.output == "Attempting refund."


async def test_tool_round_limit_is_case_failure(tmp_db):
    run = setup(conversation=["Keep refunding."])
    fake = FakeLLM()
    for idx in range(MAX_TOOL_ROUNDS + 1):
        fake.queue_message([tool_call(id=f"call{idx}")], stop_reason="tool_use")
    await run_evaluation(run["id"], fake)
    case = get_run_detail(run["id"]).cases[0]
    assert "Exceeded 8 tool rounds" in case.error
    assert len(case.tool_calls) == MAX_TOOL_ROUNDS + 1
    assert fake.call_count == MAX_TOOL_ROUNDS + 1


async def test_truncated_response_fails_even_with_text(tmp_db):
    run = setup()
    fake = FakeLLM()
    fake.queue_message([{"type": "text", "text": "Partial reply"}], stop_reason="max_tokens")
    await run_evaluation(run["id"], fake)
    assert "truncated" in get_run_detail(run["id"]).cases[0].error


async def test_api_format_roundtrip_validation_and_clearing(tmp_db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/datasets", json={"name": "Tools", "tools": [TOOL]})
        assert response.status_code == 201
        dataset_id = response.json()["id"]
        assert response.json()["tools"] == [TOOL]
        response = await client.post(f"/api/datasets/{dataset_id}/cases", json={"inputs": {}, "conversation": ["Hi", "Bye"]})
        assert response.status_code == 201
        case_id = response.json()["id"]
        assert (await client.get(f"/api/datasets/{dataset_id}")).json()["cases"][0]["conversation"] == ["Hi", "Bye"]
        assert (await client.patch(f"/api/cases/{case_id}", json={"conversation": []})).json()["conversation"] == []
        assert (await client.patch(f"/api/datasets/{dataset_id}", json={"tools": []})).json()["tools"] == []
        assert (await client.post("/api/datasets", json={"name": "Bad", "tools": [TOOL, TOOL]})).status_code == 422
        assert (await client.post("/api/datasets", json={"name": "Bad", "tools": [{**TOOL, "input_schema": {"type": "nonsense"}}]})).status_code == 422
        assert (await client.patch(f"/api/cases/{case_id}", json={"conversation": ["hi"] * 21})).status_code == 422


def test_cli_can_run_conversation(tmp_db, tmp_path):
    setup()
    assert cli.main(["run", "--prompt", "Support", "--dataset", "Tickets", "--require-pass-rate", "1", "--json", str(tmp_path / "report.json")], llm=FakeLLM(default_response="No refund.")) == 0


async def test_conversation_launch_and_detail_through_http(tmp_db):
    run = setup()
    fake = FakeLLM(default_response="No refund.")
    app.dependency_overrides[get_llm_client] = lambda: fake
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/runs", json={"prompt_version_id": run["prompt_version_id"], "dataset_id": run["dataset_id"]})
            assert response.status_code == 202
            report = (await client.get(f"/api/runs/{response.json()['run_id']}")).json()
            assert report["stats"]["pass_rate"] == 1
            assert report["cases"][0]["passed"] is True
            assert len(report["cases"][0]["transcript"]) == 4
            assert report["cases"][0]["tool_calls"] == []
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


async def test_conversation_judge_receives_all_user_turns(tmp_db):
    run = setup()
    prompt_id = models.get_prompt_version(run["prompt_version_id"])["prompt_id"]
    models.create_grader(prompt_id, "llm_judge", "judge", {"rubric": "No refunds without payment", "use_solution_criteria": False}, gating=True, pass_threshold=9)
    run = prepare_run(RunCreate(prompt_version_id=run["prompt_version_id"], dataset_id=run["dataset_id"]))
    fake = FakeLLM()
    fake.queue_response("Please clarify.")
    fake.queue_response("No refund.")
    fake.queue_response('{"strengths": [], "weaknesses": [], "reasoning": "Followed policy", "score": 8}')
    await run_evaluation(run["id"], fake)
    case = get_run_detail(run["id"]).cases[0]
    assert case.passed is False
    judge_request = fake.calls[-1].messages[0]["content"]
    assert "I paid yesterday." in judge_request
    assert "Actually I never paid." in judge_request
    assert fake.calls[-1].output_schema is not None
    assert fake.calls[-1].prefill is None


@pytest.mark.parametrize("model,has_temperature", [("claude-sonnet-5", False), ("claude-haiku-4-5", True)])
async def test_anthropic_tool_response_uses_structured_blocks_without_prefill(monkeypatch, model, has_temperature):
    # Stub the SDK request, exercising the real adapter without an API call.
    client = AnthropicLLM(api_key="test-key")
    params = {}

    async def create(**kwargs):
        params.update(kwargs)
        return Message.model_validate({"id": "msg_test", "type": "message", "role": "assistant", "model": model, "content": [{"type": "thinking", "thinking": "check", "signature": "sig"}, {"type": "text", "text": "Checking."}, tool_call()], "stop_reason": "tool_use", "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 20}})

    monkeypatch.setattr(client, "_client", SimpleNamespace(messages=SimpleNamespace(create=create)))
    result = await client.complete([{"role": "user", "content": "Help"}], model=model, tools=[{k: v for k, v in TOOL.items() if k != "response"}], temperature=0.2)
    assert result.text == "Checking."
    assert result.content[0]["signature"] == "sig"
    assert result.content[-1]["type"] == "tool_use"
    assert result.stop_reason == "tool_use"
    assert ("temperature" in params) is has_temperature
    assert params["messages"][-1]["role"] == "user"
    assert params["tools"][0]["input_schema"] == TOOL["input_schema"]
