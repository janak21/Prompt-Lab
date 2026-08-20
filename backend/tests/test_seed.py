"""Tests for backend.app.seed: seeding into an empty DB, and idempotency."""

from __future__ import annotations

from backend.app import models, seed


def test_seed_creates_expected_objects(tmp_db):
    result = seed.seed()

    assert result["created"] is True

    prompts = models.list_prompts()
    assert len(prompts) == 1
    assert prompts[0]["name"] == seed.PROMPT_NAME

    versions = models.list_prompt_versions(prompts[0]["id"])
    assert len(versions) == 1
    assert "{{task}}" in versions[0]["template"]

    datasets = models.list_datasets()
    assert len(datasets) == 1
    assert datasets[0]["name"] == seed.DATASET_NAME

    cases = models.list_test_cases(datasets[0]["id"])
    assert len(cases) == 3
    formats = {c["expected_format"] for c in cases}
    assert formats == {"python", "json", "regex"}
    for case in cases:
        assert "task" in case["inputs"]
        assert case["solution_criteria"]

    graders = models.list_graders(prompts[0]["id"])
    assert len(graders) == 2
    by_type = {g["type"]: g for g in graders}
    assert by_type["llm_judge"]["weight"] == 2.0
    assert by_type["llm_judge"]["config"]["use_solution_criteria"] is True
    assert by_type["code_syntax"]["weight"] == 1.0
    assert by_type["code_syntax"]["config"]["format"] == "auto"

    # No run created -- seeding must never spend money.
    from backend.app import db

    with db.connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM run").fetchone()
    assert row["n"] == 0


def test_seed_is_idempotent(tmp_db):
    first = seed.seed()
    assert first["created"] is True

    second = seed.seed()
    assert second["created"] is False

    assert len(models.list_prompts()) == 1
    assert len(models.list_datasets()) == 1
    prompt = models.list_prompts()[0]
    assert len(models.list_test_cases(models.list_datasets()[0]["id"])) == 3
    assert len(models.list_graders(prompt["id"])) == 2


def test_seed_does_not_touch_unrelated_existing_data(tmp_db):
    """Seeding must never overwrite or duplicate the user's own pre-existing data."""
    user_prompt = models.create_prompt("My Own Prompt", description="user data")
    models.create_prompt_version(user_prompt["id"], "Hello {{name}}")

    result = seed.seed()
    assert result["created"] is True

    prompts = {p["name"] for p in models.list_prompts()}
    assert prompts == {"My Own Prompt", seed.PROMPT_NAME}


def test_already_seeded_detection(tmp_db):
    assert seed.already_seeded() is None
    seed.seed()
    found = seed.already_seeded()
    assert found is not None
    assert found["name"] == seed.PROMPT_NAME
