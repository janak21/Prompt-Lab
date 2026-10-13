# PromptLab — API Contract (FROZEN)

All routes under `/api`. JSON in / JSON out unless noted. Errors: HTTP status + `{"detail": str}`.
Any unmatched non-`/api` path serves the SPA `index.html` (client-side routing fallback).

Field naming is `snake_case` everywhere, request and response. Timestamps ISO-8601 UTC.

---

## Shared shapes

```ts
Prompt        = { id, name, description, created_at, updated_at, version_count, latest_version_no }
PromptVersion = { id, prompt_id, version_no, template, system_prompt, model, temperature,
                  max_tokens, notes, created_at, variables: string[] }
Grader        = { id, prompt_id, type, name, weight, config: object, enabled: bool, position, gating: bool, pass_threshold: number }
Dataset       = { id, name, description, source, created_at, case_count, variables: string[], tools: MockTool[] }
TestCase      = { id, dataset_id, inputs: Record<string,string>, solution_criteria, category,
                  expected_format, conversation: string[], created_at }
Grade         = { grader_name, grader_type, score, weight, reasoning, details: object }
RunCase       = { id, run_id, test_case_id, idx, rendered_prompt, output, latency_ms,
                  input_tokens, output_tokens, cost, final_score, passed: bool|null, status, error, transcript, tool_calls,
                  grades: Grade[], test_case: TestCase }
RunSummary    = { id, prompt_id, prompt_name, prompt_version_id, version_no, dataset_id,
                  dataset_name, model, judge_model, temperature, status, avg_score, pass_rate, total_cost,
                  total, completed, failed, started_at, finished_at, created_at, error }
RunStats      = { avg_score, pass_rate, total_cost, total_latency_ms, total, completed, failed,
                  by_grader: Record<string, {avg_score, weight}>,
                  by_category: Record<string, {avg_score, count}>,
                  distribution: number[]  // 10 buckets, scores 0-1,1-2,...,9-10
                }
```

`variables` on PromptVersion/Dataset are derived, not stored: template `{{var}}` names for a version,
union of `inputs` keys for a dataset.

---

## Meta
- `GET  /api/health` -> `{ status:"ok", api_key_present: bool, db_path, version, provider_keys: {anthropic: bool, openai: bool} }`
- GET /api/models?refresh=true -> {models: ModelInfo[], providers: ProviderInfo[],
                                  default_model, default_judge_model}
  Models are discovered with ANTHROPIC_API_KEY / OPENAI_API_KEY using each provider's
  Models API. Both keys resolve independently from env / parent .env files. The UI
  accepts no keys. Discovery is cached in memory for five minutes, scoped to the
  configured credentials; refresh=true bypasses the cache. One provider's failure
  does not remove another's models. Missing keys produce an empty list for that provider.
  Upstream error bodies are never returned.

  ModelInfo = {id, provider: "anthropic"|"openai", label, created_at, shutdown_date,
               input_price_per_mtok: number|null, output_price_per_mtok: number|null,
               context_window: number|null, supports_prefill, supports_temperature,
               supports_effort}.
  ProviderInfo = {id, key_present: bool, status: "available"|"missing_key"|"error", error}.
  Models are newest first by creation date. OpenAI text candidates are filtered by
  family name because its list lacks endpoint capabilities. Listed does not guarantee
  Responses/structured-output compatibility or account inference permission.
  Expired shutdown_date entries are excluded.

  A configured default is used only when present in the discovered list; otherwise
  choose the newest Anthropic model (or newest OpenAI model if only OpenAI is available).
  Empty lists return empty default identifiers. Explicit saved version models remain
  unchanged; old/retired versions can be run with a model override.

  OpenAI selections use openai:MODEL_ID; existing bare claude-* ids remain Anthropic.
  Explicit anthropic:MODEL_ID and bare GPT/o-series ids are also accepted. Run and
  judge provider selection is independent, including each grader's judge_model override.
  Unknown prices/context limits are null. Optional sampling/effort knobs are omitted
  when unsupported or unknown. The local pricing table does not define availability.

## Prompts
- `GET    /api/prompts` -> `Prompt[]`
- `POST   /api/prompts` body `{name, description?, template, system_prompt?, model?, temperature?, max_tokens?}`
  -> `{prompt: Prompt, version: PromptVersion}`  (creates version 1)
