"""Tests for backend.app.eval.runner -- concurrency, per-case isolation, cancellation,
the grader-snapshot-not-live rule, and the RunEventBus pub/sub. FakeLLM only, no
network calls."""

from __future__ import annotations

import asyncio

import pytest

from backend.app import models
from backend.app.eval import runner
from backend.app.eval.runner import RunEventBus
from backend.app.llm import FakeLLM


def _setup_prompt_and_dataset(template: str = "Echo: {{x}}", n_cases: int = 3, inputs_fn=None):
    prompt = models.create_prompt("P")
    version = models.create_prompt_version(prompt["id"], template, model="claude-haiku-4-5", temperature=0.0, max_tokens=100)
    dataset = models.create_dataset("D")
    cases = []
    for i in range(n_cases):
        inputs = inputs_fn(i) if inputs_fn else {"x": str(i)}
        cases.append(models.create_test_case(dataset["id"], inputs))
    return prompt, version, dataset, cases


def _create_run(version, dataset, *, grader_snapshot=None, concurrency=5, model="claude-haiku-4-5"):
    return models.create_run(
        version["id"], dataset["id"],
        model=model, temperature=0.0, max_tokens=100,
        judge_model="claude-sonnet-5", concurrency=concurrency,
        grader_snapshot=grader_snapshot or [], status="pending",
    )


class TestBasicRun:
    async def test_completes_and_persists_incrementally(self, tmp_db) -> None:
        _, version, dataset, cases = _setup_prompt_and_dataset(n_cases=3)
        run = _create_run(version, dataset)
        fake = FakeLLM(default_response="hello")

        await runner.run_evaluation(run["id"], fake)

        updated = models.get_run(run["id"])
        assert updated["status"] == "completed"
        assert updated["finished_at"] is not None

        run_cases = models.list_run_cases(run["id"])
        assert len(run_cases) == 3
        assert all(rc["status"] == "completed" for rc in run_cases)
        assert all(rc["output"] == "hello" for rc in run_cases)
        # No graders configured -> no grades -> final_score is None, not 0.
        assert all(rc["final_score"] is None for rc in run_cases)

    async def test_missing_prompt_version_fails_run_globally(self, tmp_db) -> None:
        dataset = models.create_dataset("D")
        run = models.create_run(
            999999, dataset["id"], model="claude-haiku-4-5", temperature=0.0, max_tokens=100,
            judge_model="claude-sonnet-5", concurrency=5, grader_snapshot=[], status="pending",
        )
        fake = FakeLLM()
        await runner.run_evaluation(run["id"], fake)
        updated = models.get_run(run["id"])
        assert updated["status"] == "failed"
        assert updated["error"]


class TestSnapshotNotLive:
    async def test_runner_reads_snapshot_never_live_grader_rows(self, tmp_db) -> None:
        prompt, version, dataset, cases = _setup_prompt_and_dataset(n_cases=1)
        # A live grader row exists on the prompt...
        models.create_grader(prompt["id"], "string_match", "live-grader", {"must_contain": ["hello"], "case_sensitive": False})
        # ...but the run's snapshot is different (empty).
        run = _create_run(version, dataset, grader_snapshot=[])
        fake = FakeLLM(default_response="hello")

        await runner.run_evaluation(run["id"], fake)

        run_cases = models.list_run_cases(run["id"])
        grades = models.list_grades(run_cases[0]["id"])
        assert grades == []  # the live grader must NOT have been applied

    async def test_runner_applies_snapshot_graders(self, tmp_db) -> None:
        prompt, version, dataset, cases = _setup_prompt_and_dataset(n_cases=1)
        snapshot = [{"name": "sm", "type": "string_match", "weight": 1.0, "config": {"must_contain": ["hello"], "case_sensitive": False}, "enabled": True}]
        run = _create_run(version, dataset, grader_snapshot=snapshot)
        fake = FakeLLM(default_response="hello world")

        await runner.run_evaluation(run["id"], fake)

        run_cases = models.list_run_cases(run["id"])
        grades = models.list_grades(run_cases[0]["id"])
        assert len(grades) == 1
        assert grades[0]["score"] == 10.0
        assert run_cases[0]["final_score"] == 10.0


