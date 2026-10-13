"""Headless evaluations using the same launch validation, runner, and report as HTTP."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from . import db, models
from .config import settings
from .eval import runner
from .eval.scoring import compute_passed
from .llm import AnthropicLLM, LLMClient
from .routers.runs import get_run_detail, prepare_run
from .schemas import RunCreate


def _bounded_float(value: str, maximum: float) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= maximum:
        raise argparse.ArgumentTypeError(f"must be between 0 and {maximum}")
    return number


def _resolve(value: str, rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matches = [r for r in rows if str(r["id"]) == value] if value.isdecimal() else [r for r in rows if r["name"] == value]
    if not matches:
        raise ValueError(f"{kind} {value!r} not found.")
    if len(matches) > 1:
        raise ValueError(f"{kind} name {value!r} is ambiguous; use an id.")
    return matches[0]


async def _run(args: argparse.Namespace, llm: LLMClient | None) -> int:
    prompt = _resolve(args.prompt, models.list_prompts(), "Prompt")
    dataset = _resolve(args.dataset, models.list_datasets(), "Dataset")
    versions = models.list_prompt_versions(prompt["id"])
    version = next((v for v in versions if v["version_no"] == args.version), None) if args.version is not None else max(versions, key=lambda v: v["version_no"], default=None)
    if version is None:
        raise ValueError("Prompt version not found.")
    if not models.list_test_cases(dataset["id"]):
        raise ValueError("Dataset has no cases.")
    client = llm if llm is not None else AnthropicLLM(api_key=settings.anthropic_api_key)
    run = prepare_run(RunCreate(prompt_version_id=version["id"], dataset_id=dataset["id"]))
    await runner.run_evaluation(run["id"], client)
    report = get_run_detail(run["id"]).model_dump(mode="json")
    if args.json_report:
        Path(args.json_report).write_text(json.dumps(report, indent=2) + "\n")
    stats = report["stats"]
    avg, rate = stats["avg_score"], stats["pass_rate"]
    avg_text = f"{avg:.2f}/10" if avg is not None else "unscored"
    rate_text = f"{rate:.1%}" if rate is not None else "unavailable"
    print(f"Run #{run['id']} {report['run']['status']}: average {avg_text}, pass rate {rate_text}")
    for category, values in sorted(stats["by_category"].items()):
        print(f"  {category}: {values['avg_score']:.2f} ({values['count']} cases)")
    failed_cases = [c for c in report["cases"] if c["status"] == "failed" or c["passed"] is not True or any(g["details"].get("_status") == "failed" for g in c["grades"])]
    print(f"Failed or inconclusive cases: {len(failed_cases)}")
    for case in failed_cases:
        print(f"  Case #{case['idx'] + 1} (test case {case['test_case_id']}): {case['error'] or 'grader failed or gating verdict unavailable'}")
    if report["run"]["error"]:
        print(report["run"]["error"], file=sys.stderr)
    execution_failed = any(
        c["passed"] is None
        or any(g["details"].get("_status") == "failed" for g in c["grades"])
        or (c["status"] == "failed" and compute_passed(c["grades"]) is not False)
        for c in failed_cases
    )
    failed = report["run"]["status"] != "completed" or execution_failed
    if args.fail_under is not None and (avg is None or avg < args.fail_under):
        print(f"Average below required {args.fail_under:.2f}.", file=sys.stderr)
        failed = True
    if args.require_pass_rate is not None and (rate is None or rate < args.require_pass_rate):
        print(f"Pass rate below required {args.require_pass_rate:.1%}.", file=sys.stderr)
        failed = True
    return 1 if failed else 0


def main(argv: list[str] | None = None, *, llm: LLMClient | None = None) -> int:
    """Return 0 on success, 1 on evaluation failure, or 2 on invalid input/setup."""
    parser = argparse.ArgumentParser(prog="promptlab")
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="Evaluate a saved prompt against a saved dataset")
    run.add_argument("--prompt", required=True)
    run.add_argument("--version", type=int)
    run.add_argument("--dataset", required=True)
    run.add_argument("--fail-under", type=lambda v: _bounded_float(v, 10.0))
    run.add_argument("--require-pass-rate", type=lambda v: _bounded_float(v, 1.0), default=1.0)
    run.add_argument("--json", dest="json_report")
    args = parser.parse_args(argv)
    try:
        db.init_db()
        return asyncio.run(_run(args, llm))
    except HTTPException as exc:
        print(f"promptlab: {exc.detail}", file=sys.stderr)
    except (ValueError, OSError) as exc:
        print(f"promptlab: {exc}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
