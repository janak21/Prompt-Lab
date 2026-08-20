"""``json_schema`` grader: output must parse as JSON AND validate against ``config.schema``.

Scores 0 or 10. On failure (parse error or schema-validation error), the failure
message is placed in ``reasoning`` so the UI can show exactly what went wrong.

Markdown code fences are stripped before parsing, for the same reason as
``code_syntax`` -- see :mod:`backend.app.eval.graders.extract`.
"""

from __future__ import annotations

import json

import jsonschema

from .base import GradeContext, GradeResult, Grader, register
from .extract import strip_code_fences


class JsonSchemaGrader(Grader):
    type = "json_schema"

    async def grade(self, ctx: GradeContext) -> GradeResult:
        schema = ctx.config.get("schema")
        if not schema:
            return GradeResult.failed("json_schema grader has no `schema` configured.")

        content, fence_note = strip_code_fences(ctx.output or "")
        suffix = f" ({fence_note})" if fence_note else ""

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            return GradeResult.scored(
                0.0,
                reasoning=f"Output is not valid JSON: {exc}{suffix}",
                details={"valid": False, "stage": "parse", "normalizations": [fence_note] if fence_note else []},
            )

        try:
            jsonschema.validate(instance=parsed, schema=schema)
        except jsonschema.ValidationError as exc:
            return GradeResult.scored(
                0.0,
                reasoning=f"Output does not match schema: {exc.message}{suffix}",
                details={"valid": False, "stage": "validate", "normalizations": [fence_note] if fence_note else []},
            )
        except jsonschema.SchemaError as exc:
            return GradeResult.failed(f"Configured JSON Schema is itself invalid: {exc.message}")

        return GradeResult.scored(
            10.0,
            reasoning=f"Output parses and validates against the schema.{suffix}",
            details={"valid": True, "normalizations": [fence_note] if fence_note else []},
        )


register(JsonSchemaGrader())
