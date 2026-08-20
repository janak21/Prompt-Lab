"""Normalize raw model output before syntax/schema parsing.

Why this exists
---------------
The source notebooks got un-fenced code out of the model by prefilling an assistant turn
with ```` ```code ```` and stopping at the closing fence, so the fence never appeared in
the output. That technique returns HTTP 400 on Claude 5 models (assistant prefill was
removed), so **markdown-fenced output is now the normal case** for any prompt that asks
for code. A grader that feeds ```` ```json\\n{...} ```` straight into ``json.loads`` scores
a perfectly correct answer 0.

Fence stripping is therefore **unconditional**, not a per-grader flag. Rationale: a fence
is a transport artifact of how chat models emit code, not part of the answer. Making it
opt-in would mean every user has to discover the flag after first seeing a wrongly-zeroed
grade, and the failure is silent-looking (a real 0, with a plausible parse error). If a
user genuinely needs to forbid fences, that is a content assertion and belongs in a
``string_match`` grader (``must_not_contain: ["```"]``), where it reads as an explicit
intent rather than a parser quirk.

Every function here returns a ``note`` describing what was changed, so the grade's
reasoning can explain why it judged something other than the literal raw output.
"""

from __future__ import annotations

import re

# ```lang\n ... \n```  -- lang optional; non-greedy body; tolerates a missing trailing newline.
_FENCED_BLOCK = re.compile(
    r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)(?:\r?\n)?```",
    re.DOTALL,
)
# An opening fence the model never closed (it ran out of tokens, or just didn't).
_UNCLOSED_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*)\Z", re.DOTALL)

# Python/JS style raw-or-plain string literal, used to rescue a regex embedded in code.
_STRING_LITERAL = re.compile(r"""(?:r|rb|br)?(['"])(.+?)(?<!\\)\1""", re.DOTALL)


def strip_code_fences(text: str) -> tuple[str, str | None]:
    """Return ``(content, note)`` with any markdown code fence removed.

    Picks the **largest** fenced block when several are present -- models commonly emit the
    answer first and short example/usage snippets after, and the answer is normally the
    longest. Falls back to an unclosed opening fence, then to the original text.

    ``note`` is ``None`` when nothing was changed.
    """
    if not text:
        return text, None

    blocks = _FENCED_BLOCK.findall(text)
    if blocks:
        lang, body = max(blocks, key=lambda pair: len(pair[1]))
        label = f"```{lang}" if lang else "```"
        suffix = f" (largest of {len(blocks)} fenced blocks)" if len(blocks) > 1 else ""
        return body.strip(), f"stripped {label} fence before parsing{suffix}"

    unclosed = _UNCLOSED_FENCE.search(text)
    if unclosed:
        lang, body = unclosed.groups()
        label = f"```{lang}" if lang else "```"
        return body.strip(), f"stripped unclosed {label} fence before parsing"

    return text, None


def extract_regex_candidate(text: str) -> tuple[str, str | None]:
    """Rescue a regex pattern that the model wrapped in code instead of emitting bare.

    Only used **after** a direct ``re.compile`` of the (de-fenced) output has already
    failed, so this never overrides an output that was already a valid pattern. Returns
    ``(candidate, note)``; the candidate is the original text when nothing better is found.

    Deliberately conservative: it requires exactly one unambiguous string literal in the
    text. Guessing between several candidates would let the grader pass an output the user
    would consider wrong, and a grader that is quietly clever is worse than one that is
    honestly strict.
    """
    literals = [body for _quote, body in _STRING_LITERAL.findall(text)]
    candidates = [lit for lit in literals if lit.strip()]
    if len(candidates) != 1:
        return text, None
    return candidates[0], "extracted the single quoted pattern from surrounding code"
