"""``code_syntax`` grader: does the model's output parse as the expected code shape?

Scores 0 or 10 (never in between). ``config.format`` is one of ``json`` / ``python`` /
``regex`` / ``auto``:

- ``json``   -- ``json.loads(output)`` must succeed.
- ``python`` -- ``ast.parse(output)`` must succeed.
- ``regex``  -- ``re.compile(output)`` must succeed (the output itself is expected to
  be a regex pattern).
- ``auto``   -- resolves to the test case's ``expected_format``. If that is ``NULL``,
  there is nothing to check against, so the grader is SKIPPED (excluded from the
  weighted average), never scored 0.

Markdown code fences are stripped from the output before parsing -- see
:mod:`backend.app.eval.graders.extract` for why that is unconditional. What was stripped
is reported in the grade's reasoning so a user can see why the grade differs from the
literal raw output.
"""

from __future__ import annotations

import ast
import json
import re

from .base import GradeContext, GradeResult, Grader, register
from .extract import extract_regex_candidate, strip_code_fences

_CHECKERS = {"json": "json", "python": "python", "regex": "regex"}


class CodeSyntaxGrader(Grader):
    type = "code_syntax"

    async def grade(self, ctx: GradeContext) -> GradeResult:
        configured_format = ctx.config.get("format", "auto")
        actual_format = configured_format
        if configured_format == "auto":
            actual_format = ctx.test_case.get("expected_format")
            if not actual_format:
                return GradeResult.skip(
                    "format=auto and the test case has no expected_format -- nothing to check.",
                )

        if actual_format not in _CHECKERS:
            return GradeResult.failed(f"Unknown code_syntax format: {actual_format!r}")

        content, fence_note = strip_code_fences(ctx.output or "")
        notes = [n for n in (fence_note,) if n]

        try:
            if actual_format == "json":
                json.loads(content)
            elif actual_format == "python":
                ast.parse(content)
            elif actual_format == "regex":
                try:
                    re.compile(content)
                except re.error:
                    # The model may have returned code *containing* a pattern rather than
                    # a bare pattern. Try once to rescue it; re-raise the new error if not.
                    candidate, extract_note = extract_regex_candidate(content)
                    if extract_note is None:
                        raise
                    re.compile(candidate)
                    notes.append(extract_note)
        except Exception as exc:  # noqa: BLE001 - any parse error means "invalid syntax"
            return GradeResult.scored(
                0.0,
                reasoning=_with_notes(f"Output is not valid {actual_format}: {exc}", notes),
                details={
                    "format": actual_format,
                    "valid": False,
                    "error": str(exc),
                    "normalizations": notes,
                },
            )

        return GradeResult.scored(
            10.0,
            reasoning=_with_notes(f"Output is valid {actual_format}.", notes),
            details={"format": actual_format, "valid": True, "normalizations": notes},
        )


def _with_notes(message: str, notes: list[str]) -> str:
    """Append any normalization notes so the grade explains what it actually parsed."""
    return f"{message} ({'; '.join(notes)})" if notes else message


register(CodeSyntaxGrader())
