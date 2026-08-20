"""Fenced-output handling for the syntax/schema graders.

Regression coverage for a bug found in the first live end-to-end run: the model returned
```` ```json\\n{...} ```` and `code_syntax` scored 0 on an answer the LLM judge rated 9/10,
because `json.loads` chokes on the backtick. Assistant prefill (which the source notebooks
used to suppress fences) returns HTTP 400 on Claude 5, so fenced output is now normal.
"""

from __future__ import annotations

import pytest

from backend.app.eval.graders.extract import extract_regex_candidate, strip_code_fences
from backend.app.eval.graders.code_syntax import CodeSyntaxGrader
from backend.app.eval.graders.json_schema import JsonSchemaGrader
from backend.app.eval.graders.base import GradeContext


def _ctx(output: str, *, config: dict, test_case: dict | None = None) -> GradeContext:
    return GradeContext(
        test_case=test_case if test_case is not None else {},
        output=output,
        config=config,
        llm=None,  # type: ignore[arg-type]  # unused by syntax/schema graders
        judge_model="claude-sonnet-5",
    )


class TestStripCodeFences:
    def test_no_fence_is_returned_unchanged(self):
        content, note = strip_code_fences('{"a": 1}')
        assert content == '{"a": 1}'
        assert note is None

    @pytest.mark.parametrize("lang", ["json", "python", "regex", ""])
    def test_fence_with_and_without_language_tag(self, lang):
        content, note = strip_code_fences(f"```{lang}\n{{\"a\": 1}}\n```")
        assert content == '{"a": 1}'
        assert "stripped" in note

    def test_unclosed_fence(self):
        content, note = strip_code_fences('```python\nx = 1')
        assert content == "x = 1"
        assert "unclosed" in note

    def test_prose_around_the_block_is_discarded(self):
        content, _ = strip_code_fences('Here you go:\n```json\n{"a": 1}\n```\nHope that helps!')
        assert content == '{"a": 1}'

    def test_multiple_blocks_takes_the_largest(self):
        text = '```json\n{}\n```\nand usage:\n```json\n{"much": "longer", "block": true}\n```'
        content, note = strip_code_fences(text)
        assert content == '{"much": "longer", "block": true}'
        assert "largest of 2" in note

    def test_empty_output(self):
        assert strip_code_fences("") == ("", None)


class TestExtractRegexCandidate:
    def test_single_literal_is_extracted(self):
        candidate, note = extract_regex_candidate("pattern = r'^i-[0-9a-f]{8}$'")
        assert candidate == "^i-[0-9a-f]{8}$"
        assert note is not None

    def test_ambiguous_multiple_literals_refuses_to_guess(self):
        candidate, note = extract_regex_candidate("a = 'one'\nb = 'two'")
        assert note is None, "must not guess between candidates"
        assert candidate == "a = 'one'\nb = 'two'"

    def test_no_literal_returns_input(self):
        _candidate, note = extract_regex_candidate("just words")
        assert note is None


@pytest.mark.anyio
class TestCodeSyntaxGraderWithFences:
    async def test_fenced_json_now_scores_10(self):
        """The exact live-run failure: a valid IAM policy inside a ```json fence."""
        out = '```json\n{"Version": "2012-10-17", "Statement": []}\n```'
        res = await CodeSyntaxGrader().grade(_ctx(out, config={"format": "json"}))
        assert res.score == 10.0
        assert "stripped" in res.reasoning

    async def test_fenced_python_now_scores_10(self):
        out = '```python\ndef f(u):\n    return u.split(".")[1]\n```'
        res = await CodeSyntaxGrader().grade(_ctx(out, config={"format": "python"}))
        assert res.score == 10.0

    async def test_regex_inside_python_scores_10(self):
        """Note: most arbitrary text compiles as a regex, so this passes WITHOUT needing
        the extraction rescue. See TestRegexCheckIsAWeakSignal below."""
        out = "```python\nimport re\npattern = r'^i-[0-9a-f]{8}$'\n```"
        res = await CodeSyntaxGrader().grade(_ctx(out, config={"format": "regex"}))
        assert res.score == 10.0

    async def test_regex_extraction_rescues_a_genuinely_invalid_pattern(self):
        """The live-run case: an unescaped `i-1` range makes the whole blob uncompilable,
        so the single-literal rescue is what saves it."""
        out = "```python\npattern = r'^i-[0-9a-f]{8}$'\n# range check [9-0]\n```"
        res = await CodeSyntaxGrader().grade(_ctx(out, config={"format": "regex"}))
        assert res.score == 10.0
        assert "extracted" in res.reasoning

    async def test_genuinely_invalid_output_still_scores_zero(self):
        res = await CodeSyntaxGrader().grade(_ctx("```json\nnot json at all\n```", config={"format": "json"}))
        assert res.score == 0.0
        assert "not valid json" in res.reasoning.lower()

    async def test_unfenced_output_still_works(self):
        res = await CodeSyntaxGrader().grade(_ctx('{"a": 1}', config={"format": "json"}))
        assert res.score == 10.0
        assert "stripped" not in res.reasoning

    async def test_auto_with_no_expected_format_still_skips_not_zero(self):
        res = await CodeSyntaxGrader().grade(_ctx("```json\n{}\n```", config={"format": "auto"}))
        assert res.status == "skipped"


@pytest.mark.anyio
class TestJsonSchemaGraderWithFences:
    async def test_fenced_output_validates(self):
        schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
        res = await JsonSchemaGrader().grade(_ctx('```json\n{"a": 1}\n```', config={"schema": schema}))
        assert res.score == 10.0

    async def test_fenced_output_failing_schema_scores_zero(self):
        schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
        res = await JsonSchemaGrader().grade(_ctx('```json\n{"a": "wrong type"}\n```', config={"schema": schema}))
        assert res.score == 0.0


class TestRegexCheckIsAWeakSignal:
    """`re.compile` accepts almost any string, so a passing `regex` syntax check means
    very little on its own. Documented here so nobody mistakes a 10/10 for "this is the
    right pattern" -- pair it with `llm_judge` or `string_match` for real signal.
    """

    import re as _re

    @pytest.mark.parametrize(
        "text",
        ["the quick brown fox", "def f(): return 1", "just a sentence, really"],
    )
    def test_ordinary_prose_compiles_as_a_regex(self, text):
        self._re.compile(text)  # does not raise
