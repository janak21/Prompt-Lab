"""Tests for backend.app.routers.runs, driven over httpx's ASGI transport against a
standalone FastAPI app that mounts only this router (registering the router on the
real app is another agent's job -- see the module docstring in routers/runs.py).

No real network call is ever made: the LLM client dependency is overridden with
FakeLLM for every test.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI

from backend.app import models
from backend.app.llm import FakeLLM
from backend.app.routers.runs import get_llm_client, router


def _make_app(fake: FakeLLM) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_llm_client] = lambda: fake
    return app


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM(default_response="hello world")


@pytest.fixture
async def client(fake_llm: FakeLLM):
    app = _make_app(fake_llm)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def _setup(template: str = "Echo: {{x}}", n_cases: int = 3, inputs_fn=None):
    prompt = models.create_prompt("P")
    version = models.create_prompt_version(prompt["id"], template, model="claude-haiku-4-5", temperature=0.0, max_tokens=100)
    dataset = models.create_dataset("D")
    for i in range(n_cases):
        inputs = inputs_fn(i) if inputs_fn else {"x": str(i)}
        models.create_test_case(dataset["id"], inputs)
    return prompt, version, dataset


class TestCreateRun:
    async def test_create_run_returns_202_and_runs_to_completion(self, client, tmp_db, fake_llm) -> None:
        _, version, dataset = _setup(n_cases=3)
        resp = await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        run_id = body["run_id"]

        detail = (await client.get(f"/api/runs/{run_id}")).json()
        assert detail["run"]["status"] == "completed"
        assert len(detail["cases"]) == 3
        assert all(c["output"] == "hello world" for c in detail["cases"])

    async def test_422_when_dataset_missing_template_variable(self, client, tmp_db) -> None:
        prompt = models.create_prompt("P")
        version = models.create_prompt_version(prompt["id"], "Needs {{missing_var}}", model="claude-haiku-4-5")
        dataset = models.create_dataset("D")
        models.create_test_case(dataset["id"], {"other": "x"})

        resp = await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})
        assert resp.status_code == 422
        assert "missing_var" in resp.json()["detail"]

    async def test_404_for_missing_prompt_version(self, client, tmp_db) -> None:
        dataset = models.create_dataset("D")
        resp = await client.post("/api/runs", json={"prompt_version_id": 999999, "dataset_id": dataset["id"]})
        assert resp.status_code == 404

    async def test_404_for_missing_dataset(self, client, tmp_db) -> None:
        prompt = models.create_prompt("P")
        version = models.create_prompt_version(prompt["id"], "hi", model="claude-haiku-4-5")
        resp = await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": 999999})
        assert resp.status_code == 404

    async def test_grader_snapshot_taken_at_launch_time(self, client, tmp_db, fake_llm) -> None:
        prompt, version, dataset = _setup(n_cases=1)
        models.create_grader(prompt["id"], "string_match", "sm", {"must_contain": ["hello"], "case_sensitive": False})
        resp = await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})
        run_id = resp.json()["run_id"]
        detail = (await client.get(f"/api/runs/{run_id}")).json()
        assert detail["cases"][0]["grades"][0]["grader_name"] == "sm"
        assert detail["cases"][0]["final_score"] == 10.0

    async def test_concurrency_clamped_to_max_20(self, client, tmp_db, fake_llm) -> None:
        _, version, dataset = _setup(n_cases=1)
        resp = await client.post(
            "/api/runs",
            json={"prompt_version_id": version["id"], "dataset_id": dataset["id"], "concurrency": 999},
        )
        run_id = resp.json()["run_id"]
        run_row = models.get_run(run_id)
        assert run_row["concurrency"] == 20


class TestListAndDetail:
    async def test_list_runs(self, client, tmp_db, fake_llm) -> None:
        _, version, dataset = _setup(n_cases=1)
        await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})
        await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})
        resp = await client.get("/api/runs")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_filter_by_dataset_id(self, client, tmp_db, fake_llm) -> None:
        _, version, dataset = _setup(n_cases=1)
        _, version2, dataset2 = _setup(n_cases=1)
        await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})
        await client.post("/api/runs", json={"prompt_version_id": version2["id"], "dataset_id": dataset2["id"]})
        resp = await client.get(f"/api/runs?dataset_id={dataset['id']}")
        body = resp.json()
        assert len(body) == 1
        assert body[0]["dataset_id"] == dataset["id"]

    async def test_404_for_missing_run(self, client, tmp_db) -> None:
        resp = await client.get("/api/runs/999999")
        assert resp.status_code == 404

    async def test_tolerates_deleted_dataset_and_prompt(self, client, tmp_db, fake_llm) -> None:
        prompt, version, dataset = _setup(n_cases=1)
        resp = await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})
        run_id = resp.json()["run_id"]

        models.delete_prompt(prompt["id"])  # cascades prompt_version too
        models.delete_dataset(dataset["id"])  # cascades test_case too

        detail_resp = await client.get(f"/api/runs/{run_id}")
        assert detail_resp.status_code == 200
        body = detail_resp.json()
        assert body["run"]["prompt_name"] == "(deleted prompt)"
        assert body["run"]["dataset_name"] == "(deleted dataset)"
        assert len(body["cases"]) == 1
        assert body["cases"][0]["test_case"]["id"] == body["cases"][0]["test_case_id"]


class TestCancelAndDelete:
    async def test_cancel_returns_202(self, client, tmp_db) -> None:
        prompt = models.create_prompt("P")
        version = models.create_prompt_version(prompt["id"], "hi", model="claude-haiku-4-5")
        dataset = models.create_dataset("D")
        run = models.create_run(
            version["id"], dataset["id"], model="claude-haiku-4-5", temperature=0.0, max_tokens=100,
            judge_model="claude-sonnet-5", concurrency=5, grader_snapshot=[], status="pending",
        )
        resp = await client.post(f"/api/runs/{run['id']}/cancel")
        assert resp.status_code == 202
        assert resp.json()["status"] == "cancelled"

    async def test_cancel_404_for_missing_run(self, client, tmp_db) -> None:
        resp = await client.post("/api/runs/999999/cancel")
        assert resp.status_code == 404

    async def test_delete_run(self, client, tmp_db, fake_llm) -> None:
        _, version, dataset = _setup(n_cases=1)
        run_id = (await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})).json()["run_id"]
        resp = await client.delete(f"/api/runs/{run_id}")
        assert resp.status_code == 204
        assert (await client.get(f"/api/runs/{run_id}")).status_code == 404

    async def test_delete_404_for_missing_run(self, client, tmp_db) -> None:
        resp = await client.delete("/api/runs/999999")
        assert resp.status_code == 404


class TestCompare:
    async def test_compare_400_when_datasets_differ(self, client, tmp_db, fake_llm) -> None:
        _, version_a, dataset_a = _setup(n_cases=1)
        _, version_b, dataset_b = _setup(n_cases=1)
        run_a = (await client.post("/api/runs", json={"prompt_version_id": version_a["id"], "dataset_id": dataset_a["id"]})).json()["run_id"]
        run_b = (await client.post("/api/runs", json={"prompt_version_id": version_b["id"], "dataset_id": dataset_b["id"]})).json()["run_id"]
        resp = await client.get(f"/api/runs/compare?a={run_a}&b={run_b}")
        assert resp.status_code == 400

    async def test_compare_succeeds_on_same_dataset(self, client, tmp_db, fake_llm) -> None:
        prompt, version, dataset = _setup(n_cases=2)
        version2 = models.create_prompt_version(prompt["id"], "Echo v2: {{x}}", model="claude-haiku-4-5")
        run_a = (await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})).json()["run_id"]
        run_b = (await client.post("/api/runs", json={"prompt_version_id": version2["id"], "dataset_id": dataset["id"]})).json()["run_id"]

        resp = await client.get(f"/api/runs/compare?a={run_a}&b={run_b}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["a"]["run"]["id"] == run_a
        assert body["b"]["run"]["id"] == run_b
        assert len(body["cases"]) == 2
        assert body["wins"]["a"] + body["wins"]["b"] + body["wins"]["tie"] == 2

    async def test_compare_case_present_only_on_one_side(self, client, tmp_db, fake_llm) -> None:
        # Dataset extended with a new case AFTER run A launched but BEFORE run B --
        # so run B has a case (and thus a RunCase/score) that run A never saw at all.
        prompt, version, dataset = _setup(n_cases=1)
        models.create_grader(prompt["id"], "string_match", "sm", {"must_contain": ["hello"]})
        run_a = (await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})).json()["run_id"]

        extra_case = models.create_test_case(dataset["id"], {"x": "extra"})
        run_b = (await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})).json()["run_id"]

        resp = await client.get(f"/api/runs/compare?a={run_a}&b={run_b}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["cases"]) == 2  # the union of both runs' cases

        extra_row = next(c for c in body["cases"] if c["test_case"]["id"] == extra_case["id"])
        assert extra_row["a"] is None  # run A never had this case
        assert extra_row["b"] is not None
        assert extra_row["winner"] == "b"  # only b has a score, so b "wins" this case
        # Every case present in the response must resolve to exactly one of the three
        # winner buckets, and total wins must equal total cases.
        assert body["wins"]["a"] + body["wins"]["b"] + body["wins"]["tie"] == 2

    async def test_compare_case_present_but_a_ungraded_treated_as_b_win(self, client, tmp_db) -> None:
        # A case present in BOTH runs (same run_case row exists in each), but run A's
        # only grader (llm_judge) raised -> that grade is "failed" -> excluded from
        # the weighted average -> run A's final_score is None for this case, even
        # though the RunCase itself isn't null. Compare must treat "no score" the
        # same as "no case" for winner/delta purposes: b wins outright.
        prompt = models.create_prompt("P")
        version = models.create_prompt_version(prompt["id"], "Echo: {{x}}", model="claude-haiku-4-5")
        dataset = models.create_dataset("D")
        tc = models.create_test_case(dataset["id"], {"x": "1"})

        from backend.app.eval import runner

        fake_a = FakeLLM(default_response="hello world")
        fake_a.queue_response("hello world")  # main model completion call succeeds
        fake_a.queue_failure(RuntimeError("judge exploded"))  # then the judge call fails
        run_a = models.create_run(
            version["id"], dataset["id"], model="claude-haiku-4-5", temperature=0.0, max_tokens=100,
            judge_model="claude-sonnet-5", concurrency=5,
            grader_snapshot=[{"name": "judge", "type": "llm_judge", "weight": 1, "config": {"rubric": "r"}, "enabled": True}],
            status="pending",
        )
        await runner.run_evaluation(run_a["id"], fake_a)

        fake_b = FakeLLM(default_response="hello world")
        fake_b.queue_response("hello world")  # main model completion call
        fake_b.queue_response(json.dumps({"strengths": [], "weaknesses": [], "reasoning": "ok", "score": 7}))  # judge call
        run_b = models.create_run(
            version["id"], dataset["id"], model="claude-haiku-4-5", temperature=0.0, max_tokens=100,
            judge_model="claude-sonnet-5", concurrency=5,
            grader_snapshot=[{"name": "judge", "type": "llm_judge", "weight": 1, "config": {"rubric": "r"}, "enabled": True}],
            status="pending",
        )
        await runner.run_evaluation(run_b["id"], fake_b)

        resp = await client.get(f"/api/runs/compare?a={run_a['id']}&b={run_b['id']}")
        assert resp.status_code == 200
        body = resp.json()
        row = body["cases"][0]
        assert row["test_case"]["id"] == tc["id"]
        assert row["a"] is not None  # the RunCase row exists in both runs...
        assert row["a"]["final_score"] is None  # ...but a's only grader failed -> no score
        assert row["b"]["final_score"] == 7.0
        assert row["winner"] == "b"
        assert row["delta"] == -7.0

    async def test_compare_404_when_run_missing(self, client, tmp_db, fake_llm) -> None:
        _, version, dataset = _setup(n_cases=1)
        run_a = (await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})).json()["run_id"]
        resp = await client.get(f"/api/runs/compare?a={run_a}&b=999999")
        assert resp.status_code == 404


class TestSSE:
    async def test_headers_and_terminal_event_for_already_finished_run(self, client, tmp_db, fake_llm) -> None:
        _, version, dataset = _setup(n_cases=1)
        run_id = (await client.post("/api/runs", json={"prompt_version_id": version["id"], "dataset_id": dataset["id"]})).json()["run_id"]

        async with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            assert resp.headers["cache-control"] == "no-cache"
            assert resp.headers["x-accel-buffering"] == "no"
            chunks = []
            async for chunk in resp.aiter_text():
                chunks.append(chunk)
            text = "".join(chunks)

        assert "event: run_completed" in text
        assert '"run_id": ' + str(run_id) in text or f'"run_id":{run_id}' in text

    async def test_404_events_for_missing_run(self, client, tmp_db) -> None:
        resp = await client.get("/api/runs/999999/events")
        assert resp.status_code == 404

    async def test_client_disconnect_mid_stream_unsubscribes_no_leak(self, tmp_db) -> None:
        # If a browser tab navigates away or the client just stops reading mid-run,
        # the SSE generator's `finally: EVENT_BUS.unsubscribe(...)` must still run --
        # otherwise every abandoned SSE connection leaves a queue subscribed forever
        # (a slow, unbounded memory leak for a long-lived local server).
        from backend.app.eval import runner as runner_mod

        prompt = models.create_prompt("P")
        version = models.create_prompt_version(prompt["id"], "Echo: {{x}}", model="claude-haiku-4-5")
        dataset = models.create_dataset("D")
        for i in range(6):
            models.create_test_case(dataset["id"], {"x": str(i)})

        class SlowFakeLLM(FakeLLM):
            async def complete(self, *args, **kwargs):
                await asyncio.sleep(0.05)
                return await super().complete(*args, **kwargs)

        fake = SlowFakeLLM(default_response="ok")
        app = _make_app(fake)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            post_task = asyncio.create_task(
                client.post(
                    "/api/runs",
                    json={"prompt_version_id": version["id"], "dataset_id": dataset["id"], "concurrency": 1},
                )
            )

            run_id = None
            for _ in range(100):
                rows = models.list_runs()
                if rows:
                    run_id = rows[0]["id"]
                    break
                await asyncio.sleep(0.01)
            assert run_id is not None

            for _ in range(100):
                if models.get_run(run_id)["status"] == "running":
                    break
                await asyncio.sleep(0.005)

            # Open the stream, read exactly one chunk, then close the connection --
            # simulating a client that goes away mid-run instead of reading to
            # completion.
            async with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
                assert resp.status_code == 200
                async for _chunk in resp.aiter_bytes():
                    break  # abandon the stream after the first chunk

            # The abandoned connection's queue must be cleaned up promptly (allow a
            # short grace period for the ASGI layer to propagate the disconnect).
            for _ in range(100):
                if run_id not in runner_mod.EVENT_BUS._subscribers:
                    break
                await asyncio.sleep(0.01)
            assert run_id not in runner_mod.EVENT_BUS._subscribers, (
                "SSE subscriber queue was not cleaned up after client disconnect"
            )

            await post_task  # let the background run finish before the test ends

    async def test_live_run_streams_events_in_order_and_late_subscriber_catches_up(self, tmp_db) -> None:
        prompt = models.create_prompt("P")
        version = models.create_prompt_version(prompt["id"], "Echo: {{x}}", model="claude-haiku-4-5")
        dataset = models.create_dataset("D")
        for i in range(4):
            models.create_test_case(dataset["id"], {"x": str(i)})

        class SlowFakeLLM(FakeLLM):
            async def complete(self, *args, **kwargs):
                await asyncio.sleep(0.05)
                return await super().complete(*args, **kwargs)

        fake = SlowFakeLLM(default_response="ok")
        app = _make_app(fake)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            post_task = asyncio.create_task(
                client.post(
                    "/api/runs",
                    json={"prompt_version_id": version["id"], "dataset_id": dataset["id"], "concurrency": 1},
                )
            )

            # Poll for the run row to appear (POST won't return until the whole run,
            # including the background task, finishes -- see module note).
            run_id = None
            for _ in range(100):
                rows = models.list_runs()
                if rows:
                    run_id = rows[0]["id"]
                    break
                await asyncio.sleep(0.01)
            assert run_id is not None

            # Wait until it's actually running (at least one event published) before
            # attaching -- this is the "late subscriber" scenario.
            for _ in range(100):
                if models.get_run(run_id)["status"] == "running":
                    break
                await asyncio.sleep(0.005)

            events: list[str] = []
            async with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
                assert resp.status_code == 200
                buf = ""
                async for chunk in resp.aiter_text():
                    buf += chunk
                    while "\n\n" in buf:
                        raw, buf = buf.split("\n\n", 1)
                        for line in raw.splitlines():
                            if line.startswith("event:"):
                                events.append(line.split(":", 1)[1].strip())

            await post_task  # ensure the background run has fully finished

        assert events, "expected at least one event"
        assert events[-1] == "run_completed"
        # A late subscriber must not see duplicate terminal events / hang.
        assert events.count("run_completed") == 1
