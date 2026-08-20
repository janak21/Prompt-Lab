"""The concurrent run engine.

:func:`run_evaluation` is the single entry point, launched as a FastAPI background
task by ``routers/runs.py``. It:

1. Resolves the prompt version + dataset + test cases for the run (a genuinely global
   failure here -- e.g. the prompt version vanished between validation and launch --
   marks the whole run ``failed``; this should be rare since the router validates
   existence before creating the run).
2. Creates a ``run_case`` row per test case up front (status ``pending``), so the UI
   can show the full case list immediately.
3. Runs cases concurrently, bounded by an ``asyncio.Semaphore`` sized from
   ``run.concurrency``. For each case: render the prompt, call the model, then run
   every grader in ``run.grader_snapshot_json`` (NEVER live ``grader`` rows -- DATA_MODEL
   invariant 2) against that case's output.
4. Isolates failures per case: a render error, an LLM error surviving
   :class:`AnthropicLLM`'s internal retries, or a grader exploding, marks only that
   ``run_case`` ``failed`` -- it never aborts the run or other in-flight cases.
5. Persists incrementally: each ``run_case`` and its ``grade`` rows are written via
   ``models`` as soon as that case finishes, so a page refresh mid-run shows real
   progress (not just at the very end).
6. Publishes progress over :data:`EVENT_BUS`, an in-process per-run pub/sub that the
   SSE router subscribes to (see :class:`RunEventBus`).
7. Supports cooperative cancellation via :func:`cancel_run`: cases already running are
   allowed to finish (and are graded normally); cases that haven't started yet are
   skipped (left ``pending``); the run's terminal status becomes ``cancelled``.

Write-lock discipline: every ``models``/``db`` write already goes through
``db.connection(write=True)``, which itself is a short, synchronous, non-async-holding
critical section (see ``db.py``'s docstring) -- so nothing here holds that lock across
an ``await`` on the network; each write call is a self-contained synchronous op.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .. import models, templating
from ..llm import LLMClient
from .graders import GRADER_REGISTRY
from .graders.base import GradeContext
from .scoring import build_run_stats, compute_final_score

TERMINAL_EVENTS = {"run_completed", "run_failed", "cancelled"}
OUTPUT_PREVIEW_LEN = 240


class RunEventBus:
    """In-process pub/sub for one run's SSE stream.

    Each run gets its own fanout: any number of subscribers may attach concurrently
    (each gets an independent :class:`asyncio.Queue`), a subscriber attaching after the
    run has already emitted events immediately receives the most recent event first (so
    a late subscriber sees current state before live events resume), and a subscriber
    that disconnects unsubscribes itself (via the router's ``finally``), which removes
    its queue so nothing leaks.
    """

    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue[tuple[str, dict[str, Any]]]]] = {}
        self._last_event: dict[int, tuple[str, dict[str, Any]]] = {}

    def subscribe(self, run_id: int) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        """Attach a new subscriber queue for ``run_id``."""
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._subscribers.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: int, queue: asyncio.Queue[tuple[str, dict[str, Any]]]) -> None:
        """Detach ``queue`` from ``run_id``. Safe to call more than once."""
        subs = self._subscribers.get(run_id)
        if not subs:
            return
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(run_id, None)

    def last_event(self, run_id: int) -> tuple[str, dict[str, Any]] | None:
        """The most recently published event for ``run_id``, if any."""
        return self._last_event.get(run_id)

    async def publish(self, run_id: int, event: str, data: dict[str, Any]) -> None:
        """Publish ``event``/``data`` to every current subscriber of ``run_id``.

        Also records it as the "last event" so a subscriber attaching later can catch
        up immediately (see :meth:`last_event`).
        """
        self._last_event[run_id] = (event, data)
        for queue in list(self._subscribers.get(run_id, [])):
            await queue.put((event, data))

    def forget(self, run_id: int) -> None:
        """Drop all bookkeeping for a run (called once it reaches a terminal state and
        has no more subscribers to catch up, e.g. on delete)."""
        self._subscribers.pop(run_id, None)
        self._last_event.pop(run_id, None)


EVENT_BUS = RunEventBus()

_cancelled_runs: set[int] = set()


def cancel_run(run_id: int) -> None:
    """Cooperatively request cancellation of a running evaluation.

    Sets an in-process flag :func:`run_evaluation` checks before starting each new
    case. Idempotent; safe to call even if the run has already finished (a no-op then).
    """
    _cancelled_runs.add(run_id)


def is_cancelled(run_id: int) -> bool:
    return run_id in _cancelled_runs


def clear_cancelled(run_id: int) -> None:
    """Drop ``run_id`` from the cancellation set (e.g. after the run is deleted)."""
    _cancelled_runs.discard(run_id)


def _output_preview(output: str | None) -> str | None:
    if output is None:
        return None
    return output[:OUTPUT_PREVIEW_LEN]


async def _grade_case(
    run_case_id: int,
    test_case: dict[str, Any],
    output: str,
    grader_snapshot: list[dict[str, Any]],
    llm: LLMClient,
    judge_model: str,
    latency_ms: int | None,
    cost: float | None,
    output_tokens: int | None,
    input_tokens: int | None,
) -> list[dict[str, Any]]:
    """Run every enabled grader in ``grader_snapshot`` against one case's output.

    Persists a ``grade`` row per grader (even skipped/failed ones, so the UI can show
    why) and returns the enriched grade dicts (with ``details`` including the reserved
    ``_status`` key) for scoring / SSE payload use.
    """
    persisted: list[dict[str, Any]] = []
    for grader_def in grader_snapshot:
        if not grader_def.get("enabled", True):
            continue
        grader_type = grader_def["type"]
        grader = GRADER_REGISTRY.get(grader_type)
        weight = grader_def.get("weight", 1.0)
        name = grader_def.get("name", grader_type)
        if grader is None:
            row = models.create_grade(
                run_case_id, name, grader_type, 0.0, weight,
                reasoning=f"Unknown grader type: {grader_type!r}",
                details={"_status": "failed"},
            )
            persisted.append(row)
            continue

        ctx = GradeContext(
            test_case=test_case,
            output=output,
            config=grader_def.get("config") or {},
            llm=llm,
            judge_model=judge_model,
            latency_ms=latency_ms,
            cost=cost,
            output_tokens=output_tokens,
            input_tokens=input_tokens,
        )
        result = await grader.run(ctx)
        row = models.create_grade(
            run_case_id,
            name,
            grader_type,
            result.score,
            weight,
            reasoning=result.reasoning,
            details=result.details_with_status(),
        )
        persisted.append(row)
    return persisted


async def _process_case(
    *,
    run: dict[str, Any],
    prompt_version: dict[str, Any],
    test_case: dict[str, Any],
    idx: int,
    run_case_id: int,
    semaphore: asyncio.Semaphore,
    llm: LLMClient,
    progress: dict[str, Any],
    progress_lock: asyncio.Lock,
) -> None:
    run_id = run["id"]

    if is_cancelled(run_id):
        return

    async with semaphore:
        if is_cancelled(run_id):
            return

        models.update_run_case(run_case_id, status="running")
        await EVENT_BUS.publish(
            run_id, "case_started",
            {"run_case_id": run_case_id, "test_case_id": test_case["id"], "idx": idx},
        )

        try:
            rendered = templating.render(prompt_version["template"], test_case.get("inputs") or {})
        except Exception as exc:  # noqa: BLE001 - case isolation
            models.update_run_case(run_case_id, status="failed", error=str(exc), rendered_prompt=None)
            await EVENT_BUS.publish(run_id, "case_failed", {"run_case_id": run_case_id, "idx": idx, "error": str(exc)})
            await _bump_progress(run_id, progress, progress_lock, failed=True)
            return

        models.update_run_case(run_case_id, rendered_prompt=rendered)

        messages = [{"role": "user", "content": rendered}]
        try:
            result = await llm.complete(
                messages,
                model=run["model"],
                system=prompt_version.get("system_prompt"),
                temperature=run["temperature"],
                max_tokens=run["max_tokens"],
            )
        except Exception as exc:  # noqa: BLE001 - case isolation (retries already exhausted)
            models.update_run_case(run_case_id, status="failed", error=str(exc))
            await EVENT_BUS.publish(run_id, "case_failed", {"run_case_id": run_case_id, "idx": idx, "error": str(exc)})
            await _bump_progress(run_id, progress, progress_lock, failed=True)
            return

        models.update_run_case(
            run_case_id,
            output=result.text,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost=result.cost_usd,
        )

        try:
            grades = await _grade_case(
                run_case_id,
                test_case,
                result.text,
                run["grader_snapshot"],
                llm,
                run["judge_model"],
                result.latency_ms,
                result.cost_usd,
                result.output_tokens,
                result.input_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - case isolation; grading must not kill the case
            models.update_run_case(run_case_id, status="failed", error=f"Grading failed: {exc}")
            await EVENT_BUS.publish(run_id, "case_failed", {"run_case_id": run_case_id, "idx": idx, "error": str(exc)})
            await _bump_progress(run_id, progress, progress_lock, failed=True)
            return

        final_score = compute_final_score(grades)
        models.update_run_case(run_case_id, final_score=final_score, status="completed")

        await EVENT_BUS.publish(
            run_id,
            "case_completed",
            {
                "run_case_id": run_case_id,
                "test_case_id": test_case["id"],
                "idx": idx,
                "final_score": final_score,
                "latency_ms": result.latency_ms,
                "cost": result.cost_usd,
                "status": "completed",
                "output_preview": _output_preview(result.text),
                "grades": [_grade_to_event_shape(g) for g in grades],
            },
        )
        await _bump_progress(run_id, progress, progress_lock, completed=True, score=final_score)


def _grade_to_event_shape(grade: dict[str, Any]) -> dict[str, Any]:
    return {
        "grader_name": grade["grader_name"],
        "grader_type": grade["grader_type"],
        "score": grade["score"],
        "weight": grade["weight"],
        "reasoning": grade.get("reasoning"),
        "details": grade.get("details") or {},
    }


async def _bump_progress(
    run_id: int,
    progress: dict[str, Any],
    lock: asyncio.Lock,
    *,
    completed: bool = False,
    failed: bool = False,
    score: float | None = None,
) -> None:
    async with lock:
        if completed:
            progress["completed"] += 1
            if score is not None:
                progress["score_sum"] += score
                progress["scored_count"] += 1
        if failed:
            progress["failed"] += 1
        avg_score_so_far = (
            progress["score_sum"] / progress["scored_count"] if progress["scored_count"] > 0 else None
        )
        payload = {
            "completed": progress["completed"],
            "failed": progress["failed"],
            "total": progress["total"],
            "avg_score_so_far": avg_score_so_far,
        }
    await EVENT_BUS.publish(run_id, "progress", payload)


async def run_evaluation(run_id: int, llm: LLMClient) -> None:
    """Execute a run end-to-end. Intended to be launched as a background task.

    Never raises for a per-case problem -- see the module docstring. Only a genuinely
    global setup error (missing prompt version / dataset at launch time, or an
    unexpected exception outside the per-case try/excepts) marks the run itself
    ``failed``.
    """
    try:
        run = models.get_run(run_id)
        if run is None:
            return

        prompt_version = models.get_prompt_version(run["prompt_version_id"])
        if prompt_version is None:
            models.update_run(run_id, status="failed", error="Prompt version no longer exists.", finished_at=_now())
            await EVENT_BUS.publish(run_id, "run_failed", {"run_id": run_id, "error": "Prompt version no longer exists."})
            return

        test_cases = models.list_test_cases(run["dataset_id"])

        run_case_rows = [
            models.create_run_case(run_id, tc["id"], idx) for idx, tc in enumerate(test_cases)
        ]

        started_at = _now()
        models.update_run(run_id, status="running", started_at=started_at)
        await EVENT_BUS.publish(run_id, "run_started", {"run_id": run_id, "total": len(test_cases)})

        concurrency = max(1, min(20, run["concurrency"]))
        semaphore = asyncio.Semaphore(concurrency)
        progress = {"completed": 0, "failed": 0, "total": len(test_cases), "score_sum": 0.0, "scored_count": 0}
        progress_lock = asyncio.Lock()

        tasks = [
            asyncio.create_task(
                _process_case(
                    run=run,
                    prompt_version=prompt_version,
                    test_case=tc,
                    idx=idx,
                    run_case_id=case_row["id"],
                    semaphore=semaphore,
                    llm=llm,
                    progress=progress,
                    progress_lock=progress_lock,
                )
            )
            for idx, (tc, case_row) in enumerate(zip(test_cases, run_case_rows))
        ]
        if tasks:
            await asyncio.gather(*tasks)

        finished_at = _now()
        cancelled = is_cancelled(run_id)

        final_run_cases = models.list_run_cases(run_id)
        for rc in final_run_cases:
            rc["grades"] = models.list_grades(rc["id"])
            rc["test_case"] = models.get_test_case(rc["test_case_id"]) or {}
        stats = build_run_stats(final_run_cases)

        if cancelled:
            models.update_run(
                run_id, status="cancelled", finished_at=finished_at,
                avg_score=stats["avg_score"], total_cost=stats["total_cost"],
            )
            await EVENT_BUS.publish(run_id, "cancelled", {"run_id": run_id})
        else:
            models.update_run(
                run_id, status="completed", finished_at=finished_at,
                avg_score=stats["avg_score"], total_cost=stats["total_cost"],
            )
            await EVENT_BUS.publish(
                run_id,
                "run_completed",
                {
                    "run_id": run_id,
                    "avg_score": stats["avg_score"],
                    "total_cost": stats["total_cost"],
                    "completed": stats["completed"],
                    "failed": stats["failed"],
                },
            )
    except Exception as exc:  # noqa: BLE001 - genuinely global failure
        try:
            models.update_run(run_id, status="failed", error=str(exc), finished_at=_now())
        except Exception:  # noqa: BLE001 - best-effort; don't mask the original error
            pass
        await EVENT_BUS.publish(run_id, "run_failed", {"run_id": run_id, "error": str(exc)})
    finally:
        _cancelled_runs.discard(run_id)


def _now() -> str:
    return models.utcnow_iso()
