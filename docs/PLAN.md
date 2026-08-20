# PromptLab — Implementation Plan

**Goal:** a local, browser-based prompt evaluation pipeline. Write a production prompt in a UI,
generate or import a test dataset (including deliberately adversarial edge cases), grade outputs
with a configurable mix of LLM-judge and deterministic code graders, see scores and failures, and
A/B two prompt versions against the same dataset to prove one is actually better.

Base pipeline: generate dataset -> run prompt -> model grade + syntax grade -> average. Everything
below makes that loop persistent, concurrent, configurable, and visual.

---

## 1. Decisions (locked)

| Decision | Choice |
|---|---|
| Location | `Prompt Evaluation/promptlab/` |
| Backend | FastAPI + SQLite, `uv`-managed, Python 3.13 |
| Frontend | Vite + React + TypeScript + Tailwind, built to `backend/app/static/`, served by FastAPI |
| Startup | `./run.sh` -> builds frontend if stale, starts uvicorn on `:8000`, opens browser |
| Templating | Named variables: `{{ticket_text}}`, `{{tier}}`. A test case is a JSON object of those keys |
| Live progress | Server-Sent Events (`/api/runs/{id}/events`) |
| API key | Read from env / `.env` (walks up to the repo `.env` already present). Never stored in the DB, never logged, never returned by the API |
| Not in scope (per your selection) | Regression-suite / score-trend-over-time UI. Runs are still persisted, so this can be added later without a data migration |

## 2. Feature set

**Prompts**
- Named prompt, with an immutable version history. Editing + saving creates version N+1.
- `{{variable}}` detection with live chip list; warns on variables a dataset doesn't supply.
- Optional system prompt, model, temperature, max_tokens stored per version.

**Datasets**
- Three input paths, all landing in the same table:
  1. **AI-generated** — describe the domain, choose count. Generation reads the prompt's detected
     variables so every generated case has exactly the right keys, plus `solution_criteria` and a
     `category` tag.
  2. **Manual** — add/edit/delete cases inline in a table; paste in real production failures.
  3. **Import** — CSV / JSON / JSONL upload with a column -> variable mapping step and a preview.
- **Generation modes:** `standard`, `adversarial`, `mixed`.
  Adversarial deliberately produces: empty/missing fields, ambiguous, self-contradictory,
  boundary and extreme-length values, wrong language / odd encoding, prompt-injection attempts,
  out-of-domain, and hostile formatting. Every case carries its `category`, so results group by
  failure type — that is the direct answer to "which edge cases does my prompt miss?"

**Graders** (configured per prompt, weighted, snapshotted into each run so history stays reproducible)
- `llm_judge` — your own rubric, optionally grounded in the case's `solution_criteria`.
  Emits strengths / weaknesses / reasoning / score, with reasoning ordered before the score.
- `code_syntax` — output parses as JSON / Python (`ast`) / regex (`re.compile`).
- `string_match` — must contain / must not contain / regex match.
- `json_schema` — output parses and validates against a JSON Schema you paste in.
- `budget` — latency, cost, and output-token ceilings.
Final score = weighted, normalized 0-10.

**Runs**
- Concurrent execution (asyncio + semaphore, default 5) with retry/backoff on 429 and overload.
- Live per-case progress in the UI while running.
- Results: average score, distribution, per-grader averages, per-category averages, sortable case
  table, and a detail drawer per case showing the rendered prompt, the raw output, latency, tokens,
  cost, and each grader's reasoning.

**Compare (A/B)**
- Pick two runs on the same dataset -> summary deltas, per-case win/loss/tie, side-by-side outputs,
  per-grader and per-category deltas. This is the loop that answers "is v3 better than v2?"

## 3. Data model (SQLite)

- `prompt` (id, name, description, created_at)
- `prompt_version` (id, prompt_id, version_no, template, system_prompt, model, temperature,
  max_tokens, notes, created_at) — immutable
- `dataset` (id, name, description, source, created_at)
- `test_case` (id, dataset_id, inputs JSON, solution_criteria, category, expected_format, created_at)
- `grader` (id, prompt_id, type, name, weight, config JSON, enabled)
- `run` (id, prompt_version_id, dataset_id, model, temperature, judge_model, concurrency,
  grader_snapshot JSON, status, started_at, finished_at, avg_score, total_cost, error)
- `run_case` (id, run_id, test_case_id, rendered_prompt, output, latency_ms, input_tokens,
  output_tokens, cost, final_score, status, error)
- `grade` (id, run_case_id, grader_name, grader_type, score, weight, reasoning, details JSON)

## 4. Layout

```
promptlab/
  run.sh  pyproject.toml  .env.example  README.md
  docs/   PLAN.md  API_CONTRACT.md  DATA_MODEL.md  DESIGN.md
  backend/app/
    main.py config.py db.py models.py schemas.py llm.py templating.py pricing.py
    routers/   prompts.py datasets.py graders.py runs.py meta.py
    eval/      runner.py scoring.py generation.py importers.py
    eval/graders/  base.py llm_judge.py code_syntax.py string_match.py json_schema.py budget.py
    static/    <built frontend>
  backend/tests/
  frontend/src/
    pages/     Prompts.tsx Datasets.tsx Graders.tsx Run.tsx Results.tsx Compare.tsx Settings.tsx
    components/  lib/api.ts lib/sse.ts
```

## 5. Design direction

Dark-first, neutral zinc surfaces, a single accent colour, dense Linear/Vercel-style dashboard
layout. Monospace (JetBrains Mono) for every prompt, output, and JSON surface; Inter for UI chrome.
Explicitly avoided: purple gradients, glass cards, emoji-as-icons, centred marketing layouts.

## 6. Execution — orchestrated subagents (Sonnet 5)

I author the frozen contracts first (`API_CONTRACT.md`, `DATA_MODEL.md`, `DESIGN.md`) so backend
and frontend can be built in parallel without drifting. Then:

| Phase | Agents | Work |
|---|---|---|
| P1 Foundation | 1 | scaffold, uv/pyproject, config + key resolution, db + models, LLM client (retries, token accounting, cost), templating engine, pytest harness with a mocked LLM |
| P2 (parallel) | 3 | **a)** eval core: graders, scoring, concurrent runner + SSE, generation (standard/adversarial), CSV/JSON/JSONL importers. **b)** CRUD API: all routers per contract. **c)** frontend scaffold: Vite/React/TS/Tailwind, design tokens, base components, typed API client, mock-data mode |
| P3 (parallel) | 2 | **a)** Prompts + Datasets + Graders pages. **b)** Run + live progress + Results + Compare pages |
| P4 Integration | 1 | wire frontend to real API, `run.sh`, seed a starter example prompt + dataset, README, end-to-end smoke test against the live API |
| P5 Review | me + reviewers | code review, a real eval run end to end, fix pass |

Every phase gate is mine: I review the diff against the contract before the next phase starts.

## 7. Known risks

- **SSE + concurrency** — event ordering and clean completion/error propagation. Mitigated by
  unit-testing the runner against a mocked LLM before any UI touches it.
- **Live API cost during development** — all automated tests use a mocked client; real calls only in
  the P4 smoke test and P5 review, on a 3-case dataset.
- **Contract drift** between the parallel backend/frontend agents — mitigated by freezing
  `API_CONTRACT.md` before P2 and having the frontend generate its types from it.
- **Frontend build** adds a Node step to startup; `run.sh` handles it and skips when the build is fresh.
