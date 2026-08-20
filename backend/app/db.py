"""SQLite data-access layer.

Concurrency model
------------------
We use the stdlib ``sqlite3`` module directly (no ORM), matching the frozen spec. SQLite
connections are not safe to share across threads by default, and FastAPI runs sync code
(including background tasks) in a thread pool while async endpoints run on the event
loop -- so a single shared connection would be unsafe, and a naive "one connection per
process" approach would break under FastAPI's threading model.

The approach taken here: **one short-lived connection per operation** (opened with
``check_same_thread=False`` so it can be created in one thread and used synchronously
within the same call), created via :func:`get_connection`, always used as a context
manager so it is closed promptly. SQLite's own file-level locking combined with WAL mode
(``PRAGMA journal_mode=WAL``) lets multiple readers proceed concurrently while a writer
is active; to avoid "database is locked" errors under FastAPI's threaded execution of
sync background tasks, all *write* operations additionally take a process-wide
``threading.Lock`` (:data:`_WRITE_LOCK`) so only one write transaction runs at a time.
Reads do not take the lock -- WAL allows concurrent readers alongside a writer. A
``busy_timeout`` PRAGMA is also set as a defence-in-depth measure so a connection that
does contend for the lock waits briefly instead of failing immediately.

This is simple, correct for a single-process local tool (the deployment target for
PromptLab), and avoids the complexity of a connection pool or an async SQLite driver.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from .config import settings

_WRITE_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS prompt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS prompt_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL REFERENCES prompt(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    template TEXT NOT NULL,
    system_prompt TEXT,
    model TEXT,
    temperature REAL,
    max_tokens INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (prompt_id, version_no)
);

CREATE TABLE IF NOT EXISTS dataset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_case (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES dataset(id) ON DELETE CASCADE,
    inputs_json TEXT NOT NULL,
    solution_criteria TEXT,
    category TEXT,
    expected_format TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grader (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL REFERENCES prompt(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    config_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- prompt_version_id / dataset_id are intentionally NOT enforced foreign keys: per
    -- DATA_MODEL.md invariant 5, deleting a prompt (and its versions) or a dataset must
    -- NOT delete or block deletion of runs that reference them -- runs keep their
    -- grader_snapshot_json and denormalized data and become orphan-tolerant instead.
    prompt_version_id INTEGER NOT NULL,
    dataset_id INTEGER NOT NULL,
    model TEXT NOT NULL,
    temperature REAL NOT NULL,
    max_tokens INTEGER NOT NULL,
    judge_model TEXT NOT NULL,
    concurrency INTEGER NOT NULL,
    grader_snapshot_json TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    avg_score REAL,
    total_cost REAL,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_case (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    -- test_case_id is intentionally NOT an enforced foreign key, for the same reason as
    -- run.dataset_id above: deleting the parent dataset (which cascades to test_case)
    -- must not be blocked by, or cascade to, historical run_case rows.
    test_case_id INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    rendered_prompt TEXT,
    output TEXT,
    latency_ms INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost REAL,
    final_score REAL,
    status TEXT NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS grade (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_case_id INTEGER NOT NULL REFERENCES run_case(id) ON DELETE CASCADE,
    grader_name TEXT NOT NULL,
    grader_type TEXT NOT NULL,
    score REAL NOT NULL,
    weight REAL NOT NULL,
    reasoning TEXT,
    details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_prompt_version_prompt_id ON prompt_version(prompt_id);
CREATE INDEX IF NOT EXISTS idx_test_case_dataset_id ON test_case(dataset_id);
CREATE INDEX IF NOT EXISTS idx_grader_prompt_id ON grader(prompt_id);
CREATE INDEX IF NOT EXISTS idx_run_case_run_id ON run_case(run_id);
CREATE INDEX IF NOT EXISTS idx_grade_run_case_id ON grade(run_case_id);
"""


def _dict_row_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    fields = [col[0] for col in cursor.description]
    return dict(zip(fields, row))


def get_connection() -> sqlite3.Connection:
    """Open a new short-lived SQLite connection with the project's standard pragmas.

    Callers are responsible for closing the connection (prefer :func:`connection` as a
    context manager). Safe to call from any thread -- ``check_same_thread=False`` is set
    because FastAPI may create/use connections from worker threads, but each connection
    returned here is only ever used by the single call site that created it.
    """
    db_path = settings.db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
    conn.row_factory = _dict_row_factory
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def connection(*, write: bool = False) -> Iterator[sqlite3.Connection]:
    """Context manager yielding a connection for a single operation.

    Pass ``write=True`` for any operation that mutates data -- this serializes writers
    process-wide via :data:`_WRITE_LOCK` (see module docstring) and commits on success /
    rolls back on exception. Read-only operations skip the lock so concurrent reads are
    not serialized.
    """
    if write:
        with _WRITE_LOCK:
            conn = get_connection()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
    else:
        conn = get_connection()
        try:
            yield conn
        finally:
            conn.close()


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply idempotent, additive schema migrations for databases created before a column
    existed.

    ``CREATE TABLE IF NOT EXISTS`` (see :data:`SCHEMA`) only creates a table the first
    time -- it does NOT alter an existing table's columns. A returning user with a real
    ``promptlab.db`` predating a schema change would otherwise hit "no such column"
    errors. Each migration here is guarded by a ``PRAGMA table_info`` check so it is
    a no-op (and safe to re-run) once applied.
    """
    prompt_columns = _column_names(conn, "prompt")
    if "updated_at" not in prompt_columns:
        conn.execute("ALTER TABLE prompt ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        # Backfill existing rows so `updated_at` reflects reality instead of ''
        # (which would otherwise sort before every real timestamp).
        conn.execute("UPDATE prompt SET updated_at = created_at WHERE updated_at = ''")


def init_db() -> None:
    """Create all tables (and indexes) if they do not already exist, then apply any
    pending additive migrations. Safe to call repeatedly."""
    with connection(write=True) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


# --------------------------------------------------------------------------
# JSON column helpers
# --------------------------------------------------------------------------


def dumps(value: Any) -> str:
    """Encode a Python value to a JSON string for storage in a ``*_json`` column."""
    return json.dumps(value)


def loads(value: str | None) -> Any:
    """Decode a ``*_json`` column value. Returns ``None`` unchanged."""
    if value is None:
        return None
    return json.loads(value)


def row_to_dict(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize a row (already a dict, given the row_factory) to a plain dict, or None."""
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows: Iterable[Any]) -> list[dict[str, Any]]:
    """Normalize an iterable of rows to a list of plain dicts."""
    return [dict(r) for r in rows]
