"""Tests for backend.app.db and backend.app.models: schema creation, CRUD round-trips,
FK cascades, and JSON column helpers."""

from __future__ import annotations

import sqlite3

import pytest

from backend.app import db, models

pytestmark = pytest.mark.usefixtures("tmp_db")


def test_schema_creates_all_tables() -> None:
    with db.connection() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    names = {r["name"] for r in rows}
    expected = {"prompt", "prompt_version", "dataset", "test_case", "grader", "run", "run_case", "grade"}
    assert expected.issubset(names)


def test_init_db_idempotent() -> None:
    db.init_db()
    db.init_db()  # must not raise


def test_foreign_keys_pragma_on() -> None:
    with db.connection() as conn:
        row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row["foreign_keys"] == 1


def test_journal_mode_wal() -> None:
    with db.connection() as conn:
        row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row["journal_mode"].lower() == "wal"


def test_row_factory_returns_dicts() -> None:
    with db.connection() as conn:
        row = conn.execute("SELECT 1 AS one").fetchone()
    assert isinstance(row, dict)
    assert row["one"] == 1


class TestJsonHelpers:
    def test_roundtrip(self) -> None:
        value = {"a": 1, "b": ["x", "y"]}
        assert db.loads(db.dumps(value)) == value

    def test_loads_none(self) -> None:
        assert db.loads(None) is None


class TestPromptCrud:
    def test_create_and_get(self) -> None:
        prompt = models.create_prompt("Ticket triage", description="desc")
        assert prompt["id"] > 0
        assert prompt["name"] == "Ticket triage"
        fetched = models.get_prompt(prompt["id"])
        assert fetched == prompt

    def test_get_missing_returns_none(self) -> None:
        assert models.get_prompt(999999) is None

    def test_list_newest_first(self) -> None:
        p1 = models.create_prompt("first")
        p2 = models.create_prompt("second")
        listed = models.list_prompts()
        ids = [p["id"] for p in listed]
        assert ids.index(p2["id"]) < ids.index(p1["id"])

    def test_update(self) -> None:
        p = models.create_prompt("orig")
        updated = models.update_prompt(p["id"], name="renamed")
        assert updated is not None
        assert updated["name"] == "renamed"

    def test_delete(self) -> None:
        p = models.create_prompt("to delete")
        models.delete_prompt(p["id"])
        assert models.get_prompt(p["id"]) is None

    def test_delete_cascades_to_versions_and_graders(self) -> None:
        p = models.create_prompt("cascade test")
        v = models.create_prompt_version(p["id"], "template {{x}}")
        g = models.create_grader(p["id"], "code_syntax", "syntax", {"format": "json"})
        models.delete_prompt(p["id"])
        assert models.get_prompt_version(v["id"]) is None
        assert models.get_grader(g["id"]) is None


class TestPromptVersionCrud:
    def test_versions_auto_increment(self) -> None:
        p = models.create_prompt("versioned")
        v1 = models.create_prompt_version(p["id"], "t1")
        v2 = models.create_prompt_version(p["id"], "t2")
        assert v1["version_no"] == 1
        assert v2["version_no"] == 2

    def test_unique_constraint_per_prompt(self) -> None:
        p = models.create_prompt("uc")
        models.create_prompt_version(p["id"], "t1")
        # Directly forcing a duplicate version_no should violate the UNIQUE constraint.
        with db.connection(write=True) as conn, pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO prompt_version (prompt_id, version_no, template, created_at) "
                "VALUES (?, 1, 'dup', 'now')",
                (p["id"],),
            )

    def test_list_versions_ordered(self) -> None:
        p = models.create_prompt("list versions")
        models.create_prompt_version(p["id"], "t1")
        models.create_prompt_version(p["id"], "t2")
        versions = models.list_prompt_versions(p["id"])
        assert [v["version_no"] for v in versions] == [1, 2]

    def test_latest_prompt_version(self) -> None:
        p = models.create_prompt("latest")
        models.create_prompt_version(p["id"], "t1")
        v2 = models.create_prompt_version(p["id"], "t2")
        assert models.latest_prompt_version(p["id"])["id"] == v2["id"]

    def test_latest_none_when_no_versions(self) -> None:
        p = models.create_prompt("no versions")
        assert models.latest_prompt_version(p["id"]) is None


class TestDatasetCrud:
    def test_create_and_get(self) -> None:
        d = models.create_dataset("My dataset", source="manual")
        assert d["source"] == "manual"
        assert models.get_dataset(d["id"]) == d

    def test_update(self) -> None:
        d = models.create_dataset("orig")
        updated = models.update_dataset(d["id"], description="new desc")
        assert updated["description"] == "new desc"

    def test_delete_cascades_to_test_cases(self) -> None:
        d = models.create_dataset("cascade")
        tc = models.create_test_case(d["id"], {"x": "1"})
        models.delete_dataset(d["id"])
        assert models.get_test_case(tc["id"]) is None


class TestTestCaseCrud:
    def test_create_decodes_inputs(self) -> None:
        d = models.create_dataset("ds")
        tc = models.create_test_case(
            d["id"], {"ticket_text": "help", "tier": "gold"}, category="standard"
        )
        assert tc["inputs"] == {"ticket_text": "help", "tier": "gold"}
        assert tc["category"] == "standard"
        fetched = models.get_test_case(tc["id"])
        assert fetched["inputs"] == {"ticket_text": "help", "tier": "gold"}

    def test_list_in_insertion_order(self) -> None:
        d = models.create_dataset("ds2")
        tc1 = models.create_test_case(d["id"], {"a": "1"})
        tc2 = models.create_test_case(d["id"], {"a": "2"})
        listed = models.list_test_cases(d["id"])
        assert [c["id"] for c in listed] == [tc1["id"], tc2["id"]]

    def test_update_inputs(self) -> None:
        d = models.create_dataset("ds3")
        tc = models.create_test_case(d["id"], {"a": "1"})
        updated = models.update_test_case(tc["id"], inputs={"a": "2"})
        assert updated["inputs"] == {"a": "2"}

    def test_delete(self) -> None:
        d = models.create_dataset("ds4")
        tc = models.create_test_case(d["id"], {"a": "1"})
        models.delete_test_case(tc["id"])
        assert models.get_test_case(tc["id"]) is None