- `GET    /api/prompts/{id}` -> `{prompt: Prompt, versions: PromptVersion[], graders: Grader[]}`
- `PATCH  /api/prompts/{id}` body `{name?, description?}` -> `Prompt` (bumps `updated_at` when a field actually changes)
- `DELETE /api/prompts/{id}` -> 204
- `POST   /api/prompts/{id}/versions` body `{template, system_prompt?, model?, temperature?, max_tokens?, notes?}`
  -> `PromptVersion` (version_no auto-increments; also bumps the parent `Prompt.updated_at`)
- `GET    /api/prompt-versions/{id}` -> `PromptVersion`
- `POST   /api/prompts/extract-variables` body `{template}` -> `{variables: string[]}`

## Graders
- `GET    /api/prompts/{id}/graders` -> `Grader[]`
- `POST   /api/prompts/{id}/graders` body `{type, name, weight?, config, enabled?, position?, gating?, pass_threshold?}` -> `Grader`
- `PATCH  /api/graders/{id}` body any of `{name, weight, config, enabled, position, gating, pass_threshold}` -> `Grader`
- `DELETE /api/graders/{id}` -> 204

### Grader `config` shapes (validated server-side; 422 on mismatch)
```ts
llm_judge   : { rubric: string, use_solution_criteria: bool, judge_model?: string, scale_max?: 10 }
code_syntax : { format: "json"|"python"|"regex"|"auto" }   // auto -> test_case.expected_format
string_match: { must_contain: string[], must_not_contain: string[], regex?: string|null,
                case_sensitive: bool }
json_schema : { schema: object }
budget      : { max_latency_ms?: number, max_cost_usd?: number, max_output_tokens?: number }
tool_calls  : { tool: string, mode: "never_called"|"called_with_arguments", arguments?: object }
```
Every grader returns a score on 0-10. `code_syntax`/`json_schema` are 0 or 10. `string_match` scores
proportionally to satisfied constraints. `budget` scores 10 if all set ceilings hold, else 0.

## Datasets
- `GET    /api/datasets` -> `Dataset[]`
- `POST   /api/datasets` body `{name, description?, tools?: MockTool[]}` -> `Dataset` (source `manual`)
- `GET    /api/datasets/{id}` -> `{dataset: Dataset, cases: TestCase[]}`
- `PATCH  /api/datasets/{id}` body `{name?, description?, tools?: MockTool[]}` -> `Dataset`
- `DELETE /api/datasets/{id}` -> 204
- `POST   /api/datasets/{id}/cases` body `{inputs, solution_criteria?, category?, expected_format?, conversation?: string[]}` -> `TestCase`
- `PATCH  /api/cases/{id}` -> `TestCase`
- `DELETE /api/cases/{id}` -> 204

