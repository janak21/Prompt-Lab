"""Unit tests for backend.app.eval.importers -- CSV/JSON/JSONL parsing edge cases."""

from __future__ import annotations

import json

import pytest

from backend.app.eval import importers


class TestDetectFormat:
    def test_extension_csv(self) -> None:
        assert importers.detect_format("f.csv", b"a,b\n1,2\n") == "csv"

    def test_extension_json(self) -> None:
        assert importers.detect_format("f.json", b"[]") == "json"

    def test_extension_jsonl(self) -> None:
        assert importers.detect_format("f.jsonl", b'{"a":1}\n') == "jsonl"

    def test_extension_ndjson(self) -> None:
        assert importers.detect_format("f.ndjson", b'{"a":1}\n') == "jsonl"

    def test_sniff_json_no_extension(self) -> None:
        assert importers.detect_format("upload", b'[{"a": 1}]') == "json"

    def test_sniff_jsonl_no_extension(self) -> None:
        content = b'{"a": 1}\n{"a": 2}\n'
        assert importers.detect_format("upload", content) == "jsonl"

    def test_sniff_csv_fallback(self) -> None:
        assert importers.detect_format("upload", b"a,b\n1,2\n") == "csv"

    def test_empty_file_falls_back_to_csv(self) -> None:
        assert importers.detect_format("upload", b"") == "csv"


class TestUploadSize:
    def test_within_limit_ok(self) -> None:
        importers.check_upload_size(b"small file")

    def test_over_limit_raises(self) -> None:
        with pytest.raises(importers.UploadTooLargeError):
            importers.check_upload_size(b"x" * (importers.MAX_UPLOAD_BYTES + 1))


class TestCsvParsing:
    def test_basic(self) -> None:
        content = b"question,answer\nWhat is 2+2?,4\n"
        fmt, parsed = importers.parse_rows("f.csv", content)
        assert fmt == "csv"
        assert parsed.columns == ["question", "answer"]
        assert parsed.rows == [{"question": "What is 2+2?", "answer": "4"}]

    def test_bom_stripped(self) -> None:
        content = "﻿question,answer\nWhat is 2+2?,4\n".encode("utf-8")
        _fmt, parsed = importers.parse_rows("f.csv", content)
        assert parsed.columns == ["question", "answer"]
        assert "﻿question" not in parsed.columns

    def test_crlf_line_endings(self) -> None:
        content = b"question,answer\r\nWhat is 2+2?,4\r\nWhat color is the sky?,blue\r\n"
        _fmt, parsed = importers.parse_rows("f.csv", content)
        assert len(parsed.rows) == 2
        assert parsed.rows[0]["answer"] == "4"

    def test_quoted_field_with_comma(self) -> None:
        content = b'question,answer\n"What is 1, plus 1?",2\n'
        _fmt, parsed = importers.parse_rows("f.csv", content)
        assert parsed.rows[0]["question"] == "What is 1, plus 1?"

    def test_quoted_field_with_embedded_newline(self) -> None:
        content = b'question,answer\n"Multi\nline question",yes\n'
        _fmt, parsed = importers.parse_rows("f.csv", content)
        assert parsed.rows[0]["question"] == "Multi\nline question"

    def test_ragged_row_too_few_fields_padded(self) -> None:
        content = b"a,b,c\n1,2\n"
        _fmt, parsed = importers.parse_rows("f.csv", content)
        assert parsed.rows[0] == {"a": "1", "b": "2", "c": ""}

    def test_ragged_row_too_many_fields_truncated(self) -> None:
        content = b"a,b\n1,2,3,4\n"
        _fmt, parsed = importers.parse_rows("f.csv", content)
        assert parsed.rows[0] == {"a": "1", "b": "2"}

    def test_duplicate_column_names_disambiguated(self) -> None:
        content = b"name,name,name\nx,y,z\n"
        _fmt, parsed = importers.parse_rows("f.csv", content)
        assert parsed.columns == ["name", "name_2", "name_3"]
        assert parsed.rows[0] == {"name": "x", "name_2": "y", "name_3": "z"}

    def test_empty_file(self) -> None:
        _fmt, parsed = importers.parse_rows("f.csv", b"")
        assert parsed.columns == []
        assert parsed.rows == []

    def test_header_only_no_rows(self) -> None:
        _fmt, parsed = importers.parse_rows("f.csv", b"a,b\n")
        assert parsed.columns == ["a", "b"]
        assert parsed.rows == []

    def test_non_utf8_bytes_raise_clear_error(self) -> None:
        content = b"question,answer\n\xff\xfe bad bytes,4\n"
        with pytest.raises(importers.ImportError_):
            importers.parse_rows("f.csv", content)


