# PromptLab — Data Model (FROZEN)

SQLite, file at `promptlab/promptlab.db` (override with `PROMPTLAB_DB`). Created on startup via
`CREATE TABLE IF NOT EXISTS`, followed by a set of idempotent, additive migrations (each guarded
by a `PRAGMA table_info` column check) that upgrade a pre-existing database created before a
column existed -- see `db._migrate`. All timestamps are ISO-8601 UTC strings. All `*_json` columns
are TEXT holding JSON. Foreign keys ON, cascading deletes as noted.

## prompt
| col | type | notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NOT NULL | |
| description | TEXT | |
| created_at | TEXT NOT NULL | |
| updated_at | TEXT NOT NULL | bumped when a new `prompt_version` is created for this prompt, and when `name`/`description` is patched. On databases created before this column existed, it is backfilled to `created_at` by the startup migration. |

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
| tools_json | TEXT NOT NULL DEFAULT '[]' | canned mock tools, validated object JSON Schemas |

## test_case
| id | INTEGER PK |
| dataset_id | INTEGER FK -> dataset.id ON DELETE CASCADE |
| inputs_json | TEXT NOT NULL | object mapping variable name -> string value |
| solution_criteria | TEXT NULL | fed to the llm_judge grader |
| category | TEXT NULL | e.g. `standard`, `empty_input`, `prompt_injection`, `boundary` |
| conversation_json | TEXT NOT NULL DEFAULT '[]' | array of up to 20 literal user-turn strings; empty = single-output |
| expected_format | TEXT NULL | `json` \| `python` \| `regex` \| NULL — used by code_syntax `auto` |
| created_at | TEXT NOT NULL |

## grader  — belongs to a prompt, snapshotted into each run
| id | INTEGER PK |
| prompt_id | INTEGER FK -> prompt.id ON DELETE CASCADE |
| type | TEXT NOT NULL | `llm_judge` \| `code_syntax` \| `string_match` \| `json_schema` \| `budget` \| `tool_calls` |
| name | TEXT NOT NULL | display label, unique per prompt |
| weight | REAL NOT NULL DEFAULT 1.0 | |
| config_json | TEXT NOT NULL | shape per type, see API_CONTRACT.md |
| enabled | INTEGER NOT NULL DEFAULT 1 |
| position | INTEGER NOT NULL DEFAULT 0 |
| gating | INTEGER NOT NULL DEFAULT 0 | independent hard-rule verdict, including zero-weight graders |
| pass_threshold | REAL NOT NULL DEFAULT 8.0 | 0–10, used only by gating llm_judge |

## run
| id | INTEGER PK |
| prompt_version_id | INTEGER FK -> prompt_version.id |
| dataset_id | INTEGER FK -> dataset.id |
| model | TEXT NOT NULL |
| temperature | REAL NOT NULL |
| max_tokens | INTEGER NOT NULL |
| judge_model | TEXT NOT NULL |
| concurrency | INTEGER NOT NULL |
| grader_snapshot_json | TEXT NOT NULL | resolved graders including gating and pass_threshold at launch |
| tools_snapshot_json | TEXT NOT NULL DEFAULT '[]' | dataset tool definitions and canned responses at launch |
| status | TEXT NOT NULL | `pending` \| `running` \| `completed` \| `failed` \| `cancelled` |
| started_at | TEXT NULL | finished_at TEXT NULL |
| avg_score | REAL NULL |
| pass_rate | REAL NULL | passing cases / all run cases; empty run = NULL |
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
| final_score | REAL NULL | weighted 0-10, retained on scored gate failure |
| passed | INTEGER NULL | true = every gate passed (or no gates), false = scored gate or execution failure; NULL = pending or inconclusive gate |
| transcript_json | TEXT NOT NULL DEFAULT '[]' | full structured Messages API history, persisted incrementally |
| tool_calls_json | TEXT NOT NULL DEFAULT '[]' | all attempted calls: id, name, input, 1-based user turn, response or error |
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
   reproducible when graders change. Tool definitions/responses likewise use tools_snapshot_json.
3. `run_case.final_score` = sum(grade.score * grade.weight) / sum(grade.weight), 0-10, NULL if the
   case failed before grading. Skipped/errored graders and non-positive weights are excluded.
   A scored gate failure changes status to failed without replacing final_score.
4. `run.avg_score` = mean of non-NULL `run_case.final_score`.
5. Deleting a dataset or prompt does NOT delete runs; runs keep their snapshot and denormalized data.
   Run detail endpoints must tolerate a missing parent dataset/prompt.


## Gate and conversation invariants

6. A scored deterministic gate fails below 10 (String Match includes partial matches);
   llm_judge fails below its snapshotted pass_threshold (default 8.0, inclusive pass).
   A skipped/errored gate is inconclusive unless another scored gate fails. A failed
   gate has passed=false, status=failed, error="Gating grader failed.". Execution
   errors also set passed=false. Non-gating grader errors keep the original semantics.
7. pass_rate = count(passed=true) / count(all run_case rows), including failures,
   inconclusive and pending rows in the denominator. NULL for no cases. With no gates,
   successful execution passes. On migration, old completed cases are backfilled true,
   old failed cases false; no historical score is changed. Summary/detail rates are
   derived from cases, including old runs whose stored pass_rate is still NULL.
8. A conversation starts with the rendered template prefixed to its first user turn.
   Subsequent user turns are literal. Full assistant content (including text with
   tool calls) and matching tool results are persisted before continuing. On failure,
   partial transcripts, all attempted calls, and accumulated usage/cost remain.
   Tools are canned dataset mocks, used only for non-empty conversations. No real
   tool code executes. Text graders inspect all assistant text joined with newlines;
   llm_judge inspects the transcript; budget uses total execution metrics.


## Provider identifiers and unknown costs

No provider-specific columns or credentials are added. prompt_version.model, run.model,
run.judge_model and snapshotted grader config.judge_model hold the selected identifiers.
Existing bare claude-* ids route to Anthropic; new OpenAI selections use openai:MODEL_ID.
Run and judge models can select different providers. Defaults for new runs resolve from
account-visible discovery; saved immutable version selections are not rewritten.

Model catalogs and provider status are cached in memory only. Keys are environment-only
and resolved independently for both providers; keys are never written to SQLite.
OpenAI native output items, including encrypted reasoning needed to resume a tool call,
are persisted in transcript assistant messages as provider_content.

Unknown token prices produce NULL run_case.cost. RunSummary/RunStats.cost_complete is
derived from terminal cases; total_cost sums known estimates and must be displayed as
incomplete if any terminal case lacks a cost. A cost-ceiling grader cannot pass without
a cost estimate. Unknown does not mean free.
