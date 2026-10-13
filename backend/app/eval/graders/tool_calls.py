"""Deterministic assertions over all tool attempts in a conversation."""

from .base import GradeContext, GradeResult, Grader, register


class ToolCallsGrader(Grader):
    type = "tool_calls"

    async def grade(self, ctx: GradeContext) -> GradeResult:
        calls = [call for call in ctx.tool_calls if call["name"] == ctx.config["tool"]]
        if ctx.config["mode"] == "never_called":
            passed = not calls
        else:
            arguments = ctx.config.get("arguments") or {}
            passed = any(not call.get("error") and all(key in call["input"] and call["input"][key] == value for key, value in arguments.items()) for call in calls)
        return GradeResult.scored(
            10.0 if passed else 0.0,
            f"Tool {ctx.config['tool']!r}: {ctx.config['mode']} {'passed' if passed else 'failed'}.",
            {"matching_calls": calls},
        )


register(ToolCallsGrader())
