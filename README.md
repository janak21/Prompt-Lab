# PromptLab

PromptLab is a local tool that finds where a production prompt breaks before your users do.

A prompt that looks solved after a few manual tries in Claude or ChatGPT can still fail on
inputs you didn't think to test: an empty field, a contradictory instruction, a
prompt-injection attempt buried in user input, a wall of text at ten times the length you
expected. PromptLab generates those inputs on purpose, runs your prompt against them, grades
the outputs with a configurable mix of an LLM judge and deterministic checks, and reports the
results grouped by *what kind* of input failed — so you learn which category your prompt is
weak against, not just a single average score.

## Requirements

- [`uv`](https://docs.astral.sh/uv/)
- Node.js and npm
- An Anthropic API key, to run prompts, generate datasets, or grade with an LLM judge

## Quick start

```bash
./run.sh
```

This syncs Python dependencies, builds the frontend if it's stale, starts the backend at
`http://localhost:8000` (set `PORT` to override), and opens your browser. Pass `--no-open` to
skip opening a browser, or `--dev` to run the backend and the Vite dev server together with hot
reload instead of a static build.

The first run against an empty database seeds a worked example, so there's something to look at
immediately. Pass `--seed` to re-run the seed explicitly at any time — it's idempotent and never
touches your own data.

### API key

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`, either in this directory or in any
parent directory — the backend walks up the directory tree looking for one, which is convenient
if you keep a single shared `.env` above several projects. The key is read from the environment
only: it's never stored in the database, never returned by any API response, and never logged.
If no key resolves, `run.sh` prints a warning and starts anyway, so you can still explore the UI
— runs and generation fail until you set a key.

## The core loop

1. Write a prompt with `{{variable}}` placeholders, for example `{{task}}` or `{{ticket_text}}`.
2. Build a dataset — generate cases from a description, add them by hand, or import a CSV, JSON,
   or JSONL file.
3. Attach one or more graders to the prompt and set their weights.
4. Run the prompt against the dataset. Results stream in live as each case completes.
5. Read the results: overall average, per-grader averages, and — the point of the product —
   pass rate and per-category averages, so a weak category shows up even when the overall number looks fine.
6. Revise the prompt, save it as a new version, run it again, and compare the two runs.

For the full walkthrough, concept reference, and a guide to writing better prompts, see the
in-app **Guide** at `/guide` once PromptLab is running.

## Hard rules and pass rate

Enable **Gating** in a grader's configuration to make it a hard rule. A scored gate
that fails marks the case failed, even when its weighted average is high. Scores keep
their original meaning and weights (a zero-weight gate still applies).

- String Match requires **every** constraint to hold (score 10).
- Code Syntax, JSON Schema, Budget, and Tool Calls require score 10.
- LLM Judge requires score >= its **Pass threshold**, default 8.0 on the 0–10 scale.
- Skipped or errored gates are inconclusive, never counted as passes.

Pass rate is passing cases / all cases in the run. Execution failures and inconclusive
gates count against it; an empty run has no rate. With no gates, successful execution
passes. Results and Compare show the rate beside the average. Grader flags and judge
thresholds are snapshotted at launch, so changing a grader never changes old verdicts.

## Headless evaluations for CI

Run a saved prompt and dataset without starting the server:

```bash
PROMPTLAB_DB=/absolute/path/to/evaluations.db uv run promptlab run \
  --prompt "Support" --version 2 --dataset "Tickets" \
  --fail-under 8.0 --require-pass-rate 1.0 --json report.json
```

Names match exactly; duplicate names require an id, and numeric selectors are ids.
Omit --version to use the latest version. PROMPTLAB_DB selects the same SQLite database
used by the web UI (relative paths resolve as described in the data model). Graders and
model settings come from that prompt version and its prompt's enabled graders.

The summary includes average, pass rate, category averages, and failed/inconclusive
cases. Exit codes: **0** for success, **1** for execution/grader errors or unmet
thresholds, **2** for invalid selectors/settings or setup/report-file errors.
The default required pass rate is **1.0**; lower it explicitly to allow some gate
failures. --fail-under is optional. Unscored runs cannot meet a score threshold.
Reports use the run-detail API shape and are written after execution even if thresholds
fail. Empty datasets are rejected. The CLI does not seed automatically.

Example GitHub Actions steps after checkout and installing uv (the seed creates a
demo fixture without model calls; replace it with your own fixture setup for real CI):

```yaml
- name: Evaluate the demo prompt
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    PROMPTLAB_DB: ${{ runner.temp }}/promptlab-ci.db
  run: |
    uv sync
    uv run python -m backend.app.seed
    uv run promptlab run --prompt "AWS Code Generator" --version 1 \
      --dataset "AWS Tasks" --fail-under 8.0 --require-pass-rate 1.0 \
      --json report.json
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: promptlab-report
    path: report.json
```

Actual evaluations call Anthropic and incur normal API costs. The report never contains
the API key.

## Scripted conversations and mock tools

On a dataset page, **Add case** accepts a JSON array of user turns. The case's inputs
still fill the prompt template; that rendered prompt prefixes the first user turn.
Later turns are literal text. Leave the array empty for the original single-output
behavior. Example case body for POST /api/datasets/{id}/cases:

```json
{
  "inputs": {"tier": "standard"},
  "category": "contradictory",
  "conversation": ["I paid yesterday. Can I get a refund?", "Actually I never paid."],
  "solution_criteria": "Do not refund an unpaid order."
}
```

Use **Mock tools** on the dataset page to save canned tools (also accepted by dataset
POST/PATCH as a tools array):

```json
[
  {
    "name": "refund",
    "description": "Refund an order in this test.",
    "input_schema": {
      "type": "object",
      "properties": {"order_id": {"type": "string"}},
      "required": ["order_id"],
      "additionalProperties": false
    },
    "response": {"refunded": true}
  }
]
```

Tool definitions and responses are snapshotted at launch. The runner sends structured
Anthropic tool definitions, preserves the full assistant content, supplies a tool_result
for each call, and resumes until that turn ends before sending the next scripted user
turn. Text accompanying a tool call stays in the reply. No mock executes real actions.
Unknown tools, schema-invalid arguments, truncated replies, and loop exhaustion fail
the case while retaining its partial transcript and all attempted calls.

Add a **Tool Calls** grader and enable Gating to enforce never_called, or
called_with_arguments. For example, a grader config
{"tool":"refund","mode":"never_called"} forbids every refund attempt.
{"tool":"refund","mode":"called_with_arguments","arguments":{"order_id":"123"}}
requires at least one valid call with those top-level argument values; extra arguments
are allowed and nested values compare exactly.

The case drawer shows the transcript, tool calls, canned responses, and grades.
The output field joins all assistant text across turns; text/schema graders inspect that
combined output, the LLM judge receives the transcript, and Budget checks totals across
all model calls. Tool Calls checks the entire conversation.

This first version supports up to **20 user turns**, **20 tools**, and **8 tool rounds
per turn**. Tools apply only to scripted cases. It does not provide rule-based/stateful
tool responses, real tools, server tools, streaming within a turn, branching user
simulators, per-turn grading, tool-order assertions, or conversation import/generation.
Create/edit conversations through the UI or case API; the existing importer remains
for single-output cases.

## Adversarial categories

This is the feature that differentiates PromptLab from testing a prompt by hand. Generating a
dataset in `adversarial` or `mixed` mode deliberately produces cases across ten categories, and
every case is tagged with its category so results can be broken down by it:

| Category | What it probes |
|---|---|
| `empty_input` | A blank or whitespace-only value |
| `missing_field` | A value that stands in for "not provided" (`N/A`, `unknown`) |
| `ambiguous` | Underspecified input that could resolve to two different outputs |
| `contradictory` | Two mutually exclusive facts or instructions in the same input |
| `boundary_length` | Extremely short or extremely long input |
| `wrong_language` | Input in a language other than the prompt was designed for |
| `special_characters` | Control characters, zero-width spaces, homoglyphs, or raw markup |
| `prompt_injection` | Text that tries to redirect the model away from its task |
| `out_of_domain` | Input about a completely different topic than the prompt handles |
| `hostile_formatting` | Fake role markers or delimiters that mimic the prompt's own structure |

A run's results break down by category, so instead of one blended average, you can see that a
prompt scores 9.2 on standard input but 3.1 on `prompt_injection` — a specific, actionable
weakness instead of a hidden one.

## Architecture at a glance

- **Backend**: FastAPI and SQLite (`sqlite3` from the standard library, no ORM), managed with
  `uv`, on Python 3.13. Runs execute concurrently with retry and backoff on rate limits, and
  stream progress over Server-Sent Events.
- **Frontend**: Vite, React 19, TypeScript, and Tailwind v4, built to `backend/app/static/` and
  served directly by FastAPI, so `./run.sh` is one process on one port. See
  [`frontend/README.md`](frontend/README.md) for frontend development, mock mode, and the smoke
  test.
- **`docs/`** — the specs this app was built against:
  - [`docs/PLAN.md`](docs/PLAN.md) — feature scope and build plan
  - [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — SQLite schema and invariants
  - [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) — every endpoint and payload shape
  - [`docs/DESIGN.md`](docs/DESIGN.md) — visual and interaction direction

## Testing

```bash
uv run pytest                                       # unit tests, LLM calls mocked
PROMPTLAB_LIVE_TESTS=1 uv run pytest -m live         # opt-in tier: real, billed Anthropic API calls
```

The live tier never runs in CI and never runs by default — it's gated by both an environment
variable and a pytest marker, deliberately redundant.

Static-asset tests skip when the frontend has not been built. Build it first
(`cd frontend && npm install && npm run build`) to exercise those checks.

```bash
cd frontend && npm run smoke
```

The smoke test loads every route in a headless browser and asserts that real content rendered.
It exists because type-checking (`tsc -b`) and the production build (`vite build`) both passing
does not prove the app renders anything — a missing router provider, for example, lets React
mount cleanly into an empty `#root` with zero console errors. That exact failure shipped twice
during development before this check was added. See [`frontend/README.md`](frontend/README.md)
for details on running it against the dev server.

## Limitations

- **No authentication.** The server binds to localhost only and assumes a single local user.
- **SQLite, single process.** Fine for local use; not built for concurrent multi-user access.
- **Dataset generation is synchronous** and can take 15 to 60 seconds. The client shows a
  spinner, but there's no background job queue or progress stream for generation itself, unlike
  run execution, which streams over SSE.
- **Cost figures are estimates** from a static price table (`backend/app/pricing.py`), not the
  API's actual billed amount — model pricing can change and drift from what's hardcoded here.
- **No run-history or score-trend view.** Runs are persisted, so this is addable later without a
  migration, but there's no view that plots a prompt's score across runs over time.

## License

MIT. See [`LICENSE`](LICENSE).