class TestJsonParsing:
    def test_array_of_objects(self) -> None:
        content = json.dumps([{"q": "1+1?", "a": "2"}, {"q": "2+2?", "a": "4"}]).encode()
        fmt, parsed = importers.parse_rows("f.json", content)
        assert fmt == "json"
        assert parsed.columns == ["q", "a"]
        assert len(parsed.rows) == 2

    def test_not_an_array_raises(self) -> None:
        content = json.dumps({"q": "1+1?"}).encode()
        with pytest.raises(importers.ImportError_):
            importers.parse_rows("f.json", content)

    def test_array_of_non_objects_raises(self) -> None:
        content = json.dumps([1, 2, 3]).encode()
        with pytest.raises(importers.ImportError_):
            importers.parse_rows("f.json", content)

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(importers.ImportError_):
            importers.parse_rows("f.json", b"{not valid json")

    def test_empty_json_file(self) -> None:
        _fmt, parsed = importers.parse_rows("f.json", b"")
        assert parsed.rows == []

    def test_columns_are_union_across_objects(self) -> None:
        content = json.dumps([{"a": 1}, {"b": 2}]).encode()
        _fmt, parsed = importers.parse_rows("f.json", content)
        assert parsed.columns == ["a", "b"]
        assert parsed.rows[0] == {"a": 1, "b": ""}
        assert parsed.rows[1] == {"a": "", "b": 2}


class TestJsonlParsing:
    def test_basic(self) -> None:
        content = b'{"q": "1+1?", "a": "2"}\n{"q": "2+2?", "a": "4"}\n'
        fmt, parsed = importers.parse_rows("f.jsonl", content)
        assert fmt == "jsonl"
        assert len(parsed.rows) == 2

    def test_blank_lines_skipped(self) -> None:
        content = b'{"q": "1"}\n\n{"q": "2"}\n'
        _fmt, parsed = importers.parse_rows("f.jsonl", content)
        assert len(parsed.rows) == 2

    def test_bad_line_raises_with_line_number(self) -> None:
        content = b'{"q": "1"}\nnot json\n'
        with pytest.raises(importers.ImportError_, match="Line 2"):
            importers.parse_rows("f.jsonl", content)

    def test_non_object_line_raises(self) -> None:
        content = b"[1,2,3]\n"
        with pytest.raises(importers.ImportError_):
            importers.parse_rows("f.jsonl", content)


class TestPreview:
    def test_caps_at_10_rows_but_reports_total(self) -> None:
        rows = "\n".join(f"{i},{i*2}" for i in range(25))
        content = ("a,b\n" + rows + "\n").encode()
        result = importers.preview("f.csv", content)
        assert result["total_rows"] == 25
        assert len(result["rows"]) == 10


class TestApplyMapping:
    def test_maps_columns_to_variables(self) -> None:
        parsed = importers.ParsedRows(
            columns=["question", "answer", "difficulty"],
            rows=[{"question": "2+2?", "answer": "4", "difficulty": "easy"}],
        )
        cases = importers.apply_mapping(
            parsed,
            {"question": "q", "answer": "a"},
            category_column="difficulty",
        )
        assert cases[0]["inputs"] == {"q": "2+2?", "a": "4"}
        assert cases[0]["category"] == "easy"
        assert cases[0]["solution_criteria"] is None

    def test_invalid_expected_format_dropped_to_none(self) -> None:
        parsed = importers.ParsedRows(
            columns=["q", "fmt"], rows=[{"q": "x", "fmt": "not_a_real_format"}]
        )
        cases = importers.apply_mapping(parsed, {"q": "q"}, expected_format_column="fmt")
        assert cases[0]["expected_format"] is None

    def test_valid_expected_format_kept(self) -> None:
        parsed = importers.ParsedRows(columns=["q", "fmt"], rows=[{"q": "x", "fmt": "json"}])
        cases = importers.apply_mapping(parsed, {"q": "q"}, expected_format_column="fmt")
        assert cases[0]["expected_format"] == "json"

    def test_missing_mapped_value_becomes_empty_string(self) -> None:
        parsed = importers.ParsedRows(columns=["q"], rows=[{"q": "only"}])
        cases = importers.apply_mapping(parsed, {"q": "q", "missing_col": "other"})
        assert cases[0]["inputs"] == {"q": "only", "other": ""}
