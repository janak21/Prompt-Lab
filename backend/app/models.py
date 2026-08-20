"""Thin, typed data-access layer over the SQLite schema defined in :mod:`.db`.

Every function opens its own connection via :func:`db.connection` (write=True for
mutations) and returns plain ``dict`` rows (JSON columns already decoded). This module
intentionally has no framework dependencies so it can be imported from routers,
background tasks, and tests alike.

Column names and enum values match ``docs/DATA_MODEL.md`` exactly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import db


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string (used for all ``created_at`` etc.)."""
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------
# prompt
# --------------------------------------------------------------------------


def create_prompt(name: str, description: str | None = None) -> dict[str, Any]:
    """Insert a new ``prompt`` row and return it."""
    created_at = utcnow_iso()
    with db.connection(write=True) as conn:
        cur = conn.execute(
            "INSERT INTO prompt (name, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, description, created_at, created_at),
        )
        row = conn.execute("SELECT * FROM prompt WHERE id = ?", (cur.lastrowid,)).fetchone()
        return db.row_to_dict(row)  # type: ignore[return-value]


def get_prompt(prompt_id: int) -> dict[str, Any] | None:
    """Fetch a single ``prompt`` row by id, or None."""
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM prompt WHERE id = ?", (prompt_id,)).fetchone()
        return db.row_to_dict(row)


def list_prompts() -> list[dict[str, Any]]:
    """List all prompts, newest first."""
    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM prompt ORDER BY id DESC").fetchall()
        return db.rows_to_dicts(rows)


def update_prompt(prompt_id: int, *, name: str | None = None, description: str | None = None) -> dict[str, Any] | None:
    """Patch ``name``/``description`` on a prompt (only fields explicitly passed are changed).

    Bumps ``updated_at`` whenever a field actually changes.
    """
    fields: list[str] = []
    values: list[Any] = []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if not fields:
        return get_prompt(prompt_id)
    fields.append("updated_at = ?")
    values.append(utcnow_iso())
    values.append(prompt_id)
    with db.connection(write=True) as conn:
        conn.execute(f"UPDATE prompt SET {', '.join(fields)} WHERE id = ?", values)
    return get_prompt(prompt_id)


def delete_prompt(prompt_id: int) -> None:
    """Delete a prompt. Cascades to ``prompt_version`` and ``grader`` rows."""
    with db.connection(write=True) as conn:
        conn.execute("DELETE FROM prompt WHERE id = ?", (prompt_id,))


# --------------------------------------------------------------------------
# prompt_version  (immutable -- no update function)
# --------------------------------------------------------------------------


def create_prompt_version(
    prompt_id: int,
    template: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Insert the next version for a prompt (auto-incrementing ``version_no``).

    Also bumps the parent prompt's ``updated_at`` -- this is the primary way a prompt's
    ``updated_at`` changes, since the whole workflow is iterating on a prompt via new
    versions.
    """
    created_at = utcnow_iso()
    with db.connection(write=True) as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version_no), 0) AS max_v FROM prompt_version WHERE prompt_id = ?",
            (prompt_id,),
        ).fetchone()
        next_version = row["max_v"] + 1
        cur = conn.execute(
            """INSERT INTO prompt_version
               (prompt_id, version_no, template, system_prompt, model, temperature, max_tokens, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (prompt_id, next_version, template, system_prompt, model, temperature, max_tokens, notes, created_at),
        )
        new_id = cur.lastrowid
        conn.execute("UPDATE prompt SET updated_at = ? WHERE id = ?", (created_at, prompt_id))
    return get_prompt_version(new_id)  # type: ignore[arg-type,return-value]


def get_prompt_version(version_id: int) -> dict[str, Any] | None:
    """Fetch a single ``prompt_version`` row by id, or None."""
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM prompt_version WHERE id = ?", (version_id,)).fetchone()
        return db.row_to_dict(row)


def list_prompt_versions(prompt_id: int) -> list[dict[str, Any]]:
    """List all versions of a prompt, oldest first."""
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM prompt_version WHERE prompt_id = ? ORDER BY version_no ASC", (prompt_id,)
        ).fetchall()
        return db.rows_to_dicts(rows)


def latest_prompt_version(prompt_id: int) -> dict[str, Any] | None:
    """Fetch the highest-``version_no`` version for a prompt, or None if it has none."""
    with db.connection() as conn:
        row = conn.execute(
            "SELECT * FROM prompt_version WHERE prompt_id = ? ORDER BY version_no DESC LIMIT 1",
            (prompt_id,),
        ).fetchone()
        return db.row_to_dict(row)


