"""Tests for backend.app.eval.scoring."""

from __future__ import annotations

import pytest

from backend.app.eval.scoring import build_run_stats, compute_final_score


def _grade(score: float, weight: float, status: str = "scored", **details) -> dict:
    return {"grader_name": "g", "grader_type": "string_match", "score": score, "weight": weight, "details": {"_status": status, **details}}


class TestComputeFinalScore:
    def test_weighted_average(self) -> None:
        grades = [_grade(8, 1), _grade(4, 1)]
        assert compute_final_score(grades) == 6.0

    def test_weights_matter(self) -> None:
        grades = [_grade(10, 3), _grade(0, 1)]
        assert compute_final_score(grades) == 7.5

    def test_skipped_excluded_from_numerator_and_denominator(self) -> None:
        # Worked example from the module docstring.
        grades = [_grade(8, 1), _grade(6, 2), _grade(0, 1, status="skipped")]
        result = compute_final_score(grades)
        assert result == 20 / 3
        assert result != 5.0  # the naive "count skip as 0" answer

    def test_failed_excluded(self) -> None:
        grades = [_grade(9, 1), _grade(0, 5, status="failed")]
        assert compute_final_score(grades) == 9.0

    def test_all_skipped_or_failed_returns_none(self) -> None:
        grades = [_grade(0, 1, status="skipped"), _grade(0, 1, status="failed")]
        assert compute_final_score(grades) is None

    def test_no_grades_returns_none(self) -> None:
        assert compute_final_score([]) is None

    def test_clamped_to_0_10(self) -> None:
        grades = [_grade(20, 1)]  # a buggy grader emitting out-of-range score
        assert compute_final_score(grades) == 10.0

    def test_zero_weight_grade_excluded(self) -> None:
        grades = [_grade(8, 1), _grade(100, 0)]
        assert compute_final_score(grades) == 8.0


def _case(
    *,
    status: str = "completed",
    final_score: float | None = None,
    cost: float = 0.0,
    latency_ms: int = 0,
    grades: list[dict] | None = None,
    category: str | None = "standard",
) -> dict:
    return {
        "status": status,
        "final_score": final_score,
        "cost": cost,
        "latency_ms": latency_ms,
        "grades": grades or [],
        "test_case": {"category": category},
    }


class TestBuildRunStats:
    def test_empty(self) -> None:
        stats = build_run_stats([])
        assert stats["avg_score"] is None
        assert stats["total"] == 0
        assert stats["distribution"] == [0] * 10

    def test_counts(self) -> None:
        cases = [_case(status="completed", final_score=8), _case(status="failed", final_score=None)]
        stats = build_run_stats(cases)
        assert stats["total"] == 2
        assert stats["completed"] == 1
        assert stats["failed"] == 1

    def test_avg_score_only_over_non_none(self) -> None:
        cases = [_case(final_score=10), _case(final_score=None, status="failed")]
        stats = build_run_stats(cases)
        assert stats["avg_score"] == 10.0

    def test_avg_score_is_none_when_every_case_fails(self) -> None:
        cases = [_case(final_score=None, status="failed"), _case(final_score=None, status="failed")]
        stats = build_run_stats(cases)
        assert stats["avg_score"] is None
        assert stats["total"] == 2
        assert stats["failed"] == 2
        assert stats["distribution"] == [0] * 10

    def test_total_cost_and_latency_sum(self) -> None:
        cases = [_case(cost=0.1, latency_ms=100), _case(cost=0.2, latency_ms=200)]
        stats = build_run_stats(cases)
        assert stats["total_cost"] == pytest.approx(0.3)
        assert stats["total_latency_ms"] == 300

    def test_by_grader_averages_and_weight(self) -> None:
        cases = [
            _case(final_score=8, grades=[_grade(8, 2)]),
            _case(final_score=4, grades=[_grade(4, 2)]),
        ]
        stats = build_run_stats(cases)
        assert stats["by_grader"]["g"]["avg_score"] == 6.0
        assert stats["by_grader"]["g"]["weight"] == 2

    def test_by_grader_excludes_skipped_occurrences(self) -> None:
        cases = [
            _case(final_score=8, grades=[_grade(8, 1)]),
            _case(final_score=None, grades=[_grade(0, 1, status="skipped")]),
        ]
        stats = build_run_stats(cases)
        assert stats["by_grader"]["g"]["avg_score"] == 8.0

    def test_by_category(self) -> None:
        cases = [
            _case(final_score=8, category="standard"),
            _case(final_score=4, category="standard"),
            _case(final_score=10, category="adversarial"),
        ]
        stats = build_run_stats(cases)
        assert stats["by_category"]["standard"]["avg_score"] == 6.0
        assert stats["by_category"]["standard"]["count"] == 2
        assert stats["by_category"]["adversarial"]["count"] == 1

    def test_uncategorized_fallback(self) -> None:
        cases = [_case(final_score=5, category=None)]
        stats = build_run_stats(cases)
        assert stats["by_category"]["uncategorized"]["count"] == 1

    def test_by_category_single_case(self) -> None:
        cases = [_case(final_score=7, category="only_one")]
        stats = build_run_stats(cases)
        assert stats["by_category"] == {"only_one": {"avg_score": 7.0, "count": 1}}

    def test_by_category_excludes_categories_with_zero_scored_cases(self) -> None:
        # A category whose only case failed (final_score None) contributes nothing --
        # it must not appear in by_category at all (not even as 0/None).
        cases = [
            _case(final_score=8, category="standard"),
            _case(final_score=None, status="failed", category="all_failed"),
        ]
        stats = build_run_stats(cases)
        assert "all_failed" not in stats["by_category"]
        assert stats["by_category"]["standard"]["count"] == 1

    def test_by_grader_absent_when_no_scored_grades_at_all(self) -> None:
        cases = [_case(final_score=None, grades=[_grade(0, 1, status="failed")])]
        stats = build_run_stats(cases)
        assert stats["by_grader"] == {}

    def test_distribution_ten_buckets(self) -> None:
        stats = build_run_stats([])
        assert len(stats["distribution"]) == 10

    def test_distribution_bucketing_and_ten_lands_in_last_bucket(self) -> None:
        cases = [
            _case(final_score=0.0),
            _case(final_score=0.99),
            _case(final_score=5.5),
            _case(final_score=9.99),
            _case(final_score=10.0),
        ]
        stats = build_run_stats(cases)
        dist = stats["distribution"]
        assert dist[0] == 2  # 0.0 and 0.99 both in bucket [0,1)
        assert dist[5] == 1  # 5.5 in bucket [5,6)
        assert dist[9] == 2  # 9.99 and 10.0 both in the closed top bucket [9,10]
        assert sum(dist) == 5
