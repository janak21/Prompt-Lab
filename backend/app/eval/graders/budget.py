"""``budget`` grader: scores 10 if every SET ceiling holds, else 0.

Unset ceilings (``None``) are ignored entirely. If all three ceilings
(``max_latency_ms``, ``max_cost_usd``, ``max_output_tokens``) are unset, the grader is
SKIPPED -- there is nothing configured to enforce.
"""

from __future__ import annotations

from .base import GradeContext, GradeResult, Grader, register


class BudgetGrader(Grader):
    type = "budget"

    async def grade(self, ctx: GradeContext) -> GradeResult:
        config = ctx.config
        max_latency_ms = config.get("max_latency_ms")
        max_cost_usd = config.get("max_cost_usd")
        max_output_tokens = config.get("max_output_tokens")

        if max_latency_ms is None and max_cost_usd is None and max_output_tokens is None:
            return GradeResult.skip("No budget ceilings configured.")

        checks: list[tuple[str, bool, str]] = []

        if max_latency_ms is not None:
            actual = ctx.latency_ms
            ok = actual is not None and actual <= max_latency_ms
            checks.append(("latency_ms", ok, f"{actual} <= {max_latency_ms}"))

        if max_cost_usd is not None:
            actual_c = ctx.cost
            ok = actual_c is not None and actual_c <= max_cost_usd
            checks.append(("cost_usd", ok, f"{actual_c} <= {max_cost_usd}"))

        if max_output_tokens is not None:
            actual_t = ctx.output_tokens
            ok = actual_t is not None and actual_t <= max_output_tokens
            checks.append(("output_tokens", ok, f"{actual_t} <= {max_output_tokens}"))

        all_ok = all(ok for _, ok, _ in checks)
        summary = "; ".join(f"{name}: {'OK' if ok else 'OVER'} ({desc})" for name, ok, desc in checks)

        return GradeResult.scored(
            10.0 if all_ok else 0.0,
            reasoning=summary,
            details={"checks": {name: ok for name, ok, _ in checks}},
        )


register(BudgetGrader())