# --------------------------------------------------------------------------
# dataset
# --------------------------------------------------------------------------


def create_dataset(name: str, *, description: str | None = None, source: str = "manual") -> dict[str, Any]:
    """Insert a new ``dataset`` row. ``source`` is one of generated|manual|imported."""
    created_at = utcnow_iso()
    with db.connection(write=True) as conn:
        cur = conn.execute(
            "INSERT INTO dataset (name, description, source, created_at) VALUES (?, ?, ?, ?)",
            (name, description, source, created_at),
        )
        new_id = cur.lastrowid
    return get_dataset(new_id)  # type: ignore[arg-type,return-value]


def get_dataset(dataset_id: int) -> dict[str, Any] | None:
    """Fetch a single ``dataset`` row by id, or None."""
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM dataset WHERE id = ?", (dataset_id,)).fetchone()
        return db.row_to_dict(row)


def list_datasets() -> list[dict[str, Any]]:
    """List all datasets, newest first."""
    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM dataset ORDER BY id DESC").fetchall()
        return db.rows_to_dicts(rows)


def update_dataset(dataset_id: int, *, name: str | None = None, description: str | None = None) -> dict[str, Any] | None:
    """Patch ``name``/``description`` on a dataset."""
    fields: list[str] = []
    values: list[Any] = []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if not fields:
        return get_dataset(dataset_id)
    values.append(dataset_id)
    with db.connection(write=True) as conn:
        conn.execute(f"UPDATE dataset SET {', '.join(fields)} WHERE id = ?", values)
    return get_dataset(dataset_id)


def delete_dataset(dataset_id: int) -> None:
    """Delete a dataset. Cascades to ``test_case`` rows."""
    with db.connection(write=True) as conn:
        conn.execute("DELETE FROM dataset WHERE id = ?", (dataset_id,))


# --------------------------------------------------------------------------
# test_case
# --------------------------------------------------------------------------


