"""``string_match`` grader: proportional score across ``must_contain`` / ``must_not_contain``
/ ``regex`` constraints, honouring ``case_sensitive``.

Score = ``10 * satisfied_constraints / total_constraints``. If zero constraints are
configured (all three lists/patterns empty), the grader is SKIPPED -- there is nothing
to check, so it must not silently award a perfect 10.
"""

from __future__ import annotations

import re

from .base import GradeContext, GradeResult, Grader, register


class StringMatchGrader(Grader):
    type = "string_match"

    async def grade(self, ctx: GradeContext) -> GradeResult:
        config = ctx.config
        must_contain: list[str] = config.get("must_contain") or []
        must_not_contain: list[str] = config.get("must_not_contain") or []
        regex: str | None = config.get("regex")
        case_sensitive = bool(config.get("case_sensitive", False))

        total = len(must_contain) + len(must_not_contain) + (1 if regex else 0)
        if total == 0:
            return GradeResult.skip("No must_contain/must_not_contain/regex constraints configured.")

        output = ctx.output
        haystack = output if case_sensitive else output.lower()

        satisfied = 0
        passed: list[str] = []
        failed: list[str] = []

        for needle in must_contain:
            target = needle if case_sensitive else needle.lower()
            if target in haystack:
                satisfied += 1
                passed.append(f"contains {needle!r}")
            else:
                failed.append(f"missing {needle!r}")

        for needle in must_not_contain:
            target = needle if case_sensitive else needle.lower()
            if target not in haystack:
                satisfied += 1
                passed.append(f"does not contain {needle!r}")
            else:
                failed.append(f"unexpectedly contains {needle!r}")

        if regex:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(regex, flags)
            except re.error as exc:
                return GradeResult.failed(f"Invalid regex in config: {exc}")
            if pattern.search(output):
                satisfied += 1
                passed.append(f"matches regex {regex!r}")
            else:
                failed.append(f"does not match regex {regex!r}")

        score = 10.0 * satisfied / total
        reasoning_parts = []
        if passed:
            reasoning_parts.append("Passed: " + "; ".join(passed))
        if failed:
            reasoning_parts.append("Failed: " + "; ".join(failed))
        reasoning = " | ".join(reasoning_parts)

        return GradeResult.scored(
            score,
            reasoning=reasoning,
            details={"satisfied": satisfied, "total": total, "passed": passed, "failed": failed},
        )


register(StringMatchGrader())