class TestGraderCrud:
    def test_create_decodes_config_and_enabled(self) -> None:
        p = models.create_prompt("graded prompt")
        g = models.create_grader(
            p["id"], "llm_judge", "quality", {"rubric": "be nice", "use_solution_criteria": True}
        )
        assert g["config"] == {"rubric": "be nice", "use_solution_criteria": True}
        assert g["enabled"] is True

    def test_update_config(self) -> None:
        p = models.create_prompt("p")
        g = models.create_grader(p["id"], "budget", "cost cap", {"max_cost_usd": 0.1})
        updated = models.update_grader(g["id"], config={"max_cost_usd": 0.5})
        assert updated["config"] == {"max_cost_usd": 0.5}

    def test_list_ordered_by_position(self) -> None:
        p = models.create_prompt("p2")
        g2 = models.create_grader(p["id"], "code_syntax", "b", {"format": "json"}, position=2)
        g1 = models.create_grader(p["id"], "code_syntax", "a", {"format": "json"}, position=1)
        listed = models.list_graders(p["id"])
        assert [g["id"] for g in listed] == [g1["id"], g2["id"]]

    def test_delete(self) -> None:
        p = models.create_prompt("p3")
        g = models.create_grader(p["id"], "code_syntax", "c", {"format": "json"})
        models.delete_grader(g["id"])
        assert models.get_grader(g["id"]) is None


class TestRunAndRunCaseAndGrade:
    def _setup_run(self) -> tuple[dict, dict, dict]:
        p = models.create_prompt("run prompt")
        v = models.create_prompt_version(p["id"], "hi {{x}}")
        d = models.create_dataset("run dataset")
        run = models.create_run(
            v["id"],
            d["id"],
            model="claude-haiku-4-5",
            temperature=1.0,
            max_tokens=1000,
            judge_model="claude-sonnet-5",
            concurrency=5,
            grader_snapshot=[{"type": "code_syntax", "name": "s", "weight": 1.0, "config": {"format": "json"}}],
        )
        return p, v, run

    def test_create_run_decodes_snapshot(self) -> None:
        _, _, run = self._setup_run()
        assert run["status"] == "pending"
        assert run["grader_snapshot"][0]["type"] == "code_syntax"

    def test_update_run(self) -> None:
        _, _, run = self._setup_run()
        updated = models.update_run(run["id"], status="running", started_at="2026-01-01T00:00:00")
        assert updated["status"] == "running"
        assert updated["started_at"] == "2026-01-01T00:00:00"

    def test_list_runs_filters_by_dataset(self) -> None:
        _, _, run = self._setup_run()
        listed = models.list_runs(dataset_id=run["dataset_id"])
        assert run["id"] in [r["id"] for r in listed]
        assert models.list_runs(dataset_id=999999) == []

    def test_list_runs_filters_by_prompt(self) -> None:
        p, _, run = self._setup_run()
        listed = models.list_runs(prompt_id=p["id"])
        assert run["id"] in [r["id"] for r in listed]

    def test_run_case_and_grade_roundtrip(self) -> None:
        p = models.create_prompt("rc prompt")
        d = models.create_dataset("rc dataset")
        tc = models.create_test_case(d["id"], {"x": "1"})
        _, _, run = self._setup_run()
        rc = models.create_run_case(run["id"], tc["id"], 0)
        assert rc["status"] == "pending"

        updated_rc = models.update_run_case(rc["id"], status="completed", output="hello", final_score=8.5)
        assert updated_rc["output"] == "hello"
        assert updated_rc["final_score"] == 8.5

        grade = models.create_grade(
            rc["id"], "syntax", "code_syntax", 10.0, 1.0, reasoning="valid json", details={"ok": True}
        )
        assert grade["details"] == {"ok": True}
        grades = models.list_grades(rc["id"])
        assert len(grades) == 1
        assert grades[0]["grader_name"] == "syntax"

    def test_delete_run_cascades_to_run_case_and_grade(self) -> None:
        p = models.create_prompt("cascade run prompt")
        d = models.create_dataset("cascade run dataset")
        tc = models.create_test_case(d["id"], {"x": "1"})
        _, _, run = self._setup_run()
        rc = models.create_run_case(run["id"], tc["id"], 0)
        grade = models.create_grade(rc["id"], "g", "budget", 10.0, 1.0)

        models.delete_run(run["id"])

        assert models.get_run_case(rc["id"]) is None
        assert models.get_grade(grade["id"]) is None

    def test_deleting_dataset_does_not_delete_run(self) -> None:
        """Invariant 5 in DATA_MODEL.md: deleting a dataset must not delete its runs."""
        p, v, run = self._setup_run()
        models.delete_dataset(run["dataset_id"])
        assert models.get_run(run["id"]) is not None

    def test_deleting_prompt_does_not_delete_run(self) -> None:
        """Invariant 5 in DATA_MODEL.md: deleting a prompt must not delete its runs."""
        p, v, run = self._setup_run()
        models.delete_prompt(p["id"])
        assert models.get_run(run["id"]) is not None
