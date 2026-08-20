"""Seed a starting example drawn from the user's own source notebook.

The four ``001_prompt_evals*.ipynb`` notebooks in the parent directory (see
``docs/PLAN.md``) are what PromptLab grew out of: a single prompt that generates
Python/JSON/regex for AWS tasks, graded by an LLM judge ("expert AWS code reviewer")
averaged with a deterministic syntax check. This module recreates that as a real
PromptLab prompt + dataset + grader set, so a fresh clone has something useful to run
immediately instead of starting from a blank slate.

Run it directly:

    python -m backend.app.seed

or let ``run.sh`` invoke it automatically the first time the database is empty (see
``--seed`` / the auto-seed check in ``run.sh``).

**Idempotent and non-destructive.** It never touches existing data: it looks for a
prompt/dataset with the exact seed names first and, if found, leaves the database
alone (see :func:`already_seeded`). It never creates a ``run`` -- running costs money
and stays the user's explicit choice.
"""

from __future__ import annotations

from typing import Any

from . import models

PROMPT_NAME = "AWS Code Generator"
DATASET_NAME = "AWS Tasks (from dataset.json)"

# Ported from the notebook's `run_prompt` (see
# ../../../001_prompt_evals_complete.ipynb, the cell defining `run_prompt`), converted
# from an f-string embedding `test_case["task"]` to the `{{task}}` variable convention.
PROMPT_TEMPLATE = """Please solve the following task:

{{task}}

* Respond only with Python, JSON, or a plain Regex
* Do not add any comments or commentary or explanation
"""

# The notebook's `grade_by_model` rubric ("You are an expert AWS code reviewer...")
# reworded as a grader rubric. `use_solution_criteria=True` grounds the judge in each
# case's `solution_criteria`, mirroring the notebook's `<criteria>` block.
LLM_JUDGE_RUBRIC = """You are an expert AWS code reviewer. Evaluate the solution below for
correctness, completeness, and idiomatic quality as Python, JSON, or a regular
expression, whichever the task calls for.

Consider:
- Does it actually solve the stated task?
- Is it syntactically valid and idiomatic for its format?
- Does it meet the specific criteria given for this task?
- Would it work correctly on realistic AWS inputs, including edge cases?
"""

# The three AWS tasks from ../../../dataset.json, with `expected_format` and
# `solution_criteria` added -- the source file has only a bare `task` string per case.
SEED_CASES: list[dict[str, Any]] = [
    {
        "task": (
            "Write a Python function that extracts the AWS region from an S3 bucket URL "
            "in the format 's3://bucket-name.region.amazonaws.com'. The function should "
            "return just the region code (e.g., 'us-east-1')."
        ),
        "expected_format": "python",
        "solution_criteria": (
            "Defines a single Python function that takes the S3 URL string and returns "
            "only the region code (e.g. 'us-east-1'), correctly parsing the bucket name, "
            "region, and 'amazonaws.com' segments regardless of bucket-name length."
        ),
        "category": "standard",
    },
    {
        "task": (
            "Create a JSON object that represents an AWS IAM policy allowing read-only "
            "access to all objects in an S3 bucket named 'my-data-bucket'."
        ),
        "expected_format": "json",
        "solution_criteria": (
            "Valid IAM policy JSON with a '2012-10-17' Version, an Allow Statement "
            "restricted to read-only S3 actions (e.g. s3:GetObject, s3:ListBucket), and "
            "a Resource ARN scoped to the 'my-data-bucket' bucket and its objects."
        ),
        "category": "standard",
    },
    {
        "task": (
            "Write a regular expression that matches valid AWS EC2 instance IDs, which "
            "always start with 'i-' followed by 8 or 17 hexadecimal characters."
        ),
        "expected_format": "regex",
        "solution_criteria": (
            "A single regex pattern that matches 'i-' followed by exactly 8 or exactly "
            "17 lowercase hex characters, anchored so it does not also match invalid "
            "lengths or non-hex characters."
        ),
        "category": "standard",
    },
]


def already_seeded() -> dict[str, Any] | None:
    """Return the existing seed prompt's record if this database was already seeded."""
    for prompt in models.list_prompts():
        if prompt["name"] == PROMPT_NAME:
            return prompt
    return None


def seed() -> dict[str, Any]:
    """Create the seed prompt/dataset/graders if they don't already exist.

    Returns a summary dict describing what was created (or found already present).
    Never overwrites or duplicates existing data -- safe to call any number of times.
    """
    existing = already_seeded()
    if existing is not None:
        dataset = next((d for d in models.list_datasets() if d["name"] == DATASET_NAME), None)
        graders = models.list_graders(existing["id"])
        return {
            "created": False,
            "message": (
                f"Seed data already present (prompt '{PROMPT_NAME}' id={existing['id']}). "
                "Nothing changed."
            ),
            "prompt": existing,
            "dataset": dataset,
            "graders": graders,
        }

    prompt = models.create_prompt(
        PROMPT_NAME,
        description=(
            "Generates Python, JSON, or Regex for AWS tasks. Seeded from the original "
            "001_prompt_evals_complete.ipynb notebook this project grew out of."
        ),
    )
    version = models.create_prompt_version(
        prompt["id"],
        PROMPT_TEMPLATE,
        model="claude-haiku-4-5",
        notes="Seeded from the notebook's run_prompt.",
    )

    dataset = models.create_dataset(
        DATASET_NAME,
        description="The 3 AWS tasks from the original dataset.json, with expected_format and solution_criteria added.",
        source="imported",
    )
    cases = [
        models.create_test_case(
            dataset["id"],
            inputs={"task": case["task"]},
            solution_criteria=case["solution_criteria"],
            category=case["category"],
            expected_format=case["expected_format"],
        )
        for case in SEED_CASES
    ]

    llm_judge = models.create_grader(
        prompt["id"],
        "llm_judge",
        "Expert AWS Code Reviewer",
        {
            "rubric": LLM_JUDGE_RUBRIC,
            "use_solution_criteria": True,
        },
        weight=2.0,
        position=0,
    )
    code_syntax = models.create_grader(
        prompt["id"],
        "code_syntax",
        "Syntax Check",
        {"format": "auto"},
        weight=1.0,
        position=1,
    )

    return {
        "created": True,
        "message": (
            f"Seeded prompt '{PROMPT_NAME}' (id={prompt['id']}, version {version['version_no']}), "
            f"dataset '{DATASET_NAME}' (id={dataset['id']}) with {len(cases)} cases, and "
            f"2 graders (llm_judge weight=2, code_syntax weight=1). No run was created."
        ),
        "prompt": prompt,
        "version": version,
        "dataset": dataset,
        "cases": cases,
        "graders": [llm_judge, code_syntax],
    }


def main() -> None:
    from . import db

    db.init_db()
    result = seed()
    print(result["message"])


if __name__ == "__main__":
    main()
