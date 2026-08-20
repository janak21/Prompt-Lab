# PromptLab — Data Model (FROZEN)

SQLite, file at `promptlab/promptlab.db` (override with `PROMPTLAB_DB`). Created on startup via
`CREATE TABLE IF NOT EXISTS`. All timestamps are ISO-8601 UTC strings. All `*_json` columns are TEXT
holding JSON. Foreign keys ON, cascading deletes as noted.

## prompt
| col | type | notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NOT NULL | |
| description | TEXT | |
| created_at | TEXT NOT NULL | |

## prompt_version  — IMMUTABLE, never UPDATE
| id | INTEGER PK |
| prompt_id | INTEGER FK -> prompt.id ON DELETE CASCADE |
| version_no | INTEGER NOT NULL | 1-based, unique per prompt |
| template | TEXT NOT NULL | contains `{{variable}}` placeholders |
| system_prompt | TEXT NULL |
| model | TEXT NULL | falls back to settings default |
| temperature | REAL NULL |
| max_tokens | INTEGER NULL |
| notes | TEXT NULL | "what changed" |
| created_at | TEXT NOT NULL |

UNIQUE(prompt_id, version_no)

## dataset
| id | INTEGER PK |
| name | TEXT NOT NULL |
| description | TEXT |
| source | TEXT NOT NULL | `generated` \| `manual` \| `imported` |
| created_at | TEXT NOT NULL |

## test_case
| id | INTEGER PK |
| dataset_id | INTEGER FK -> dataset.id ON DELETE CASCADE |
| inputs_json | TEXT NOT NULL | object mapping variable name -> string value |
| solution_criteria | TEXT NULL | fed to the llm_judge grader |
| category | TEXT NULL | e.g. `standard`, `empty_input`, `prompt_injection`, `boundary` |
| expected_format | TEXT NULL | `json` \| `python` \| `regex` \| NULL — used by code_syntax `auto` |
| created_at | TEXT NOT NULL |

## grader  — belongs to a prompt, snapshotted into each run
| id | INTEGER PK |
| prompt_id | INTEGER FK -> prompt.id ON DELETE CASCADE |
| type | TEXT NOT NULL | `llm_judge` \| `code_syntax` \| `string_match` \| `json_schema` \| `budget` |
| name | TEXT NOT NULL | display label, unique per prompt |
| weight | REAL NOT NULL DEFAULT 1.0 | |
| config_json | TEXT NOT NULL | shape per type, see API_CONTRACT.md |
| enabled | INTEGER NOT NULL DEFAULT 1 |
| position | INTEGER NOT NULL DEFAULT 0 |

## run
| id | INTEGER PK |
| prompt_version_id | INTEGER FK -> prompt_version.id |
| dataset_id | INTEGER FK -> dataset.id |
| model | TEXT NOT NULL |
| temperature | REAL NOT NULL |
| max_tokens | INTEGER NOT NULL |
| judge_model | TEXT NOT NULL |
| concurrency | INTEGER NOT NULL |
| grader_snapshot_json | TEXT NOT NULL | array of resolved grader defs at launch time |
| status | TEXT NOT NULL | `pending` \| `running` \| `completed` \| `failed` \| `cancelled` |
| started_at | TEXT NULL | finished_at TEXT NULL |
| avg_score | REAL NULL |
| total_cost | REAL NULL |
| error | TEXT NULL |
| created_at | TEXT NOT NULL |

## run_case
| id | INTEGER PK |
| run_id | INTEGER FK -> run.id ON DELETE CASCADE |
| test_case_id | INTEGER FK -> test_case.id |
| idx | INTEGER NOT NULL | stable ordering |
| rendered_prompt | TEXT NULL |
| output | TEXT NULL |
| latency_ms | INTEGER NULL |
| input_tokens | INTEGER NULL | output_tokens INTEGER NULL |
| cost | REAL NULL |
| final_score | REAL NULL | weighted 0-10 |
| status | TEXT NOT NULL | `pending` \| `running` \| `completed` \| `failed` |
| error | TEXT NULL |

## grade
| id | INTEGER PK |
| run_case_id | INTEGER FK -> run_case.id ON DELETE CASCADE |
| grader_name | TEXT NOT NULL | grader_type TEXT NOT NULL |
| score | REAL NOT NULL | 0-10 |
| weight | REAL NOT NULL |
| reasoning | TEXT NULL |
| details_json | TEXT NULL |

## Invariants
1. `prompt_version` rows are append-only. Editing a prompt creates a new version.
2. A run NEVER reads live `grader` rows — it reads `run.grader_snapshot_json`. Historical runs stay
   reproducible when graders change.
3. `run_case.final_score` = sum(grade.score * grade.weight) / sum(grade.weight), 0-10, NULL if the
   case failed before grading.
4. `run.avg_score` = mean of non-NULL `run_case.final_score`.
5. Deleting a dataset or prompt does NOT delete runs; runs keep their snapshot and denormalized data.
   Run detail endpoints must tolerate a missing parent dataset/prompt.
