"""``/api/runs*`` endpoints -- launching, listing, inspecting, cancelling, deleting,
comparing, and streaming live progress for evaluation runs.

Registering this router on the app is another agent's job (``main.py``) -- this module
only needs to expose ``router``.

Route ordering note: ``GET /api/runs/compare`` is registered *before*
``GET /api/runs/{run_id}`` deliberately -- FastAPI matches path operations in
registration order, and ``{run_id}: int`` would otherwise structurally match
``/runs/compare`` first and fail int-parsing ``"compare"`` with a 422 instead of ever
reaching the compare handler.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from .. import models, templating
from ..config import settings
from ..eval import runner
from ..eval.scoring import build_run_stats
from ..llm import AnthropicLLM, LLMClient
from ..schemas import (
    CategoryStat,
    CompareCase,
    CompareDeltas,
    CompareSideResponse,
    CompareWins,
    Grade,
    GraderStat,
    RunCancelResponse,
    RunCase,
    RunCompareResponse,
    RunCreate,
    RunCreateResponse,
    RunDetailResponse,
    RunStats,
    RunSummary,
    TestCase,
)

router = APIRouter(prefix="/api", tags=["runs"])


# --------------------------------------------------------------------------
# LLM client dependency -- overridable in tests (dependency_overrides), defaults to
# the real Anthropic-backed client. Never constructed at import time.
# --------------------------------------------------------------------------


def get_llm_client() -> LLMClient:
    """FastAPI dependency yielding the LLM client used to execute runs.

    Tests should override this (``app.dependency_overrides[get_llm_client] = lambda:
    fake_llm``) to inject :class:`backend.app.llm.FakeLLM` and guarantee no real
    network call is ever made.
    """
    return AnthropicLLM(api_key=settings.anthropic_api_key)


# --------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------


def _placeholder_test_case(test_case_id: int, dataset_id: int) -> dict[str, Any]:
    """A best-effort stand-in ``TestCase`` for a run_case whose parent test_case row
    was deleted (dataset deleted) -- keeps run-detail/compare endpoints from 500ing,
    per DATA_MODEL invariant 5."""
    return {
        "id": test_case_id,
        "dataset_id": dataset_id,
        "inputs": {},
        "solution_criteria": None,
        "category": None,
        "expected_format": None,
        "created_at": "",
    }


def _build_run_summary(run: dict[str, Any]) -> RunSummary:
    prompt_version = models.get_prompt_version(run["prompt_version_id"])
    prompt = models.get_prompt(prompt_version["prompt_id"]) if prompt_version else None
    dataset = models.get_dataset(run["dataset_id"])
    cases = models.list_run_cases(run["id"])
    completed = sum(1 for c in cases if c["status"] == "completed")
    failed = sum(1 for c in cases if c["status"] == "failed")
    return RunSummary(
        id=run["id"],
        prompt_id=prompt_version["prompt_id"] if prompt_version else 0,
        prompt_name=prompt["name"] if prompt else "(deleted prompt)",
        prompt_version_id=run["prompt_version_id"],
        version_no=prompt_version["version_no"] if prompt_version else 0,
        dataset_id=run["dataset_id"],
        dataset_name=dataset["name"] if dataset else "(deleted dataset)",
        model=run["model"],
        judge_model=run["judge_model"],
        temperature=run["temperature"],
        status=run["status"],
        avg_score=run["avg_score"],
        pass_rate=build_run_stats(cases)["pass_rate"],
        total_cost=run["total_cost"],
        total=len(cases),
        completed=completed,
        failed=failed,
        started_at=run["started_at"],
        finished_at=run["finished_at"],
        created_at=run["created_at"],
        error=run["error"],
    )


def _load_case_dicts(run_id: int) -> list[dict[str, Any]]:
    """Every run_case for ``run_id``, enriched with ``grades`` and ``test_case``
    (falling back to a placeholder if the parent test_case/dataset was deleted)."""
    run = models.get_run(run_id)
    dataset_id = run["dataset_id"] if run else 0
    rows = models.list_run_cases(run_id)
    out: list[dict[str, Any]] = []
    for row in rows:
        rc = dict(row)
        rc["grades"] = models.list_grades(rc["id"])
        test_case = models.get_test_case(rc["test_case_id"])
        rc["test_case"] = test_case if test_case is not None else _placeholder_test_case(rc["test_case_id"], dataset_id)
        out.append(rc)
    return out


def _case_to_pydantic(rc: dict[str, Any]) -> RunCase:
    return RunCase(
        id=rc["id"],
        run_id=rc["run_id"],
        test_case_id=rc["test_case_id"],
        idx=rc["idx"],
        rendered_prompt=rc.get("rendered_prompt"),
        output=rc.get("output"),
        latency_ms=rc.get("latency_ms"),
        input_tokens=rc.get("input_tokens"),
        output_tokens=rc.get("output_tokens"),
        cost=rc.get("cost"),
        final_score=rc.get("final_score"),
        passed=rc.get("passed"),
        transcript=rc.get("transcript", []),
        tool_calls=rc.get("tool_calls", []),
        status=rc["status"],
        error=rc.get("error"),
        grades=[
            Grade(
                grader_name=g["grader_name"],
                grader_type=g["grader_type"],
                score=g["score"],
                weight=g["weight"],
                reasoning=g.get("reasoning"),
                details=g.get("details") or {},
            )
            for g in rc.get("grades", [])
        ],
        test_case=TestCase(**rc["test_case"]),
    )


def _stats_to_pydantic(stats: dict[str, Any]) -> RunStats:
    return RunStats(
        avg_score=stats["avg_score"],
        pass_rate=stats["pass_rate"],
        total_cost=stats["total_cost"],
        total_latency_ms=stats["total_latency_ms"],
        total=stats["total"],
        completed=stats["completed"],
        failed=stats["failed"],
        by_grader={k: GraderStat(**v) for k, v in stats["by_grader"].items()},
        by_category={k: CategoryStat(**v) for k, v in stats["by_category"].items()},
        distribution=stats["distribution"],
    )


def prepare_run(body: RunCreate) -> dict[str, Any]:
    """Validate launch settings and snapshot graders for both HTTP and the CLI."""
    prompt_version = models.get_prompt_version(body.prompt_version_id)
    if prompt_version is None:
        raise HTTPException(status_code=404, detail=f"Prompt version {body.prompt_version_id} not found.")
    dataset = models.get_dataset(body.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail=f"Dataset {body.dataset_id} not found.")

    test_cases = models.list_test_cases(body.dataset_id)
    dataset_vars: set[str] = set()
    for tc in test_cases:
        dataset_vars.update((tc.get("inputs") or {}).keys())
    required_vars = templating.extract_variables(prompt_version["template"])
    missing = [v for v in required_vars if v not in dataset_vars]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Dataset is missing template variable(s): {', '.join(sorted(missing))}",
        )

    model = body.model or prompt_version.get("model") or settings.default_model
    temperature = (
        body.temperature
        if body.temperature is not None
        else (prompt_version.get("temperature") if prompt_version.get("temperature") is not None else 1.0)
    )
    max_tokens = (
        body.max_tokens
        if body.max_tokens is not None
        else (prompt_version.get("max_tokens") if prompt_version.get("max_tokens") is not None else 1024)
    )
    judge_model = body.judge_model or settings.default_judge_model
    concurrency = body.concurrency if body.concurrency is not None else settings.default_concurrency
    concurrency = max(1, min(settings.max_concurrency, concurrency))

    graders = [g for g in models.list_graders(prompt_version["prompt_id"]) if g["enabled"]]
    grader_snapshot = [
        {"name": g["name"], "type": g["type"], "weight": g["weight"], "config": g["config"], "enabled": True, "gating": g["gating"], "pass_threshold": g["pass_threshold"]}
        for g in graders
    ]

    run = models.create_run(
        body.prompt_version_id,
        body.dataset_id,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        judge_model=judge_model,
        concurrency=concurrency,
        grader_snapshot=grader_snapshot,
        status="pending",
        tools_snapshot=dataset["tools"],
    )

    return run


# --------------------------------------------------------------------------
# POST /api/runs
# --------------------------------------------------------------------------


@router.post("/runs", status_code=202, response_model=RunCreateResponse)
async def create_run(
    body: RunCreate,
    background_tasks: BackgroundTasks,
    llm: LLMClient = Depends(get_llm_client),
) -> RunCreateResponse:
    """Launch a new evaluation run. Execution happens in a background task; the
    client is expected to immediately open the SSE stream at
    ``GET /api/runs/{id}/events`` to watch progress."""
    run = prepare_run(body)

    background_tasks.add_task(runner.run_evaluation, run["id"], llm)

    return RunCreateResponse(run_id=run["id"], status="pending")


# --------------------------------------------------------------------------
# GET /api/runs
# --------------------------------------------------------------------------


@router.get("/runs", response_model=list[RunSummary])
def list_runs(prompt_id: int | None = None, dataset_id: int | None = None, limit: int | None = None) -> list[RunSummary]:
    rows = models.list_runs(prompt_id=prompt_id, dataset_id=dataset_id, limit=limit)
    return [_build_run_summary(r) for r in rows]


# --------------------------------------------------------------------------
# GET /api/runs/compare  (MUST be registered before /runs/{run_id} -- see module docstring)
# --------------------------------------------------------------------------


@router.get("/runs/compare", response_model=RunCompareResponse)
def compare_runs(a: int, b: int) -> RunCompareResponse:
    run_a = models.get_run(a)
    run_b = models.get_run(b)
    if run_a is None or run_b is None:
        raise HTTPException(status_code=404, detail="One or both runs were not found.")
    if run_a["dataset_id"] != run_b["dataset_id"]:
        raise HTTPException(status_code=400, detail="The two runs used different datasets; cannot compare.")

    cases_a = _load_case_dicts(a)
    cases_b = _load_case_dicts(b)
    stats_a = build_run_stats(cases_a)
    stats_b = build_run_stats(cases_b)

    avg_a, avg_b = stats_a["avg_score"], stats_b["avg_score"]
    avg_delta = (avg_a - avg_b) if avg_a is not None and avg_b is not None else 0.0
    cost_delta = stats_a["total_cost"] - stats_b["total_cost"]

    by_grader_delta: dict[str, float] = {}
    for name in set(stats_a["by_grader"]) | set(stats_b["by_grader"]):
        av = stats_a["by_grader"].get(name, {}).get("avg_score")
        bv = stats_b["by_grader"].get(name, {}).get("avg_score")
        if av is not None and bv is not None:
            by_grader_delta[name] = av - bv

    by_category_delta: dict[str, float] = {}
    for cat in set(stats_a["by_category"]) | set(stats_b["by_category"]):
        av = stats_a["by_category"].get(cat, {}).get("avg_score")
        bv = stats_b["by_category"].get(cat, {}).get("avg_score")
        if av is not None and bv is not None:
            by_category_delta[cat] = av - bv

    by_tc_a = {c["test_case_id"]: c for c in cases_a}
    by_tc_b = {c["test_case_id"]: c for c in cases_b}
    all_ids = set(by_tc_a) | set(by_tc_b)
    ordered_ids = sorted(all_ids, key=lambda tid: (by_tc_a.get(tid) or by_tc_b[tid])["idx"])

    compare_cases: list[CompareCase] = []
    wins = {"a": 0, "b": 0, "tie": 0}
    for tid in ordered_ids:
        ca = by_tc_a.get(tid)
        cb = by_tc_b.get(tid)
        test_case_dict = (ca or cb)["test_case"]  # type: ignore[index]
        score_a = ca["final_score"] if ca else None
        score_b = cb["final_score"] if cb else None
        if score_a is not None and score_b is not None:
            delta = score_a - score_b
            winner = "a" if delta > 0 else ("b" if delta < 0 else "tie")
        elif score_a is not None:
            delta, winner = score_a, "a"
        elif score_b is not None:
            delta, winner = -score_b, "b"
        else:
            delta, winner = 0.0, "tie"
        wins[winner] += 1
        compare_cases.append(
            CompareCase(
                test_case=TestCase(**test_case_dict),
                a=_case_to_pydantic(ca) if ca else None,
                b=_case_to_pydantic(cb) if cb else None,
                winner=winner,  # type: ignore[arg-type]
                delta=delta,
            )
        )

    return RunCompareResponse(
        a=CompareSideResponse(run=_build_run_summary(run_a), stats=_stats_to_pydantic(stats_a)),
        b=CompareSideResponse(run=_build_run_summary(run_b), stats=_stats_to_pydantic(stats_b)),
        deltas=CompareDeltas(pass_rate=(stats_a["pass_rate"] - stats_b["pass_rate"]) if stats_a["pass_rate"] is not None and stats_b["pass_rate"] is not None else None, avg_score=avg_delta, total_cost=cost_delta, by_grader=by_grader_delta, by_category=by_category_delta),
        cases=compare_cases,
        wins=CompareWins(**wins),
    )


# --------------------------------------------------------------------------
# GET /api/runs/{run_id}
# --------------------------------------------------------------------------


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run_detail(run_id: int) -> RunDetailResponse:
    run = models.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    case_dicts = _load_case_dicts(run_id)
    stats = build_run_stats(case_dicts)
    return RunDetailResponse(
        run=_build_run_summary(run),
        stats=_stats_to_pydantic(stats),
        cases=[_case_to_pydantic(c) for c in case_dicts],
    )


# --------------------------------------------------------------------------
# POST /api/runs/{run_id}/cancel
# --------------------------------------------------------------------------


@router.post("/runs/{run_id}/cancel", status_code=202, response_model=RunCancelResponse)
def cancel_run_endpoint(run_id: int) -> RunCancelResponse:
    run = models.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run["status"] in ("pending", "running"):
        runner.cancel_run(run_id)
    return RunCancelResponse(status="cancelled")


# --------------------------------------------------------------------------
# GET /api/runs/{run_id}/events  (SSE)
# --------------------------------------------------------------------------


def _sse_bytes(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def _terminal_event_for_run(run: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    cases = models.list_run_cases(run["id"])
    completed = sum(1 for c in cases if c["status"] == "completed")
    failed = sum(1 for c in cases if c["status"] == "failed")
    if run["status"] == "cancelled":
        return "cancelled", {"run_id": run["id"]}
    if run["status"] == "failed":
        return "run_failed", {"run_id": run["id"], "error": run.get("error") or "Run failed."}
    return "run_completed", {
        "run_id": run["id"],
        "avg_score": run.get("avg_score"),
        "pass_rate": build_run_stats(cases)["pass_rate"],
        "total_cost": run.get("total_cost") or 0.0,
        "completed": completed,
        "failed": failed,
    }


async def _event_stream(run_id: int) -> AsyncIterator[bytes]:
    run = models.get_run(run_id)
    if run is None:
        return

    if run["status"] in ("completed", "failed", "cancelled"):
        event, data = _terminal_event_for_run(run)
        yield _sse_bytes(event, data)
        return

    queue = runner.EVENT_BUS.subscribe(run_id)
    try:
        last = runner.EVENT_BUS.last_event(run_id)
        if last is not None:
            event, data = last
            yield _sse_bytes(event, data)
            if event in runner.TERMINAL_EVENTS:
                return
        while True:
            try:
                event, data = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield b": ping\n\n"
                continue
            yield _sse_bytes(event, data)
            if event in runner.TERMINAL_EVENTS:
                return
    finally:
        runner.EVENT_BUS.unsubscribe(run_id, queue)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: int) -> StreamingResponse:
    run = models.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return StreamingResponse(
        _event_stream(run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------
# DELETE /api/runs/{run_id}
# --------------------------------------------------------------------------


@router.delete("/runs/{run_id}", status_code=204)
def delete_run_endpoint(run_id: int) -> Response:
    run = models.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    models.delete_run(run_id)
    runner.EVENT_BUS.forget(run_id)
    runner.clear_cancelled(run_id)
    return Response(status_code=204)
