"""Shared grader interface.

Every grader type (``llm_judge``, ``code_syntax``, ``string_match``, ``json_schema``,
``budget``) implements :class:`Grader`. The runner never calls a subclass's
:meth:`Grader.grade` directly -- it calls :meth:`Grader.run`, which wraps ``grade`` in
a try/except so a grader that raises marks ITSELF ``failed`` (via :meth:`GradeResult.failed`)
instead of propagating and aborting the case or the run (see ``docs/PLAN.md`` / the
eval-core task spec).

A grader can resolve to one of three outcomes, tracked by :attr:`GradeResult.status`:

- ``"scored"``  -- a real 0-10 score that participates in the weighted average.
- ``"skipped"`` -- the grader had nothing to check (e.g. ``code_syntax: auto`` with no
  ``expected_format`` on the test case, or ``string_match`` with zero constraints
  configured). Excluded from the weighted average, not counted as a 0.
- ``"failed"``  -- the grader itself blew up (bad config, LLM error, malformed judge
  JSON after retries, ...). Also excluded from the weighted average. The case itself
  still completes; only this grader's contribution is dropped.

``status`` is persisted in the stored ``grade.details_json`` under the reserved key
``"_status"`` (see :func:`status_from_details` / :meth:`GradeResult.with_status_detail`)
since the ``grade`` DB row / API ``Grade`` shape has no dedicated status column --
:mod:`..scoring` reads it back from there to decide inclusion in the weighted average.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from ...llm import LLMClient

GraderStatus = Literal["scored", "skipped", "failed"]

STATUS_DETAIL_KEY = "_status"


@dataclass
class GradeContext:
    """Everything a grader needs to evaluate one (test case, model output) pair.

    ``test_case`` is the plain dict shape from :mod:`...models` (``inputs``,
    ``solution_criteria``, ``category``, ``expected_format``). ``config`` is this
    grader's resolved config dict, taken from the run's ``grader_snapshot`` (never a
    live ``grader`` row -- see DATA_MODEL invariant 2). ``llm``/``judge_model`` are
    used only by the ``llm_judge`` grader; other graders ignore them.
    """

    test_case: dict[str, Any]
    output: str
    config: dict[str, Any]
    llm: LLMClient
    judge_model: str
    latency_ms: int | None = None
    cost: float | None = None
    output_tokens: int | None = None
    input_tokens: int | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GradeResult:
    """The outcome of one grader running against one case.

    ``score`` is always a float in ``[0, 10]`` (required by the ``grade`` DB column /
    API ``Grade`` shape), but is meaningless -- and must be ignored by aggregation --
    when ``status`` isn't ``"scored"``; skip/fail results conventionally carry ``0.0``.
    """

    score: float
    reasoning: str
    details: dict[str, Any] = field(default_factory=dict)
    status: GraderStatus = "scored"

    @classmethod
    def scored(cls, score: float, reasoning: str, details: dict[str, Any] | None = None) -> "GradeResult":
        clamped = max(0.0, min(10.0, score))
        return cls(score=clamped, reasoning=reasoning, details=details or {}, status="scored")

    @classmethod
    def skip(cls, reasoning: str, details: dict[str, Any] | None = None) -> "GradeResult":
        return cls(score=0.0, reasoning=reasoning, details=details or {}, status="skipped")

    @classmethod
    def failed(cls, reasoning: str, details: dict[str, Any] | None = None) -> "GradeResult":
        return cls(score=0.0, reasoning=reasoning, details=details or {}, status="failed")

    def details_with_status(self) -> dict[str, Any]:
        """``details`` with :data:`STATUS_DETAIL_KEY` merged in, for DB persistence."""
        return {**self.details, STATUS_DETAIL_KEY: self.status}


def status_from_details(details: dict[str, Any] | None) -> GraderStatus:
    """Read a persisted grade's status back out of its ``details`` dict.

    Missing key defaults to ``"scored"`` -- forward-compatible with any grade row that
    predates this convention (there are none yet, since this ships in the same phase,
    but it keeps the reader total rather than partial).
    """
    if not details:
        return "scored"
    status = details.get(STATUS_DETAIL_KEY, "scored")
    if status not in ("scored", "skipped", "failed"):
        return "scored"
    return status  # type: ignore[return-value]


class Grader(ABC):
    """Base class for all grader types. Subclasses implement :meth:`grade`."""

    type: str

    @abstractmethod
    async def grade(self, ctx: GradeContext) -> GradeResult:
        """Evaluate ``ctx`` and return a :class:`GradeResult`.

        May raise -- callers MUST use :meth:`run`, not this method directly, unless
        they intend to handle exceptions themselves.
        """
        raise NotImplementedError

    async def run(self, ctx: GradeContext) -> GradeResult:
        """Run :meth:`grade`, converting any exception into a ``failed`` result.

        This is the entry point the runner uses. It guarantees a grader can never
        crash the case or the run it participates in.
        """
        try:
            return await self.grade(ctx)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: grader isolation
            return GradeResult.failed(f"{type(self).__name__} raised: {exc}")


GRADER_REGISTRY: dict[str, Grader] = {}


def register(grader: Grader) -> Grader:
    """Register a grader instance under its ``type`` in :data:`GRADER_REGISTRY`."""
    GRADER_REGISTRY[grader.type] = grader
    return grader
