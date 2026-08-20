"""``llm_judge`` grader: an LLM scores the model's output against a rubric.

Ported from the source notebook's ``grade_by_model`` (``../001_prompt_evals_complete.ipynb``,
the cell defining the AWS-code-review judge prompt), with two changes required by the
frozen contract:

1. **Structured outputs, not prefill.** The notebook gets JSON out of the model by
   prefilling an assistant turn with ` ```json ` and stopping at ` ``` `. That trick is
   removed on Claude Opus 5 / Sonnet 5 (HTTP 400). This grader always calls
   ``llm.json_complete(..., schema=...)`` -- the structured-outputs path -- regardless
   of which model is configured as judge (see API_CONTRACT.md rule 0).
2. **Field order.** The JSON schema's ``properties`` (and ``required``) list
   ``strengths``, ``weaknesses``, ``reasoning``, ``score`` in that order, so the model
   is asked to articulate strengths/weaknesses and reason about them *before* it
   commits to a number -- the notebook's own field order, preserved deliberately.

The rubric comes from the grader's ``config.rubric`` (not hardcoded, unlike the
notebook's fixed AWS-review prompt). ``config.use_solution_criteria`` controls whether
the test case's ``solution_criteria`` is included as grounding. ``config.judge_model``
overrides the run's judge model when set.
"""

from __future__ import annotations

from typing import Any

from .base import GradeContext, GradeResult, Grader, register

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "1-3 key strengths of the output.",
        },
        "weaknesses": {
            "type": "array",
            "items": {"type": "string"},
            "description": "1-3 key areas for improvement.",
        },
        "reasoning": {
            "type": "string",
            "description": "A concise explanation of the overall assessment, written before the score.",
        },
        "score": {
            "type": "number",
            "description": "Overall quality score from 1 (worst) to 10 (best).",
        },
    },
    "required": ["strengths", "weaknesses", "reasoning", "score"],
    "additionalProperties": False,
}


def _format_inputs(inputs: dict[str, Any]) -> str:
    if not inputs:
        return "(no inputs)"
    return "\n".join(f"{key}: {value}" for key, value in inputs.items())


def build_judge_prompt(
    *,
    inputs: dict[str, Any],
    output: str,
    rubric: str,
    solution_criteria: str | None,
    use_solution_criteria: bool,
) -> str:
    """Build the judge's user-turn prompt. Exposed for testing/inspection."""
    criteria_block = ""
    if use_solution_criteria and solution_criteria:
        criteria_block = f"""
Solution criteria to weigh heavily in your evaluation:
<criteria>
{solution_criteria}
</criteria>
"""
    return f"""You are an expert evaluator. Your task is to evaluate the following AI-generated output.

Task inputs:
<inputs>
{_format_inputs(inputs)}
</inputs>

Rubric to evaluate against:
<rubric>
{rubric}
</rubric>
{criteria_block}
Output to evaluate:
<output>
{output}
</output>

Evaluate the output. First identify concrete strengths and weaknesses, then reason about
the overall quality, then assign a score. Keep your response concise and direct."""


class LLMJudgeGrader(Grader):
    type = "llm_judge"

    async def grade(self, ctx: GradeContext) -> GradeResult:
        config = ctx.config
        rubric = config.get("rubric", "")
        use_solution_criteria = bool(config.get("use_solution_criteria", False))
        judge_model = config.get("judge_model") or ctx.judge_model

        prompt = build_judge_prompt(
            inputs=ctx.test_case.get("inputs") or {},
            output=ctx.output,
            rubric=rubric,
            solution_criteria=ctx.test_case.get("solution_criteria"),
            use_solution_criteria=use_solution_criteria,
        )

        result = await ctx.llm.json_complete(
            [{"role": "user", "content": prompt}],
            model=judge_model,
            schema=JUDGE_SCHEMA,
            system="You are a rigorous, fair evaluator of AI-generated outputs. Respond with JSON only.",
            temperature=0.0,
            max_tokens=1024,
        )

        if not isinstance(result, dict):
            return GradeResult.failed(f"Judge response was not a JSON object: {result!r}")

        missing = [k for k in ("strengths", "weaknesses", "reasoning", "score") if k not in result]
        if missing:
            return GradeResult.failed(f"Judge response missing field(s): {', '.join(missing)}")

        try:
            score = float(result["score"])
        except (TypeError, ValueError):
            return GradeResult.failed(f"Judge score was not numeric: {result['score']!r}")

        return GradeResult.scored(
            score,
            reasoning=str(result["reasoning"]),
            details={
                "strengths": result["strengths"],
                "weaknesses": result["weaknesses"],
                "judge_model": judge_model,
            },
        )


register(LLMJudgeGrader())
