"""Account model discovery and cross-provider execution, always network-free."""

import json

import httpx
import pytest

from backend.app import model_catalog, models
from backend.app.config import settings
from backend.app.eval.runner import run_evaluation
from backend.app.llm import FakeLLM
from backend.app.main import app
from backend.app.openai_llm import OpenAILLM
from backend.app.providers import ProviderLLM, resolve_run_models
from backend.app.routers.runs import get_run_detail, prepare_run
from backend.app.schemas import RunCreate


def response(text="hello", *, output=None, status="completed"):
    return {"status": status, "output": output if output is not None else [{"type": "message", "id": "msg1", "role": "assistant", "content": [{"type": "output_text", "text": text}]}], "usage": {"input_tokens": 10, "output_tokens": 20}}


def stub_openai(monkeypatch, replies):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        reply = replies.pop(0)
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": "test credential must not be returned"})
        return httpx.Response(200, json=reply)

    client = OpenAILLM("test-key")
    monkeypatch.setattr(client, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return client, requests


async def test_catalog_dynamic_sort_cache_refresh_and_missing_price(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "anthropic-test")
    monkeypatch.setattr(settings, "openai_api_key", "openai-test")
    calls = []

    async def listed(provider, key):
        calls.append(provider)
        return [{"id": "claude-new", "display_name": "New Claude", "created_at": "2027-01-01T00:00:00Z"}] if provider == "anthropic" else [{"id": "gpt-new", "created": 1800000000}, {"id": "text-embedding-test", "created": 1900000000}, {"id": "gpt-audio-test", "created": 1900000001}, {"id": "gpt-retired", "created": 1800000001, "shutdown_date": "2000-01-01"}]

    monkeypatch.setattr(model_catalog, "_list_models", listed)
    catalog = await model_catalog.discover_models()
    assert {m.id for m in catalog.models} == {"claude-new", "openai:gpt-new"}
    assert catalog.models[0].created_at >= catalog.models[1].created_at
    assert all(m.input_price_per_mtok is None for m in catalog.models)
    assert catalog.default_model == "claude-new"
    assert len(calls) == 2
    await model_catalog.discover_models()
    assert len(calls) == 2
    await model_catalog.discover_models(refresh=True)
    assert len(calls) == 4
    monkeypatch.setattr(settings, "openai_api_key", "rotated-test")
    await model_catalog.discover_models()
    assert len(calls) == 6


async def test_catalog_errors_are_isolated_and_never_echo_keys(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "anthropic-test")
    monkeypatch.setattr(settings, "openai_api_key", "openai-test")

    async def listed(provider, key):
        if provider == "anthropic":
            raise ValueError("bad authentication: " + key)
        return [{"id": "gpt-new", "created": 1800000000}]

    monkeypatch.setattr(model_catalog, "_list_models", listed)
    catalog = await model_catalog.discover_models()
    assert [m.id for m in catalog.models] == ["openai:gpt-new"]
    assert catalog.providers[0].status == "error"
    assert catalog.default_model == "openai:gpt-new"
    assert "anthropic-test" not in catalog.model_dump_json()
    assert "openai-test" not in catalog.model_dump_json()


async def test_no_credentials_means_no_network_and_empty_catalog(monkeypatch):
    async def forbidden(*args):
        raise AssertionError("Network is forbidden")

    monkeypatch.setattr(model_catalog, "_list_models", forbidden)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        catalog = (await client.get("/api/models?refresh=true")).json()
        assert catalog["models"] == []
        assert all(p["status"] == "missing_key" for p in catalog["providers"])
        assert (await client.get("/api/health")).json()["provider_keys"] == {"anthropic": False, "openai": False}


async def test_anthropic_model_pagination(monkeypatch):
    cursors = []

    def handler(request):
        cursors.append(request.url.params.get("after_id"))
        assert request.headers["x-api-key"] == "test-key"
        return httpx.Response(200, json={"data": [{"id": "claude-a" if len(cursors) == 1 else "claude-b"}], "has_more": len(cursors) == 1, "last_id": "claude-a"})

    monkeypatch.setattr(model_catalog, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert len(await model_catalog._list_models("anthropic", "test-key")) == 2
    assert cursors == [None, "claude-a"]


async def test_openai_structured_judge_without_prefill_or_sampling(monkeypatch):
    client, requests = stub_openai(monkeypatch, [response('{"score":8}')])
    value = await client.json_complete([{"role": "user", "content": "Judge"}], model="gpt-new", schema={"type": "object", "properties": {"score": {"type": "number"}}, "required": ["score"], "additionalProperties": False})
    assert value == {"score": 8}
    assert requests[0]["text"]["format"]["strict"] is True
    assert requests[0]["store"] is False
    assert "temperature" not in requests[0]
    assert "reasoning" not in requests[0]


async def test_openai_retries_and_sanitizes_authentication_errors(monkeypatch):
    client, requests = stub_openai(monkeypatch, [429, response()])
    monkeypatch.setattr("backend.app.openai_llm._backoff_delay", lambda attempt: 0)
    assert (await client.complete([{"role": "user", "content": "Hi"}], model="gpt-new")).text == "hello"
    assert len(requests) == 2
    client, requests = stub_openai(monkeypatch, [401])
    with pytest.raises(ValueError, match="HTTP 401") as error:
        await client.complete([{"role": "user", "content": "Hi"}], model="gpt-new")
    assert "test credential" not in str(error.value)
    assert len(requests) == 1


async def test_anthropic_run_openai_judge_uses_same_engine(tmp_db, monkeypatch):
    prompt = models.create_prompt("Cross provider")
    version = models.create_prompt_version(prompt["id"], "{{task}}")
    dataset = models.create_dataset("Tasks")
    models.create_test_case(dataset["id"], {"task": "Say hello"})
    models.create_grader(prompt["id"], "llm_judge", "independent judge", {"rubric": "Helpful", "use_solution_criteria": False}, gating=True)
    openai, requests = stub_openai(monkeypatch, [response('{"strengths":[],"weaknesses":[],"reasoning":"Helpful","score":9}')])
    llm = ProviderLLM()
    llm._clients = {"anthropic": FakeLLM(default_response="hello"), "openai": openai}
    run = prepare_run(RunCreate(prompt_version_id=version["id"], dataset_id=dataset["id"], model="claude-haiku-4-5", judge_model="openai:gpt-new"))
    await run_evaluation(run["id"], llm)
    report = get_run_detail(run["id"])
    assert report.cases[0].passed is True
    assert report.stats.avg_score == 9
    assert report.run.judge_model == "openai:gpt-new"
    assert requests[0]["model"] == "gpt-new"
    assert "hello" in requests[0]["input"][0]["content"]


async def test_openai_conversation_replays_native_reasoning_and_tool_outputs(tmp_db, monkeypatch):
    prompt = models.create_prompt("Agent")
    version = models.create_prompt_version(prompt["id"], "Assist")
    tool = {"name": "lookup", "input_schema": {"type": "object"}, "response": {"ok": True}}
    dataset = models.create_dataset("Turns", tools=[tool])
    models.create_test_case(dataset["id"], {}, conversation=["Look it up", "Thanks"])
    models.create_grader(prompt["id"], "tool_calls", "lookup used", {"tool": "lookup", "mode": "called_with_arguments", "arguments": {}}, gating=True)
    native = [{"type": "reasoning", "id": "reason1", "summary": [], "encrypted_content": "opaque"}, {"type": "message", "id": "msg1", "role": "assistant", "content": [{"type": "output_text", "text": "Checking."}]}, {"type": "function_call", "id": "fc1", "call_id": "call1", "name": "lookup", "arguments": "{}"}]
    openai, requests = stub_openai(monkeypatch, [response(output=native), response("Found it"), response("You're welcome")])
    llm = ProviderLLM()
    llm._clients["openai"] = openai
    run = prepare_run(RunCreate(prompt_version_id=version["id"], dataset_id=dataset["id"], model="openai:gpt-new"))
    await run_evaluation(run["id"], llm)
    report = get_run_detail(run["id"])
    case = report.cases[0]
    assert case.passed is True
    assert case.output == "Checking.\nFound it\nYou're welcome"
    assert case.tool_calls[0]["name"] == "lookup"
    assert case.cost is None and report.stats.cost_complete is False
    assert requests[1]["input"][1:4] == native
    assert requests[1]["input"][-1]["type"] == "function_call_output"
    assert requests[1]["input"][-1]["call_id"] == "call1"
    assert requests[2]["input"][-1]["content"] == "Thanks"
    assert requests[0]["tools"][0]["strict"] is False


async def test_openai_only_defaults_are_available_models(tmp_db, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    async def listed(*args):
        return [{"id": "gpt-new", "created": 1800000000}]

    monkeypatch.setattr(model_catalog, "_list_models", listed)
    prompt = models.create_prompt("P")
    version = models.create_prompt_version(prompt["id"], "Hi")
    dataset = models.create_dataset("D")
    body = await resolve_run_models(RunCreate(prompt_version_id=version["id"], dataset_id=dataset["id"]))
    assert body.model == body.judge_model == "openai:gpt-new"


async def test_unknown_cost_does_not_pass_cost_gate(tmp_db, monkeypatch):
    prompt = models.create_prompt("P")
    version = models.create_prompt_version(prompt["id"], "Hi")
    dataset = models.create_dataset("D")
    models.create_test_case(dataset["id"], {})
    models.create_grader(prompt["id"], "budget", "cost", {"max_cost_usd": 1}, gating=True)
    openai, _ = stub_openai(monkeypatch, [response()])
    llm = ProviderLLM()
    llm._clients["openai"] = openai
    run = prepare_run(RunCreate(prompt_version_id=version["id"], dataset_id=dataset["id"], model="openai:gpt-new"))
    await run_evaluation(run["id"], llm)
    case = get_run_detail(run["id"]).cases[0]
    assert case.passed is False
    assert case.cost is None


@pytest.mark.parametrize("text,provider,name", [("claude-new", "anthropic", "claude-new"), ("anthropic:claude-new", "anthropic", "claude-new"), ("openai:gpt-new", "openai", "gpt-new"), ("gpt-new", "openai", "gpt-new")])
def test_provider_identifiers(text, provider, name):
    assert model_catalog.provider_model(text) == (provider, name)


def test_env_keys_resolve_independently_and_settings_are_preserved(tmp_path, monkeypatch):
    import os
    from backend.app import config

    child = tmp_path / "project"
    child.mkdir()
    (child / ".env").write_text("ANTHROPIC_API_KEY=anthropic-test\nDEFAULT_CONCURRENCY=9\n")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=openai-test\n")
    monkeypatch.setattr(config, "PROJECT_ROOT", child)
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEFAULT_CONCURRENCY"):
        monkeypatch.delenv(name, raising=False)
    config._find_and_load_env()
    assert os.environ["ANTHROPIC_API_KEY"] == "anthropic-test"
    assert os.environ["OPENAI_API_KEY"] == "openai-test"
    assert config.Settings().default_concurrency == 9
    assert "openai-test" not in repr(config.Settings())


def test_explicit_empty_environment_key_is_not_overridden(tmp_path, monkeypatch):
    import os
    from backend.app import config

    (tmp_path / ".env").write_text("OPENAI_API_KEY=openai-test\n")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    config._find_and_load_env()
    assert os.environ["OPENAI_API_KEY"] == ""


async def test_reverse_provider_judging_and_per_grader_override(tmp_db, monkeypatch):
    prompt = models.create_prompt("Cross provider")
    version = models.create_prompt_version(prompt["id"], "Hi")
    dataset = models.create_dataset("Tasks")
    models.create_test_case(dataset["id"], {})
    models.create_grader(prompt["id"], "llm_judge", "judge", {"rubric": "Helpful", "use_solution_criteria": False, "judge_model": "claude-haiku-4-5"})
    openai, requests = stub_openai(monkeypatch, [response("hello")])
    anthropic = FakeLLM(default_response='{"strengths":[],"weaknesses":[],"reasoning":"Helpful","score":9}')
    llm = ProviderLLM()
    llm._clients = {"anthropic": anthropic, "openai": openai}
    run = prepare_run(RunCreate(prompt_version_id=version["id"], dataset_id=dataset["id"], model="openai:gpt-new", judge_model="openai:gpt-new"))
    await run_evaluation(run["id"], llm)
    assert get_run_detail(run["id"]).stats.avg_score == 9
    assert len(requests) == 1
    assert anthropic.calls[0].model == "claude-haiku-4-5"


async def test_single_turn_truncation_fails_before_grading(tmp_db, monkeypatch):
    prompt = models.create_prompt("P")
    version = models.create_prompt_version(prompt["id"], "Hi")
    dataset = models.create_dataset("D")
    models.create_test_case(dataset["id"], {})
    models.create_grader(prompt["id"], "string_match", "text", {"must_contain": ["hello"]})
    openai, _ = stub_openai(monkeypatch, [response("hello", status="incomplete")])
    llm = ProviderLLM()
    llm._clients["openai"] = openai
    run = prepare_run(RunCreate(prompt_version_id=version["id"], dataset_id=dataset["id"], model="openai:gpt-new"))
    await run_evaluation(run["id"], llm)
    case = get_run_detail(run["id"]).cases[0]
    assert case.status == "failed" and case.passed is False
    assert case.output == "hello" and case.grades == []