def _decode_test_case(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row = dict(row)
    row["inputs"] = db.loads(row.pop("inputs_json"))
    return row


def create_test_case(
    dataset_id: int,
    inputs: dict[str, str],
    *,
    solution_criteria: str | None = None,
    category: str | None = None,
    expected_format: str | None = None,
) -> dict[str, Any]:
    """Insert a new ``test_case`` row. ``inputs`` is stored JSON-encoded."""
    created_at = utcnow_iso()
    with db.connection(write=True) as conn:
        cur = conn.execute(
            """INSERT INTO test_case
               (dataset_id, inputs_json, solution_criteria, category, expected_format, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (dataset_id, db.dumps(inputs), solution_criteria, category, expected_format, created_at),
        )
        new_id = cur.lastrowid
    return get_test_case(new_id)  # type: ignore[arg-type,return-value]


def get_test_case(test_case_id: int) -> dict[str, Any] | None:
    """Fetch a single ``test_case`` row (with ``inputs`` decoded), or None."""
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM test_case WHERE id = ?", (test_case_id,)).fetchone()
        return _decode_test_case(row)


def list_test_cases(dataset_id: int) -> list[dict[str, Any]]:
    """List all test cases in a dataset, in insertion order."""
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM test_case WHERE dataset_id = ? ORDER BY id ASC", (dataset_id,)
        ).fetchall()
        return [d for r in rows if (d := _decode_test_case(r)) is not None]


def update_test_case(
    test_case_id: int,
    *,
    inputs: dict[str, str] | None = None,
    solution_criteria: str | None = None,
    category: str | None = None,
    expected_format: str | None = None,
) -> dict[str, Any] | None:
    """Patch any subset of a test case's fields."""
    fields: list[str] = []
    values: list[Any] = []
    if inputs is not None:
        fields.append("inputs_json = ?")
        values.append(db.dumps(inputs))
    if solution_criteria is not None:
        fields.append("solution_criteria = ?")
        values.append(solution_criteria)
    if category is not None:
        fields.append("category = ?")
        values.append(category)
    if expected_format is not None:
        fields.append("expected_format = ?")
        values.append(expected_format)
    if not fields:
        return get_test_case(test_case_id)
    values.append(test_case_id)
    with db.connection(write=True) as conn:
        conn.execute(f"UPDATE test_case SET {', '.join(fields)} WHERE id = ?", values)
    return get_test_case(test_case_id)


def delete_test_case(test_case_id: int) -> None:
    """Delete a single test case."""
    with db.connection(write=True) as conn:
        conn.execute("DELETE FROM test_case WHERE id = ?", (test_case_id,))


# --------------------------------------------------------------------------
# grader
# --------------------------------------------------------------------------


def _decode_grader(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row = dict(row)
    row["config"] = db.loads(row.pop("config_json"))
    row["enabled"] = bool(row["enabled"])
    return row


def create_grader(
    prompt_id: int,
    type: str,
    name: str,
    config: dict[str, Any],
    *,
    weight: float = 1.0,
    enabled: bool = True,
    position: int = 0,
) -> dict[str, Any]:
    """Insert a new ``grader`` row for a prompt."""
    with db.connection(write=True) as conn:
        cur = conn.execute(
            """INSERT INTO grader (prompt_id, type, name, weight, config_json, enabled, position)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (prompt_id, type, name, weight, db.dumps(config), int(enabled), position),
        )
        new_id = cur.lastrowid
    return get_grader(new_id)  # type: ignore[arg-type,return-value]


def get_grader(grader_id: int) -> dict[str, Any] | None:
    """Fetch a single ``grader`` row (with ``config`` decoded), or None."""
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM grader WHERE id = ?", (grader_id,)).fetchone()
        return _decode_grader(row)


def list_graders(prompt_id: int) -> list[dict[str, Any]]:
    """List all graders for a prompt, ordered by ``position``."""
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM grader WHERE prompt_id = ? ORDER BY position ASC, id ASC", (prompt_id,)
        ).fetchall()
        return [d for r in rows if (d := _decode_grader(r)) is not None]


def update_grader(
    grader_id: int,
    *,
    name: str | None = None,
    weight: float | None = None,
    config: dict[str, Any] | None = None,
    enabled: bool | None = None,
    position: int | None = None,
) -> dict[str, Any] | None:
    """Patch any subset of a grader's mutable fields."""
    fields: list[str] = []
    values: list[Any] = []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if weight is not None:
        fields.append("weight = ?")
        values.append(weight)
    if config is not None:
        fields.append("config_json = ?")
        values.append(db.dumps(config))
    if enabled is not None:
        fields.append("enabled = ?")
        values.append(int(enabled))
    if position is not None:
        fields.append("position = ?")
        values.append(position)
    if not fields:
        return get_grader(grader_id)
    values.append(grader_id)
    with db.connection(write=True) as conn:
        conn.execute(f"UPDATE grader SET {', '.join(fields)} WHERE id = ?", values)
    return get_grader(grader_id)


def delete_grader(grader_id: int) -> None:
    """Delete a single grader."""
    with db.connection(write=True) as conn:
        conn.execute("DELETE FROM grader WHERE id = ?", (grader_id,))


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------


def _decode_run(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row = dict(row)
    row["grader_snapshot"] = db.loads(row.pop("grader_snapshot_json"))
    return row


def create_run(
    prompt_version_id: int,
    dataset_id: int,
    *,
    model: str,
    temperature: float,
    max_tokens: int,
    judge_model: str,
    concurrency: int,
    grader_snapshot: list[dict[str, Any]],
    status: str = "pending",
) -> dict[str, Any]:
    """Insert a new ``run`` row. ``status`` is one of pending|running|completed|failed|cancelled."""
    created_at = utcnow_iso()
    with db.connection(write=True) as conn:
        cur = conn.execute(
            """INSERT INTO run
               (prompt_version_id, dataset_id, model, temperature, max_tokens, judge_model,
                concurrency, grader_snapshot_json, status, started_at, finished_at, avg_score,
                total_cost, error, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?)""",
            (
                prompt_version_id,
                dataset_id,
                model,
                temperature,
                max_tokens,
                judge_model,
                concurrency,
                db.dumps(grader_snapshot),
                status,
                created_at,
            ),
        )
        new_id = cur.lastrowid
    return get_run(new_id)  # type: ignore[arg-type,return-value]


def get_run(run_id: int) -> dict[str, Any] | None:
    """Fetch a single ``run`` row (with ``grader_snapshot`` decoded), or None."""
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
        return _decode_run(row)


def list_runs(*, prompt_id: int | None = None, dataset_id: int | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    """List runs, newest first. ``prompt_id`` filters via a join through ``prompt_version``."""
    query = "SELECT run.* FROM run"
    conditions: list[str] = []
    values: list[Any] = []
    if prompt_id is not None:
        query += " JOIN prompt_version ON prompt_version.id = run.prompt_version_id"
        conditions.append("prompt_version.prompt_id = ?")
        values.append(prompt_id)
    if dataset_id is not None:
        conditions.append("run.dataset_id = ?")
        values.append(dataset_id)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY run.id DESC"
    if limit is not None:
        query += " LIMIT ?"
        values.append(limit)
    with db.connection() as conn:
        rows = conn.execute(query, values).fetchall()
        return [d for r in rows if (d := _decode_run(r)) is not None]


def update_run(run_id: int, **fields: Any) -> dict[str, Any] | None:
    """Patch arbitrary columns on a run (e.g. status, started_at, avg_score, total_cost, error).

    ``grader_snapshot`` (if passed) is JSON-encoded automatically into ``grader_snapshot_json``.
    """
    if "grader_snapshot" in fields:
        fields["grader_snapshot_json"] = db.dumps(fields.pop("grader_snapshot"))
    if not fields:
        return get_run(run_id)
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = [*fields.values(), run_id]
    with db.connection(write=True) as conn:
        conn.execute(f"UPDATE run SET {set_clause} WHERE id = ?", values)
    return get_run(run_id)


def delete_run(run_id: int) -> None:
    """Delete a run. Cascades to ``run_case`` (and thence ``grade``) rows."""
    with db.connection(write=True) as conn:
        conn.execute("DELETE FROM run WHERE id = ?", (run_id,))


# --------------------------------------------------------------------------
# run_case
# --------------------------------------------------------------------------


def create_run_case(
    run_id: int,
    test_case_id: int,
    idx: int,
    *,
    status: str = "pending",
) -> dict[str, Any]:
    """Insert a new ``run_case`` row (typically all cases are created up-front as ``pending``)."""
    with db.connection(write=True) as conn:
        cur = conn.execute(
            "INSERT INTO run_case (run_id, test_case_id, idx, status) VALUES (?, ?, ?, ?)",
            (run_id, test_case_id, idx, status),
        )
        new_id = cur.lastrowid
    return get_run_case(new_id)  # type: ignore[arg-type,return-value]


def get_run_case(run_case_id: int) -> dict[str, Any] | None:
    """Fetch a single ``run_case`` row by id, or None."""
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM run_case WHERE id = ?", (run_case_id,)).fetchone()
        return db.row_to_dict(row)


def list_run_cases(run_id: int) -> list[dict[str, Any]]:
    """List all cases for a run, ordered by ``idx``."""
    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM run_case WHERE run_id = ? ORDER BY idx ASC", (run_id,)).fetchall()
        return db.rows_to_dicts(rows)


def update_run_case(run_case_id: int, **fields: Any) -> dict[str, Any] | None:
    """Patch arbitrary columns on a run_case (output, latency_ms, tokens, cost, status, ...)."""
    if not fields:
        return get_run_case(run_case_id)
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = [*fields.values(), run_case_id]
    with db.connection(write=True) as conn:
        conn.execute(f"UPDATE run_case SET {set_clause} WHERE id = ?", values)
    return get_run_case(run_case_id)


# --------------------------------------------------------------------------
# grade
# --------------------------------------------------------------------------


def _decode_grade(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row = dict(row)
    row["details"] = db.loads(row.pop("details_json"))
    return row


def create_grade(
    run_case_id: int,
    grader_name: str,
    grader_type: str,
    score: float,
    weight: float,
    *,
    reasoning: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert a new ``grade`` row for a run_case."""
    with db.connection(write=True) as conn:
        cur = conn.execute(
            """INSERT INTO grade (run_case_id, grader_name, grader_type, score, weight, reasoning, details_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_case_id, grader_name, grader_type, score, weight, reasoning, db.dumps(details) if details is not None else None),
        )
        new_id = cur.lastrowid
    return get_grade(new_id)  # type: ignore[arg-type,return-value]


def get_grade(grade_id: int) -> dict[str, Any] | None:
    """Fetch a single ``grade`` row by id, or None."""
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM grade WHERE id = ?", (grade_id,)).fetchone()
        return _decode_grade(row)


def list_grades(run_case_id: int) -> list[dict[str, Any]]:
    """List all grades for a run_case."""
    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM grade WHERE run_case_id = ? ORDER BY id ASC", (run_case_id,)).fetchall()
        return [d for r in rows if (d := _decode_grade(r)) is not None]
