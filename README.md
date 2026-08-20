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
   per-category averages, so a weak category shows up even when the overall number looks fine.
6. Revise the prompt, save it as a new version, run it again, and compare the two runs.

For the full walkthrough, concept reference, and a guide to writing better prompts, see the
in-app **Guide** at `/guide` once PromptLab is running.

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

Two tests in `backend/tests/test_api.py` exercise the built frontend's static assets and skip
themselves when `backend/app/static/assets/` doesn't exist yet. On a fresh clone, before you
build the frontend, `uv run pytest` reports `421 passed, 3 skipped`. Build the frontend first
(`cd frontend && npm install && npm run build`) to get the full `423 passed, 1 skipped`.

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
