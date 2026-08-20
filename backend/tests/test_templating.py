"""Tests for backend.app.templating."""

from __future__ import annotations

import pytest

from backend.app.templating import extract_variables, render, validate


class TestExtractVariables:
    def test_simple(self) -> None:
        assert extract_variables("Hello {{name}}, you are {{age}}.") == ["name", "age"]

    def test_dedupes_preserving_order(self) -> None:
        assert extract_variables("{{a}} {{b}} {{a}}") == ["a", "b"]

    def test_tolerant_of_whitespace(self) -> None:
        assert extract_variables("{{ name }} {{name}} {{  name  }}") == ["name"]

    def test_no_variables(self) -> None:
        assert extract_variables("no placeholders here") == []

    def test_ignores_json_braces(self) -> None:
        # {{"key": "value"}} is not a bare-identifier placeholder -- left alone.
        template = 'Example: {{"key": "value"}} and real {{var}}'
        assert extract_variables(template) == ["var"]

    def test_escaped_braces_not_extracted(self) -> None:
        assert extract_variables("literal {{{{brace}}}} plus {{real}}") == ["real"]

    def test_underscored_and_numeric_names(self) -> None:
        assert extract_variables("{{ticket_text}} {{tier}} {{var_2}}") == ["ticket_text", "tier", "var_2"]


class TestRender:
    def test_basic_substitution(self) -> None:
        assert render("Hello {{name}}!", {"name": "World"}) == "Hello World!"

    def test_whitespace_tolerant(self) -> None:
        assert render("{{ name }}", {"name": "x"}) == "x"

    def test_missing_variable_raises(self) -> None:
        with pytest.raises(ValueError, match="Missing template variables"):
            render("{{a}} {{b}}", {"a": "1"})

    def test_repeated_variable_substituted_everywhere(self) -> None:
        assert render("{{a}}-{{a}}", {"a": "x"}) == "x-x"

    def test_escaped_braces_render_literally(self) -> None:
        assert render("json: {{{{example}}}} real: {{v}}", {"v": "5"}) == "json: {{example}} real: 5"

    def test_json_example_untouched(self) -> None:
        template = 'Return like {{"score": 10}} using {{input}}'
        assert render(template, {"input": "x"}) == 'Return like {{"score": 10}} using x'

    def test_extra_unused_inputs_ok(self) -> None:
        assert render("{{a}}", {"a": "1", "b": "unused"}) == "1"


class TestValidate:
    def test_no_missing(self) -> None:
        result = validate("{{a}} {{b}}", {"a", "b", "c"})
        assert result == []
        assert not result

    def test_missing_reported(self) -> None:
        result = validate("{{a}} {{b}}", {"a"})
        assert result == ["b"]
        assert result

    def test_accepts_list_input(self) -> None:
        assert validate("{{x}}", ["x"]) == []
