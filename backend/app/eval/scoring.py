"""Weighted scoring and run-level statistics aggregation.

Per DATA_MODEL.md invariant 3::

    run_case.final_score = sum(grade.score * grade.weight) / sum(grade.weight), 0-10

with the extension (this phase's job to define) that **skipped and failed graders are
excluded from both the numerator and the denominator** -- they contribute nothing, as
if they had never run, rather than being counted as a zero. If every grader for a case
is skipped or failed, ``final_score`` is ``None`` (the case still completes).

Worked example
---------------
A case has three enabled graders: ``string_match`` (weight 1, scores 8), ``llm_judge``
(weight 2, scores 6), and ``code_syntax`` (weight 1, configured ``auto`` but the test
case has no ``expected_format`` -> SKIPPED). The skipped grader drops out entirely:

    final_score = (8*1 + 6*2) / (1 + 2) = 20 / 3 = 6.666...

not ``(8*1 + 6*2 + 0*1) / (1 + 2 + 1) = 20/4 = 5.0`` -- the skip must not silently drag
the average down as if it had scored zero.

Distribution bucket-edge rule
------------------------------
:func:`build_run_stats`'s ``distribution`` has exactly 10 buckets, labelled (by index)
``0-1, 1-2, ..., 8-9, 9-10``. A score is clamped to ``[0, 10]`` (scores are already
supposed to be in this range, but this is defence in depth) and bucketed by
``min(9, floor(score))`` -- i.e. each bucket ``[n, n+1)`` is half-open on the right,
**except** the final bucket ``[9, 10]`` is closed on both ends so a perfect ``10.0``
lands in the top bucket (index 9) rather than overflowing past it.
"""

from __future__ import annotations

from typing import Any

from .graders.base import status_from_details

_SCORED_STATUS = "scored"


def _grade_status(grade: dict[str, Any]) -> str:
    return status_from_details(grade.get("details"))


def compute_final_score(grades: list[dict[str, Any]]) -> float | None:
    """Compute a case's weighted-average ``final_score`` from its persisted grades.

    ``grades`` is a list of dicts shaped like the ``grade`` DB row (``score``,
    ``weight``, ``details`` with the reserved ``_status`` key -- see
    :mod:`.graders.base`). Skipped/failed grades are excluded from numerator and
    denominator. Returns ``None`` if there are no grades, or every grade is
    skipped/failed (total weight is zero). The result is clamped to ``[0, 10]``.
    """
    numerator = 0.0
    denominator = 0.0
    for grade in grades:
        if _grade_status(grade) != _SCORED_STATUS:
            continue
        weight = grade.get("weight", 0.0) or 0.0
        if weight <= 0:
            continue
        numerator += grade["score"] * weight
        denominator += weight

    if denominator <= 0:
        return None
    return max(0.0, min(10.0, numerator / denominator))


def compute_passed(grades: list[dict[str, Any]]) -> bool | None:
    """Evaluate gates independently of weights; an unscored gate is inconclusive.

    Deterministic graders require every constraint (score 10); llm_judge uses its
    snapshotted threshold. No gates means a successfully executed case passes.
    """
    gates = [g for g in grades if (g.get("details") or {}).get("_gating", False)]
    for grade in gates:
        details = grade.get("details") or {}
        threshold = details.get("_pass_threshold", 8.0) if grade["grader_type"] == "llm_judge" else 10.0
        if _grade_status(grade) == _SCORED_STATUS and grade["score"] < threshold:
            return False
    if any(_grade_status(g) != _SCORED_STATUS for g in gates):
        return None
    return True


def _bucket_index(score: float) -> int:
    clamped = max(0.0, min(10.0, score))
    return min(9, int(clamped))


def build_run_stats(run_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the ``RunStats`` payload (see API_CONTRACT.md) from a run's cases.

    ``run_cases`` is a list of dicts, each shaped like the enriched ``RunCase`` API
    object: at minimum ``status``, ``final_score``, ``cost``, ``latency_ms``,
    ``grades`` (list of grade dicts as in :func:`compute_final_score`), and
    ``test_case`` (dict with a ``category`` key, possibly ``None``/missing if the
    parent dataset was deleted).

    - ``by_grader``: average score + configured weight per grader NAME, over cases
      where that grader was ``scored`` (skipped/failed occurrences of that grader on
      other cases don't pull its average down). ``weight`` is that grader's configured
      weight (identical across cases within one run, since it's snapshotted once).
    - ``by_category``: average ``final_score`` + case count per test-case category,
      over cases that have a non-``None`` ``final_score`` (i.e. completed with at
      least one scored grader). A case whose category is ``None``/missing is grouped
      under the key ``"uncategorized"``.
    - ``distribution``: see the module docstring for the bucket-edge rule.
    """
    total = len(run_cases)
    completed = sum(1 for c in run_cases if c.get("status") == "completed")
    failed = sum(1 for c in run_cases if c.get("status") == "failed")

    total_cost = sum(c.get("cost") or 0.0 for c in run_cases)
    total_latency_ms = sum(c.get("latency_ms") or 0 for c in run_cases)

    final_scores = [c["final_score"] for c in run_cases if c.get("final_score") is not None]
    avg_score = sum(final_scores) / len(final_scores) if final_scores else None

    distribution = [0] * 10
    for score in final_scores:
        distribution[_bucket_index(score)] += 1

    grader_sums: dict[str, float] = {}
    grader_counts: dict[str, int] = {}
    grader_weights: dict[str, float] = {}
    for case in run_cases:
        for grade in case.get("grades", []):
            if _grade_status(grade) != _SCORED_STATUS:
                continue
            name = grade["grader_name"]
            grader_sums[name] = grader_sums.get(name, 0.0) + grade["score"]
            grader_counts[name] = grader_counts.get(name, 0) + 1
            grader_weights[name] = grade["weight"]

    by_grader = {
        name: {"avg_score": grader_sums[name] / grader_counts[name], "weight": grader_weights[name]}
        for name in grader_sums
    }

    category_sums: dict[str, float] = {}
    category_counts: dict[str, int] = {}
    for case in run_cases:
        if case.get("final_score") is None:
            continue
        test_case = case.get("test_case") or {}
        category = test_case.get("category") or "uncategorized"
        category_sums[category] = category_sums.get(category, 0.0) + case["final_score"]
        category_counts[category] = category_counts.get(category, 0) + 1

    by_category = {
        category: {"avg_score": category_sums[category] / category_counts[category], "count": category_counts[category]}
        for category in category_sums
    }

    return {
        "avg_score": avg_score,
        "pass_rate": sum(bool(c.get("passed", c.get("status") == "completed")) for c in run_cases) / total if total else None,
        "total_cost": total_cost,
        "total_latency_ms": total_latency_ms,
        "total": total,
        "completed": completed,
        "failed": failed,
        "by_grader": by_grader,
        "by_category": by_category,
        "distribution": distribution,
    }
