"""CSV / JSON / JSONL dataset importers.

Pure functions over raw bytes + filename -- no FastAPI dependency, so they're directly
unit-testable. The router (``routers/datasets.py``) is a thin wrapper that reads the
uploaded file, calls :func:`detect_format` + :func:`preview` or :func:`parse_rows`, and
turns :class:`ImportError` into the appropriate HTTP status.

Defensive about real-world files
----------------------------------
- UTF-8 BOM is stripped transparently (``utf-8-sig`` decode).
- CRLF / mixed line endings are normalized by the CSV module (opened with
  ``newline=""`` per the stdlib's recommendation) and by universal-newline text decode
  for JSON/JSONL.
- Quoted CSV fields containing commas/newlines are handled by :mod:`csv`'s own quoting.
- Ragged CSV rows (too few/many fields vs. the header) are padded/truncated rather than
  raising.
- Duplicate CSV column names are disambiguated (``name``, ``name_2``, ``name_3``, ...)
  rather than silently colliding or crashing.
- Empty files parse to zero rows/columns rather than raising.
- Non-UTF-8 bytes raise a clear :class:`ImportError` (surfaced as 422), never a raw
  ``UnicodeDecodeError`` (which would otherwise surface as a 500).
- Valid JSON that isn't an array of objects raises a clear :class:`ImportError`.
- :func:`check_upload_size` enforces :data:`MAX_UPLOAD_BYTES`, for the router to turn
  into a 413.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB -- generous for a CSV/JSON/JSONL test-case file,
# small enough to keep preview/commit fast and bound memory for an in-process, local tool.


class ImportError_(ValueError):
    """Raised for any malformed-upload condition. Message is safe to surface directly to
    the client as a 422 ``detail`` (never a raw parser traceback)."""


class UploadTooLargeError(ImportError_):
    """Raised when the upload exceeds :data:`MAX_UPLOAD_BYTES` -- the router maps this to 413."""


def check_upload_size(content: bytes) -> None:
    """Raise :class:`UploadTooLargeError` if ``content`` exceeds :data:`MAX_UPLOAD_BYTES`."""
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadTooLargeError(
            f"Upload is {len(content)} bytes, exceeding the {MAX_UPLOAD_BYTES}-byte limit"
        )


def detect_format(filename: str, content: bytes) -> str:
    """Detect ``"csv" | "json" | "jsonl"`` from the filename extension AND content.

    Extension is checked first (fast, usually correct). If the extension is missing or
    unrecognized, falls back to content sniffing: valid whole-document JSON -> "json";
    otherwise, if every non-blank line parses as its own JSON value -> "jsonl";
    otherwise -> "csv" (the most permissive format -- almost anything parses as CSV).
    """
    lower = filename.lower()
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".jsonl") or lower.endswith(".ndjson"):
        return "jsonl"
    if lower.endswith(".json"):
        return "json"

    text = _decode(content)
    stripped = text.strip()
    if not stripped:
        return "csv"
    try:
        json.loads(stripped)
        return "json"
    except json.JSONDecodeError:
        pass

    lines = [line for line in stripped.splitlines() if line.strip()]
    if lines and all(_is_json_line(line) for line in lines):
        return "jsonl"
    return "csv"


def _is_json_line(line: str) -> bool:
    try:
        json.loads(line)
        return True
    except json.JSONDecodeError:
        return False


def _decode(content: bytes) -> str:
    """Decode upload bytes to text, stripping a UTF-8 BOM if present.

    Raises :class:`ImportError_` (never a raw ``UnicodeDecodeError``) on non-UTF-8 bytes.
    """
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportError_(
            "File is not valid UTF-8 text. Re-save the file with UTF-8 encoding and try again."
        ) from exc


# --------------------------------------------------------------------------
# Row parsing
# --------------------------------------------------------------------------


@dataclass
class ParsedRows:
    """The result of parsing an upload into tabular rows."""

    columns: list[str]
    rows: list[dict[str, Any]]


def _dedupe_columns(columns: list[str]) -> list[str]:
    """Disambiguate duplicate column names: ``name``, ``name_2``, ``name_3``, ..."""
    seen: dict[str, int] = {}
    result: list[str] = []
    for col in columns:
        seen[col] = seen.get(col, 0) + 1
        result.append(col if seen[col] == 1 else f"{col}_{seen[col]}")
    return result


def _parse_csv(text: str) -> ParsedRows:
    # newline="" (via StringIO here, since we already have text) is the stdlib-recommended
    # way to let csv's own universal-newline + quoting handling work correctly on CRLF and
    # on quoted fields that themselves contain embedded newlines.
    buf = io.StringIO(text, newline="")
    reader = csv.reader(buf)
    try:
        header = next(reader)
    except StopIteration:
        return ParsedRows(columns=[], rows=[])

    columns = _dedupe_columns([h.strip() for h in header])
    rows: list[dict[str, Any]] = []
    for raw_row in reader:
        if not raw_row or (len(raw_row) == 1 and raw_row[0] == ""):
            continue  # skip fully blank lines
        # Pad/truncate ragged rows to the header width instead of raising.
        if len(raw_row) < len(columns):
            raw_row = raw_row + [""] * (len(columns) - len(raw_row))
        elif len(raw_row) > len(columns):
            raw_row = raw_row[: len(columns)]
        rows.append(dict(zip(columns, raw_row)))
    return ParsedRows(columns=columns, rows=rows)


def _parse_json(text: str) -> ParsedRows:
    stripped = text.strip()
    if not stripped:
        return ParsedRows(columns=[], rows=[])
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ImportError_(f"File is not valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ImportError_("JSON file must contain an array of objects at the top level.")
    if not all(isinstance(item, dict) for item in data):
        raise ImportError_("JSON array must contain only objects (one per test case).")

    columns: list[str] = []
    for item in data:
        for key in item:
            if key not in columns:
                columns.append(key)
    rows = [{col: item.get(col, "") for col in columns} for item in data]
    return ParsedRows(columns=columns, rows=rows)


def _parse_jsonl(text: str) -> ParsedRows:
    lines = [line for line in text.splitlines() if line.strip()]
    items: list[dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ImportError_(f"Line {i} is not valid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ImportError_(f"Line {i} must be a JSON object.")
        items.append(value)

    columns: list[str] = []
    for item in items:
        for key in item:
            if key not in columns:
                columns.append(key)
    rows = [{col: item.get(col, "") for col in columns} for item in items]
    return ParsedRows(columns=columns, rows=rows)


def parse_rows(filename: str, content: bytes, fmt: str | None = None) -> tuple[str, ParsedRows]:
    """Parse an upload into ``(format, ParsedRows)``. ``fmt`` overrides detection if given."""
    check_upload_size(content)
    detected = fmt or detect_format(filename, content)
    text = _decode(content)
    if detected == "csv":
        return "csv", _parse_csv(text)
    if detected == "json":
        return "json", _parse_json(text)
    if detected == "jsonl":
        return "jsonl", _parse_jsonl(text)
    raise ImportError_(f"Unsupported import format: {detected!r}")


def preview(filename: str, content: bytes) -> dict[str, Any]:
    """Build the ``ImportPreviewResponse`` payload: format, columns, first 10 rows, total_rows."""
    fmt, parsed = parse_rows(filename, content)
    return {
        "format": fmt,
        "columns": parsed.columns,
        "rows": parsed.rows[:10],
        "total_rows": len(parsed.rows),
    }


# --------------------------------------------------------------------------
# Commit: apply column -> variable mapping
# --------------------------------------------------------------------------


_VALID_EXPECTED_FORMATS = {"json", "python", "regex"}


def apply_mapping(
    parsed: ParsedRows,
    mapping: dict[str, str],
    *,
    solution_criteria_column: str | None = None,
    category_column: str | None = None,
    expected_format_column: str | None = None,
) -> list[dict[str, Any]]:
    """Turn parsed rows into test-case dicts ``{inputs, solution_criteria, category,
    expected_format}`` by applying the column -> variable ``mapping`` plus the optional
    metadata columns. Unmapped columns are ignored. Missing values become empty strings
    for mapped input columns."""
    cases: list[dict[str, Any]] = []
    for row in parsed.rows:
        inputs = {var_name: str(row.get(col, "") or "") for col, var_name in mapping.items()}
        solution_criteria = row.get(solution_criteria_column) if solution_criteria_column else None
        category = row.get(category_column) if category_column else None
        expected_format = row.get(expected_format_column) if expected_format_column else None
        if isinstance(expected_format, str):
            expected_format = expected_format.strip().lower() or None
            if expected_format not in _VALID_EXPECTED_FORMATS:
                expected_format = None
        else:
            expected_format = None
        cases.append(
            {
                "inputs": inputs,
                "solution_criteria": (solution_criteria or None),
                "category": (category or None),
                "expected_format": expected_format,
            }
        )
    return cases