### Generation (synchronous; may take 15-60s — client shows a spinner)
- `POST /api/datasets/generate` body:
  ```ts
  { dataset_id?: number,        // append to existing; omit to create new
    name?: string,              // required when dataset_id omitted
    domain_description: string, // what the prompt does / what inputs look like
    variables: string[],        // generated `inputs` keys MUST be exactly these
    count: number,              // 1..50
    mode: "standard"|"adversarial"|"mixed",
    model?: string,
    prompt_template?: string }  // optional, gives the generator context
  ```
  -> `{ dataset: Dataset, cases: TestCase[] }`

  **Adversarial categories** the generator must draw from (tag each case's `category`):
  `empty_input`, `missing_field`, `ambiguous`, `contradictory`, `boundary_length`, `wrong_language`,
  `special_characters`, `prompt_injection`, `out_of_domain`, `hostile_formatting`.
  `mixed` = ~50/50 with `standard`-category cases.

### Import
- `POST /api/datasets/import/preview` multipart `file` ->
  `{ format: "csv"|"json"|"jsonl", columns: string[], rows: object[] /*first 10*/, total_rows }`
- `POST /api/datasets/import` multipart `file` + form field `payload` (JSON string):
  ```ts
  { dataset_id?: number,       // append to existing; omit to create new
    name?: string,             // required when dataset_id omitted
    mapping: Record<string,string>,  // column -> variable name
    solution_criteria_column?: string, category_column?: string, expected_format_column?: string }
  ```
  -> `{ dataset: Dataset, cases: TestCase[] }`. 404 if `dataset_id` doesn't exist; 422 if
  both `dataset_id` and `name` are omitted. Appending does not require the imported rows'
  mapped variable names to match the existing cases' keys -- `Dataset.variables` is the
  union across all cases, and a real mismatch against a prompt's template surfaces as a
  422 from the run pre-flight check instead (see `POST /api/runs` below).

## Runs
- `POST /api/runs` body `{prompt_version_id, dataset_id, model?, temperature?, max_tokens?,
  judge_model?, concurrency?}` -> `202 { run_id, status: "pending" }`. Execution starts as a
  background task; the client immediately opens the SSE stream.
  422 if the dataset is missing any variable the template requires.
- `GET    /api/runs?prompt_id=&dataset_id=&limit=` -> `RunSummary[]` (newest first)
- `GET    /api/runs/{id}` -> `{ run: RunSummary, stats: RunStats, cases: RunCase[] }`
- `POST   /api/runs/{id}/cancel` -> `202 {status:"cancelled"}`
- `DELETE /api/runs/{id}` -> 204
- `GET    /api/runs/compare?a={run_id}&b={run_id}` ->
  ```ts
  { a: {run: RunSummary, stats: RunStats}, b: {run: RunSummary, stats: RunStats},
    deltas: { avg_score: number, pass_rate: number|null, total_cost: number,
              by_grader: Record<string, number>, by_category: Record<string, number> },
    cases: [{ test_case: TestCase, a: RunCase|null, b: RunCase|null,
              winner: "a"|"b"|"tie", delta: number }],
    wins: {a: number, b: number, tie: number} }
  ```
  400 if the two runs used different datasets.

### SSE — `GET /api/runs/{id}/events`
`text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`. Named events, JSON data.
Comment heartbeat `:ping` every 15s. Stream closes after `run_completed` / `run_failed` / `cancelled`.
If the run already finished, emit the terminal event immediately and close.

```
run_started    {run_id, total}
case_started   {run_case_id, test_case_id, idx}
case_completed {run_case_id, test_case_id, idx, final_score, passed, error, latency_ms, cost, status,
                output_preview /*first 240 chars*/, grades: Grade[]}
case_failed    {run_case_id, idx, error}
progress       {completed, failed, total, avg_score_so_far}
run_completed  {run_id, avg_score, pass_rate, total_cost, completed, failed}
run_failed     {run_id, error}
cancelled      {run_id}
```

---

## Cross-cutting rules
0. **STRUCTURED JSON MUST NOT RELY ON ASSISTANT PREFILL.** An older technique gets JSON out of the
   model by prefilling an assistant turn with ```` ```json ```` and stopping at ```` ``` ````. That
   technique is **unsupported on Claude 5 models and returns HTTP 400**. Every place PromptLab needs
   structured JSON from the model (the `llm_judge` grader and dataset generation) MUST use
   **structured outputs** — `output_config={"format": {...}}` on `messages.create()` — as the primary
   path. Prefill is permitted ONLY as a fallback for models whose `supports_prefill` flag is true.
   A model's capability flag decides which path is taken; never hardcode the assumption.
0b. **`temperature` MUST NOT be sent to models where `supports_temperature` is false.** Verified
   against the live API: any non-default `temperature` returns HTTP 400 `temperature is deprecated
   for this model` on `claude-opus-5` and `claude-sonnet-5`. Omit the parameter entirely for those
   models rather than clamping it to 1.0. The UI must disable the temperature control (with an
   explanation) when the selected model does not support it.
0c. **NEVER read `message.content[0].text`.** Claude 5 models run adaptive thinking by default, so
   `content[0]` is frequently a `ThinkingBlock` and `.text` raises `AttributeError`. This is
   INTERMITTENT — short prompts return a lone text block and long/hard ones do not, so it passes
   smoke tests and fails on real grading. Always scan `message.content` for the first block with
   `type == "text"`, and raise a clear error if none exists. Budget `max_tokens` with thinking in
   mind: thinking tokens count toward the cap.
1. The Anthropic API key is read from the environment only. It is never accepted, stored, or
   returned by any endpoint, and never logged. `/api/health` reports presence as a boolean only.
2. Every LLM call retries on 429 / 5xx / `overloaded_error` with exponential backoff + jitter,
   max 4 attempts. A case that still fails is marked `failed`, never crashes the run.
3. Requests are validated with Pydantic; violations return 422 with a readable `detail`.
4. Run execution is concurrency-limited by an asyncio semaphore (`concurrency`, default 5, max 20).
5. `output_preview` is truncated server-side; full output only via `GET /api/runs/{id}`.


## Gating verdicts

gating defaults false. pass_threshold defaults 8.0 and accepts finite values from
0 to 10; only llm_judge uses it. Both values are part of the run's grader snapshot.
A scored string_match/code_syntax/json_schema/budget/tool_calls gate requires 10;
llm_judge requires score >= pass_threshold. A failed scored gate sets case status
failed and passed=false while retaining the weighted final_score. Skipped/errored
gates set passed=null unless a different scored gate fails. With no gates, successful
execution sets passed=true. Execution errors set passed=false.

pass_rate is count(passed=true) / total cases, including pending/inconclusive/error
cases in total. Empty runs return null. Compare pass_rate delta is A minus B (0–1
units; null if either rate is unavailable). Score-based winners remain score-based.
Grade.details contains _status, _gating, and _pass_threshold for inspecting verdicts.
The CLI's JSON report has exactly the GET /api/runs/{id} shape.

## Scripted conversations

MockTool = {name, description?: string, input_schema: object, response?: JSON value}.
Dataset POST/PATCH accepts tools (default []), max 20, with unique names matching
[a-zA-Z0-9_-]{1,64}; schemas must be valid JSON Schemas with type object. Responses
are canned JSON, default null. PATCH tools=[] clears the list.

Case POST/PATCH accepts conversation: string[] (max 20, default []). Empty means the
original single-output path; PATCH conversation=[] clears it. The rendered template
prefixes the first turn; subsequent turns are literal. Existing inputs and template
variable validation still apply.

RunCase.transcript is an array of {role, content}, preserving structured assistant
content blocks and user tool_result blocks. RunCase.tool_calls is an array of
{id, name, input, turn, response?, error?}; turn is the 1-based scripted user turn.
Both fields persist incrementally and remain available after dataset deletion.
Single-output cases return [] for both. Full transcripts are available on run detail
and compare, not sent over per-case SSE previews.

The runner snapshots dataset tools at launch, resumes after every tool_use with a
matching tool_result for each call, and permits 8 tool rounds per user turn. Unknown
tools, invalid arguments, unsupported stop reasons, max_tokens truncation, or loop
exhaustion fail that case while keeping partial evidence. It uses the existing
Anthropic retry wrapper and temperature capabilities, with no assistant prefill.
See [Anthropic tool-call lifecycle](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls).

tool_calls never_called checks every attempt; called_with_arguments requires at least
one successful mock call whose input contains every specified top-level argument/value.
Extra arguments are allowed; nested values use exact equality. Scores are binary,
usable as gates. For conversations, llm_judge gets the transcript, text/schema graders
get all assistant text joined by newlines, and budget gets total model-call metrics.

Not covered: rule-based/stateful responses, real or server tools, within-turn streaming,
branching simulators, per-turn grading, tool-order assertions, and conversation
import/generation. Use case/dataset CRUD or the UI to author scripts.


## OpenAI execution

OpenAI uses POST /v1/responses with store=false and structured output text.format
(type=json_schema, strict=true) for judging/generation. Tools use function definitions
with strict=false to preserve user-authored mock schemas. Function calls/results are
normalized for the existing runner; native output items and encrypted reasoning are
retained in transcript assistant messages as provider_content and replayed verbatim.
The same four-attempt retry policy handles 429/5xx/transport errors. Provider error
bodies are sanitized. Truncated single-output responses also fail before grading.

RunStats and RunSummary include cost_complete (boolean). Unknown case prices yield
cost=null; total_cost is the sum of known costs only and is incomplete when this flag
is false. Cost budgets fail rather than treating unknown prices as free. API keys
never appear in discovery, reports, stored transcripts or error messages.
