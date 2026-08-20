# PromptLab

A local tool for finding out where your production prompt breaks before your users do.

## The problem

A prompt that works great on the five examples you tried while writing it can still fail
on the edge cases you didn't think to test: an empty field, a contradictory instruction, a
prompt-injection attempt buried in user input, a wall of text at 10x the length you
expected. PromptLab exists to generate those hostile inputs on purpose, run your prompt
against them, grade the outputs with a configurable mix of an LLM judge and deterministic
checks, and show you the results broken down by *category* — so you learn which kind of
input your prompt is weak against, not just a single average score.

It grew directly out of a small notebook-based eval loop (`../001_prompt_evals_complete.ipynb`):
generate a dataset, run a prompt, grade with an LLM judge + a syntax check, average the two.
PromptLab makes that loop persistent (SQLite instead of a notebook variable), concurrent,
configurable, and has a UI on top of it — and adds the adversarial dataset generation and
version-comparison pieces the notebook didn't have.

## Quick start

Prerequisites: [`uv`](https://docs.astral.sh/uv/), Node.js, and npm.

```bash
./run.sh
```

This syncs Python dependencies, builds the frontend if it's stale, starts the backend on
`http://localhost:8000` (override with `PORT=...`), and opens your browser. Add `--no-open`
to skip opening a browser, or `--dev` to run the backend and the Vite dev server together
with hot reload instead of a static build.

The first time it runs against an empty database, it seeds a worked example (see below) so
there's something to look at immediately. `--seed` re-runs the seed explicitly at any time
— it's idempotent and never touches your own data.

**API key.** PromptLab needs `ANTHROPIC_API_KEY` to run prompts, generate datasets, or grade
with an LLM judge. Copy `.env.example` to `.env` and fill it in, either in this directory or
in any parent directory (the backend walks up looking for one — handy if you keep one shared
`.env` above several projects). The key is read from the environment only: it is **never**
stored in the database, never returned by any API response, and never logged. If no key is
resolvable, `run.sh` prints a clear warning and starts anyway, so you can still explore the
UI — runs and generation will just fail until you set it.

## The core loop

1. **Write a prompt** with `{{variable}}` placeholders (e.g. `{{task}}`, `{{ticket_text}}`).
   PromptLab detects the variables live as you type.
2. **Build a dataset** — three ways, landing in the same table:
   - **Generate**: describe the domain, pick a count and a mode (`standard`, `adversarial`,
     `mixed`). Generation reads your prompt's variables so every case has exactly the right
     keys.
   - **Manual**: add or edit cases by hand — paste in a real production failure.
   - **Import**: upload CSV/JSON/JSONL with a column → variable mapping step.
3. **Configure graders** on the prompt — pick types, write rubrics/schemas/patterns, set
   weights.
4. **Run** the prompt against the dataset. Results stream in live (SSE) as each case
   completes.
5. **Read results** — overall average, score distribution, per-grader averages, and
   per-category averages, plus a detail drawer per case with the rendered prompt, raw
   output, latency/tokens/cost, and each grader's reasoning.
6. **Change the prompt**, save it as a new version, run it again, then **compare** two runs
   on the same dataset — deltas, per-case win/loss/tie, side-by-side outputs.

## Adversarial mode

This is the feature that makes PromptLab more than a notebook. Generation in `adversarial`
or `mixed` mode deliberately produces cases in ten categories, and every generated case is
tagged with its category:

| Category | What it probes |
|---|---|
| `empty_input` | Blank or missing values |
| `missing_field` | A variable your template needs but the case doesn't supply |
| `ambiguous` | Underspecified instructions with multiple reasonable interpretations |
| `contradictory` | Self-contradicting requirements |
| `boundary_length` | Extremely short or extremely long input |
| `wrong_language` | Input in a language other than the prompt was designed for |
| `special_characters` | Unicode edge cases, control characters, odd encodings |
| `prompt_injection` | Text that tries to override your instructions |
| `out_of_domain` | Input outside the domain the prompt was built for |
| `hostile_formatting` | Malformed markup, broken JSON-looking text, weird whitespace |

Results break down `by_category` in the run stats, so instead of one blended average you
see, for example, that your prompt scores 9.2 on standard input but 3.1 on
`prompt_injection` — the specific weakness, not a hidden one.

## Graders

Five grader types, each configured per prompt and snapshotted into every run (so old runs
stay reproducible even if you later edit the grader):

| Type | What it checks | Score |
|---|---|---|
| `llm_judge` | A model scores the output against your rubric, optionally grounded in the case's `solution_criteria` | 0–10 |
| `code_syntax` | Output parses as JSON / Python (`ast`) / regex (`re.compile`), or `auto` to use the case's `expected_format` | 0 or 10 |
| `string_match` | Must-contain / must-not-contain / regex constraints | proportional to constraints satisfied |
| `json_schema` | Output parses and validates against a JSON Schema | 0 or 10 |
| `budget` | Latency / cost / output-token ceilings | 10 if all set ceilings hold, else 0 |

Each grader has a **weight**. A case's final score is the weighted average of its graders'
scores, normalized to 0–10:

```
final_score = sum(grade.score * grade.weight) / sum(grade.weight)
```

**Skipped graders are excluded from that average, not scored zero.** For example,
`code_syntax` in `auto` mode skips itself entirely when a test case has no
`expected_format` set — there's nothing to check, so it doesn't drag the score down as if
it had failed. The same applies to any grader that errors before producing a score. If
every grader on a case is skipped or failed, that case's `final_score` is left `null`
rather than reported as 0.

## Architecture at a glance

- **Backend**: FastAPI + SQLite (stdlib `sqlite3`, no ORM), managed with `uv`, Python 3.13.
  Runs are executed concurrently (asyncio + semaphore) with retry/backoff on rate limits,
  and stream progress over Server-Sent Events.
- **Frontend**: Vite + React 19 + TypeScript + Tailwind v4, built to `backend/app/static/`
  and served directly by FastAPI (so `./run.sh` really is one process, one port). See
  [`frontend/README.md`](frontend/README.md) for frontend-specific development, mock mode,
  and the smoke test.
- **`docs/`** — the frozen specs this app was built against:
  - [`docs/PLAN.md`](docs/PLAN.md) — feature scope and build plan
  - [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — SQLite schema and invariants
  - [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — every endpoint and payload shape
  - [`docs/DESIGN.md`](docs/DESIGN.md) — visual/interaction direction

## Testing

```bash
uv run pytest                                       # unit tests, LLM calls mocked (409 tests, 1 skipped)
PROMPTLAB_LIVE_TESTS=1 uv run pytest -m live         # opt-in tier: real, billed Anthropic API calls
```

The live tier is never run in CI and never runs by default — it's gated by both an env var
and a pytest marker, deliberately redundant.

**Two tests in `backend/tests/test_api.py` are conditional on the frontend being built.**
The backend only mounts `/assets` when `backend/app/static/assets/` exists at import time
(see `main.py`'s `if ASSETS_DIR.is_dir():` guard, which lets the server boot before a build
exists). `TestStaticAssets` exercises that mount against the actual built assets, so both
of its tests skip themselves — rather than failing — when the directory isn't there yet. On
a fresh clone, before you've run `cd frontend && npm install && npm run build`, `uv run
pytest` reports `407 passed, 3 skipped` (the two asset tests, plus the always-skipped
opt-in live tier below). Build the frontend first (see
[`frontend/README.md`](frontend/README.md)) to get the full `409 passed, 1 skipped` count.

```bash
cd frontend && npm run smoke
```

The smoke test loads every route in a headless browser and asserts real content rendered.
It exists because `tsc -b` and `vite build` both passing does **not** prove the app renders
anything — a missing Router provider, for instance, lets React mount cleanly into an empty
`#root` with zero console errors. That exact failure shipped twice during development before
this check was added. See `frontend/README.md` for details on running it against the dev
server.

## Known limitations / not yet built

- **No auth.** The server binds to localhost only and assumes a single local user.
- **SQLite, single process.** Fine for local use; not built for concurrent multi-user access.
- **No run-history / score-trend UI.** Runs are persisted (so this is addable later without
  a migration), but there's no view that plots a prompt's score over time across runs yet.
- **Dataset generation is synchronous** and can take 15–60 seconds — the client shows a
  spinner, but there's no background job queue or progress stream for generation itself
  (unlike run execution, which does stream over SSE).
- **Cost figures are estimates** from a static price table (`backend/app/pricing.py`), not
  the API's actual billed amount — model pricing can change and drift from what's hardcoded
  here.

## Seed example

`backend/app/seed.py` recreates the source notebook's pipeline as a real PromptLab prompt:
an "AWS Code Generator" prompt (`{{task}}` template), a 3-case dataset (S3 region
extraction, an IAM policy, an EC2 instance-ID regex) pulled from the notebook's own
`dataset.json`, and two graders — an `llm_judge` (weight 2, "expert AWS code reviewer"
rubric) and a `code_syntax` check (weight 1, `auto` format) — reproducing the notebook's
model-score-plus-syntax-score average, now weighted. It never creates a run (that costs
money and stays your choice), and it's idempotent: run it as many times as you like via
`./run.sh --seed` or `python -m backend.app.seed`.
