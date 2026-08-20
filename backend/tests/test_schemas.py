"""Tests for the grader config discriminated-union validation in backend.app.schemas."""

from __future__ import annotations

import pydantic
import pytest

from backend.app.schemas import GraderCreateAdapter, validate_grader_config


class TestGraderCreateDiscriminatedUnion:
    def test_valid_llm_judge(self) -> None:
        parsed = GraderCreateAdapter.validate_python(
            {
                "type": "llm_judge",
                "name": "quality",
                "config": {"rubric": "be helpful", "use_solution_criteria": True},
            }
        )
        assert parsed.type == "llm_judge"
        assert parsed.config.rubric == "be helpful"

    def test_valid_budget(self) -> None:
        parsed = GraderCreateAdapter.validate_python(
            {"type": "budget", "name": "cost cap", "config": {"max_cost_usd": 0.05}}
        )
        assert parsed.config.max_cost_usd == 0.05

    def test_mismatched_config_rejected(self) -> None:
        # budget type but llm_judge-shaped config (missing rubric/use_solution_criteria
        # which llm_judge requires, and budget fields are all optional so this would
        # otherwise "validate" against budget -- but the extra unknown fields plus
        # wrong shape should fail against the type's actual model).
        with pytest.raises(pydantic.ValidationError):
            GraderCreateAdapter.validate_python(
                {"type": "code_syntax", "name": "syntax", "config": {"rubric": "not a code_syntax field"}}
            )

    def test_unknown_type_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            GraderCreateAdapter.validate_python(
                {"type": "not_a_real_type", "name": "x", "config": {}}
            )

    def test_invalid_code_syntax_format_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            GraderCreateAdapter.validate_python(
                {"type": "code_syntax", "name": "x", "config": {"format": "yaml"}}
            )


class TestValidateGraderConfig:
    def test_valid_string_match(self) -> None:
        result = validate_grader_config(
            "string_match", {"must_contain": ["ok"], "must_not_contain": [], "case_sensitive": False}
        )
        assert result["must_contain"] == ["ok"]

    def test_json_schema_alias_roundtrips(self) -> None:
        result = validate_grader_config("json_schema", {"schema": {"type": "object"}})
        assert result["schema"] == {"type": "object"}

    def test_invalid_config_raises(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            validate_grader_config("llm_judge", {"rubric": "x"})  # missing use_solution_criteria

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError):
            validate_grader_config("nope", {})


class TestUnknownFieldsRejected:
    """Extra/unknown keys must 422 on every grader config type -- via both the POST
    discriminated union and the PATCH-time validate_grader_config() path -- so a typoed
    field (e.g. max_latency vs. max_latency_ms) is caught at save time instead of being
    silently dropped and producing a grader that looks configured but never runs."""

    def test_llm_judge_rejects_unknown_key(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="nope"):
            validate_grader_config(
                "llm_judge", {"rubric": "x", "use_solution_criteria": True, "nope": 1}
            )

    def test_code_syntax_rejects_unknown_key(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="nope"):
            validate_grader_config("code_syntax", {"format": "json", "nope": 1})

    def test_string_match_rejects_unknown_key(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="typo_field"):
            validate_grader_config(
                "string_match", {"must_contain": ["ok"], "typo_field": 9}
            )

    def test_json_schema_rejects_unknown_key(self) -> None:
        # The reported repro: {"schemaa": {}} -- typoed key, no valid `schema` supplied.
        with pytest.raises(pydantic.ValidationError):
            validate_grader_config("json_schema", {"schemaa": {}})

    def test_budget_rejects_unknown_key(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="nope"):
            validate_grader_config("budget", {"nope": 1})

    def test_budget_rejects_unknown_key_via_post_path(self) -> None:
        """Same enforcement via the discriminated union used by POST, not just PATCH."""
        with pytest.raises(pydantic.ValidationError, match="nope"):
            GraderCreateAdapter.validate_python(
                {"type": "budget", "name": "cost cap", "config": {"nope": 1}}
            )

    def test_string_match_rejects_unknown_key_via_post_path(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="typo_field"):
            GraderCreateAdapter.validate_python(
                {
                    "type": "string_match",
                    "name": "contains ok",
                    "config": {"must_contain": ["ok"], "typo_field": 9},
                }
            )


class TestAlwaysSkipConfigurationsRejected:
    """A grader that can never contribute a score (budget with no ceiling, string_match
    with no constraints) is a configuration error, not a valid lenient state -- it would
    silently never run while still counting as 'configured' in the UI."""

    def test_budget_with_no_ceiling_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="no ceiling configured"):
            validate_grader_config("budget", {})

    def test_budget_with_all_ceilings_explicitly_none_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="no ceiling configured"):
            validate_grader_config(
                "budget", {"max_latency_ms": None, "max_cost_usd": None, "max_output_tokens": None}
            )

    def test_budget_with_one_ceiling_set_accepted(self) -> None:
        result = validate_grader_config("budget", {"max_latency_ms": 5000})
        assert result["max_latency_ms"] == 5000

    def test_string_match_with_no_constraints_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="no constraints configured"):
            validate_grader_config("string_match", {})

    def test_string_match_with_empty_lists_and_no_regex_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="no constraints configured"):
            validate_grader_config(
                "string_match", {"must_contain": [], "must_not_contain": [], "regex": None}
            )

    def test_string_match_with_only_regex_accepted(self) -> None:
        result = validate_grader_config("string_match", {"regex": "^ok$"})
        assert result["regex"] == "^ok$"

    def test_string_match_with_only_must_not_contain_accepted(self) -> None:
        result = validate_grader_config("string_match", {"must_not_contain": ["bad"]})
        assert result["must_not_contain"] == ["bad"]

    def test_code_syntax_auto_format_is_not_treated_as_always_skip(self) -> None:
        """format: "auto" legitimately skips per-case (when a case has no
        expected_format) -- that's dynamic, not an always-skip config, so it must NOT
        be rejected the way empty budget/string_match configs are."""
        result = validate_grader_config("code_syntax", {"format": "auto"})
        assert result["format"] == "auto"

    def test_always_skip_rejected_via_post_path_too(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="no ceiling configured"):
            GraderCreateAdapter.validate_python(
                {"type": "budget", "name": "cost cap", "config": {}}
            )


class TestMalformedRegexAndSchemaRejected:
    """A regex that doesn't compile or a schema that isn't valid JSON Schema must 422
    at config-save time, not fail on every case of a run."""

    def test_string_match_uncompilable_regex_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="regex does not compile"):
            validate_grader_config("string_match", {"regex": "("})

    def test_string_match_valid_regex_accepted(self) -> None:
        result = validate_grader_config("string_match", {"regex": r"^\d+$"})
        assert result["regex"] == r"^\d+$"

    def test_json_schema_invalid_schema_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="not a valid JSON Schema"):
            validate_grader_config("json_schema", {"schema": {"type": "definitely-not-a-type"}})

    def test_json_schema_invalid_schema_shape_rejected(self) -> None:
        # "properties" must be an object -- this is structurally invalid JSON Schema.
        with pytest.raises(pydantic.ValidationError, match="not a valid JSON Schema"):
            validate_grader_config("json_schema", {"schema": {"type": "object", "properties": "nope"}})

    def test_json_schema_valid_schema_accepted(self) -> None:
        result = validate_grader_config(
            "json_schema",
            {"schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}},
        )
        assert result["schema"]["type"] == "object"