class TestCaseIsolation:
    async def test_render_error_isolated_to_one_case(self, tmp_db) -> None:
        # Case 1 is missing the "x" variable the template needs.
        def inputs_fn(i: int) -> dict:
            return {"x": str(i)} if i != 1 else {"wrong_key": "oops"}

        _, version, dataset, cases = _setup_prompt_and_dataset(n_cases=3, inputs_fn=inputs_fn)
        run = _create_run(version, dataset)
        fake = FakeLLM(default_response="ok")

        await runner.run_evaluation(run["id"], fake)

        run_cases = {rc["idx"]: rc for rc in models.list_run_cases(run["id"])}
        assert run_cases[0]["status"] == "completed"
        assert run_cases[1]["status"] == "failed"
        assert run_cases[1]["error"]
        assert run_cases[2]["status"] == "completed"
        # The run as a whole still completes -- one bad case doesn't abort it.
        assert models.get_run(run["id"])["status"] == "completed"

    async def test_llm_error_isolated_to_one_case(self, tmp_db) -> None:
        _, version, dataset, cases = _setup_prompt_and_dataset(n_cases=3)
        run = _create_run(version, dataset)
        fake = FakeLLM(default_response="ok")
        # First call succeeds, second fails, third succeeds (queue is FIFO but cases
        # run concurrently -- use call_count-independent approach: queue one failure,
        # rest succeed via default_response).
        fake.queue_failure(RuntimeError("upstream exploded"))

        await runner.run_evaluation(run["id"], fake)

        run_cases = models.list_run_cases(run["id"])
        statuses = [rc["status"] for rc in run_cases]
        assert statuses.count("failed") == 1
        assert statuses.count("completed") == 2
        assert models.get_run(run["id"])["status"] == "completed"

    async def test_grader_exception_isolated_case_still_completes(self, tmp_db) -> None:
        _, version, dataset, cases = _setup_prompt_and_dataset(n_cases=1)
        # json_schema grader with no "schema" key in config -> grade() raises/fails.
        snapshot = [{"name": "bad-schema", "type": "json_schema", "weight": 1.0, "config": {}, "enabled": True}]
        run = _create_run(version, dataset, grader_snapshot=snapshot)
        fake = FakeLLM(default_response="output")

        await runner.run_evaluation(run["id"], fake)

        run_cases = models.list_run_cases(run["id"])
        assert run_cases[0]["status"] == "completed"
        grades = models.list_grades(run_cases[0]["id"])
        assert len(grades) == 1
        assert run_cases[0]["final_score"] is None  # only grader present failed -> excluded


class TestConcurrency:
    async def test_respects_semaphore_bound(self, tmp_db) -> None:
        _, version, dataset, cases = _setup_prompt_and_dataset(n_cases=6)
        run = _create_run(version, dataset, concurrency=2)

        current = 0
        peak = 0
        lock = asyncio.Lock()

        class SlowFakeLLM(FakeLLM):
            async def complete(self, *args, **kwargs):
                nonlocal current, peak
                async with lock:
                    current += 1
                    peak = max(peak, current)
                await asyncio.sleep(0.02)
                result = await super().complete(*args, **kwargs)
                async with lock:
                    current -= 1
                return result

        fake = SlowFakeLLM(default_response="ok")
        await runner.run_evaluation(run["id"], fake)

        assert peak <= 2
        assert models.get_run(run["id"])["status"] == "completed"


class TestCancellation:
    async def test_cancel_marks_run_cancelled_and_no_orphan_state(self, tmp_db) -> None:
        _, version, dataset, cases = _setup_prompt_and_dataset(n_cases=8)
        run = _create_run(version, dataset, concurrency=2)

        class SlowFakeLLM(FakeLLM):
            async def complete(self, *args, **kwargs):
                await asyncio.sleep(0.03)
                return await super().complete(*args, **kwargs)

        fake = SlowFakeLLM(default_response="ok")

        task = asyncio.create_task(runner.run_evaluation(run["id"], fake))
        await asyncio.sleep(0.01)
        runner.cancel_run(run["id"])
        await task

        updated = models.get_run(run["id"])
        assert updated["status"] == "cancelled"
        assert not runner.is_cancelled(run["id"])  # cleaned up after the run ends

        run_cases = models.list_run_cases(run["id"])
        # Not every case need have started -- but none should be left "running".
        assert all(rc["status"] in ("pending", "completed", "failed") for rc in run_cases)

    async def test_cancel_before_start_leaves_all_cases_pending(self, tmp_db) -> None:
        _, version, dataset, cases = _setup_prompt_and_dataset(n_cases=3)
        run = _create_run(version, dataset)
        runner.cancel_run(run["id"])
        fake = FakeLLM(default_response="ok")

        await runner.run_evaluation(run["id"], fake)

        updated = models.get_run(run["id"])
        assert updated["status"] == "cancelled"
        run_cases = models.list_run_cases(run["id"])
        assert all(rc["status"] == "pending" for rc in run_cases)


class TestRunEventBus:
    async def test_late_subscriber_gets_last_event_first(self) -> None:
        bus = RunEventBus()
        await bus.publish(1, "run_started", {"run_id": 1, "total": 2})
        await bus.publish(1, "progress", {"completed": 1, "failed": 0, "total": 2, "avg_score_so_far": 5.0})

        queue = bus.subscribe(1)
        last = bus.last_event(1)
        assert last == ("progress", {"completed": 1, "failed": 0, "total": 2, "avg_score_so_far": 5.0})

        await bus.publish(1, "case_completed", {"foo": "bar"})
        event, data = await asyncio.wait_for(queue.get(), timeout=1)
        assert event == "case_completed"

    async def test_multiple_concurrent_subscribers_each_get_events(self) -> None:
        bus = RunEventBus()
        q1 = bus.subscribe(2)
        q2 = bus.subscribe(2)
        await bus.publish(2, "run_started", {"run_id": 2, "total": 1})
        e1 = await asyncio.wait_for(q1.get(), timeout=1)
        e2 = await asyncio.wait_for(q2.get(), timeout=1)
        assert e1 == e2 == ("run_started", {"run_id": 2, "total": 1})

    async def test_unsubscribe_removes_queue_no_leak(self) -> None:
        bus = RunEventBus()
        q = bus.subscribe(3)
        assert len(bus._subscribers[3]) == 1
        bus.unsubscribe(3, q)
        assert 3 not in bus._subscribers  # cleaned up entirely once empty

    async def test_unsubscribe_is_safe_to_call_twice(self) -> None:
        bus = RunEventBus()
        q = bus.subscribe(4)
        bus.unsubscribe(4, q)
        bus.unsubscribe(4, q)  # must not raise
