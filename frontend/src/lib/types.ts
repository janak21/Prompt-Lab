// Hand-written TypeScript types mirroring promptlab/docs/API_CONTRACT.md exactly.
// Field naming is snake_case everywhere to match the wire format 1:1.

// ---------------------------------------------------------------------------
// Error shapes — FastAPI/Pydantic 422s return `detail` as an array of these;
// other errors (404, 400, 500) return `detail` as a plain string.
// ---------------------------------------------------------------------------

export interface ValidationIssue {
  loc: (string | number)[]
  msg: string
  type: string
}

export type ErrorDetail = string | ValidationIssue[]


export type GraderType = 'llm_judge' | 'code_syntax' | 'string_match' | 'json_schema' | 'budget'

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
export type RunCaseStatus = 'pending' | 'running' | 'completed' | 'failed'
export type DatasetSource = 'generated' | 'manual' | 'imported'
export type GenerationMode = 'standard' | 'adversarial' | 'mixed'
export type ExpectedFormat = 'json' | 'python' | 'regex' | null

export type AdversarialCategory =
  | 'empty_input'
  | 'missing_field'
  | 'ambiguous'
  | 'contradictory'
  | 'boundary_length'
  | 'wrong_language'
  | 'special_characters'
  | 'prompt_injection'
  | 'out_of_domain'
  | 'hostile_formatting'

export type CaseCategory = 'standard' | AdversarialCategory | string

// ---------------------------------------------------------------------------
// Shared shapes
// ---------------------------------------------------------------------------

export interface Prompt {
  id: number
  name: string
  description: string | null
  created_at: string
  updated_at: string
  version_count: number
  latest_version_no: number
}

export interface PromptVersion {
  id: number
  prompt_id: number
  version_no: number
  template: string
  system_prompt: string | null
  model: string | null
  temperature: number | null
  max_tokens: number | null
  notes: string | null
  created_at: string
  variables: string[]
}

export interface GraderConfigLlmJudge {
  rubric: string
  use_solution_criteria: boolean
  judge_model?: string
  scale_max?: 10
}
export interface GraderConfigCodeSyntax {
  format: 'json' | 'python' | 'regex' | 'auto'
}
export interface GraderConfigStringMatch {
  must_contain: string[]
  must_not_contain: string[]
  regex?: string | null
  case_sensitive: boolean
}
export interface GraderConfigJsonSchema {
  schema: object
}
export interface GraderConfigBudget {
  max_latency_ms?: number
  max_cost_usd?: number
  max_output_tokens?: number
}
export type GraderConfig =
  | GraderConfigLlmJudge
  | GraderConfigCodeSyntax
  | GraderConfigStringMatch
  | GraderConfigJsonSchema
  | GraderConfigBudget
  | Record<string, unknown>

export interface Grader {
  id: number
  prompt_id: number
  type: GraderType
  name: string
  weight: number
  config: GraderConfig
  enabled: boolean
  position: number
}

export interface Dataset {
  id: number
  name: string
  description: string | null
  source: DatasetSource
  created_at: string
  case_count: number
  variables: string[]
}

export interface TestCase {
  id: number
  dataset_id: number
  inputs: Record<string, string>
  solution_criteria: string | null
  category: CaseCategory | null
  expected_format: ExpectedFormat
  created_at: string
}

export interface Grade {
  grader_name: string
  grader_type: GraderType
  score: number
  weight: number
  reasoning: string | null
  details: Record<string, unknown>
}

export interface RunCase {
  id: number
  run_id: number
  test_case_id: number
  idx: number
  rendered_prompt: string | null
  output: string | null
  latency_ms: number | null
  input_tokens: number | null
  output_tokens: number | null
  cost: number | null
  final_score: number | null
  status: RunCaseStatus
  error: string | null
  grades: Grade[]
  test_case: TestCase
}

export interface RunSummary {
  id: number
  prompt_id: number
  prompt_name: string
  prompt_version_id: number
  version_no: number
  dataset_id: number
  dataset_name: string
  model: string
  judge_model: string
  temperature: number
  status: RunStatus
  avg_score: number | null
  total_cost: number | null
  total: number
  completed: number
  failed: number
  started_at: string | null
  finished_at: string | null
  created_at: string
  error: string | null
}

export interface RunStats {
  avg_score: number | null
  total_cost: number
  total_latency_ms: number
  total: number
  completed: number
  failed: number
  by_grader: Record<string, { avg_score: number; weight: number }>
  by_category: Record<string, { avg_score: number; count: number }>
  distribution: number[] // 10 buckets, 0-1..9-10
}

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: 'ok'
  api_key_present: boolean
  db_path: string
  version: string
}

export interface ModelInfo {
  id: string
  label: string
  input_price_per_mtok: number
  output_price_per_mtok: number
}

export interface ModelsResponse {
  models: ModelInfo[]
  default_model: string
  default_judge_model: string
}

// ---------------------------------------------------------------------------
// Prompts
// ---------------------------------------------------------------------------

export interface CreatePromptBody {
  name: string
  description?: string
  template: string
  system_prompt?: string
  model?: string
  temperature?: number
  max_tokens?: number
}
export interface CreatePromptResponse {
  prompt: Prompt
  version: PromptVersion
}
export interface PromptDetailResponse {
  prompt: Prompt
  versions: PromptVersion[]
  graders: Grader[]
}
export interface UpdatePromptBody {
  name?: string
  description?: string
}
export interface CreatePromptVersionBody {
  template: string
  system_prompt?: string
  model?: string
  temperature?: number
  max_tokens?: number
  notes?: string
}
export interface ExtractVariablesBody {
  template: string
}
export interface ExtractVariablesResponse {
  variables: string[]
}

// ---------------------------------------------------------------------------
// Graders
// ---------------------------------------------------------------------------

export interface CreateGraderBody {
  type: GraderType
  name: string
  weight?: number
  config: GraderConfig
  enabled?: boolean
  position?: number
}
export interface UpdateGraderBody {
  name?: string
  weight?: number
  config?: GraderConfig
  enabled?: boolean
  position?: number
}

// ---------------------------------------------------------------------------
// Datasets
// ---------------------------------------------------------------------------

export interface CreateDatasetBody {
  name: string
  description?: string
}
export interface DatasetDetailResponse {
  dataset: Dataset
  cases: TestCase[]
}
export interface UpdateDatasetBody {
  name?: string
  description?: string
}
export interface CreateCaseBody {
  inputs: Record<string, string>
  solution_criteria?: string
  category?: string
  expected_format?: ExpectedFormat
}
export type UpdateCaseBody = Partial<CreateCaseBody>

export interface GenerateDatasetBody {
  dataset_id?: number
  name?: string
  domain_description: string
  variables: string[]
  count: number
  mode: GenerationMode
  model?: string
  prompt_template?: string
}
export interface GenerateDatasetResponse {
  dataset: Dataset
  cases: TestCase[]
}

export interface ImportPreviewResponse {
  format: 'csv' | 'json' | 'jsonl'
  columns: string[]
  rows: Record<string, unknown>[]
  total_rows: number
}
export interface ImportDatasetPayload {
  dataset_id?: number
  name?: string
  mapping: Record<string, string>
  solution_criteria_column?: string
  category_column?: string
  expected_format_column?: string
}
export interface ImportDatasetResponse {
  dataset: Dataset
  cases: TestCase[]
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

export interface CreateRunBody {
  prompt_version_id: number
  dataset_id: number
  model?: string
  temperature?: number
  max_tokens?: number
  judge_model?: string
  concurrency?: number
}
export interface CreateRunResponse {
  run_id: number
  status: 'pending'
}
export interface RunDetailResponse {
  run: RunSummary
  stats: RunStats
  cases: RunCase[]
}
export interface CancelRunResponse {
  status: 'cancelled'
}

export interface RunCompareResponse {
  a: { run: RunSummary; stats: RunStats }
  b: { run: RunSummary; stats: RunStats }
  deltas: {
    avg_score: number
    total_cost: number
    by_grader: Record<string, number>
    by_category: Record<string, number>
  }
  cases: Array<{
    test_case: TestCase
    a: RunCase | null
    b: RunCase | null
    winner: 'a' | 'b' | 'tie'
    delta: number
  }>
  wins: { a: number; b: number; tie: number }
}

// ---------------------------------------------------------------------------
// SSE event payloads — GET /api/runs/{id}/events
// ---------------------------------------------------------------------------

export interface SseRunStarted {
  run_id: number
  total: number
}
export interface SseCaseStarted {
  run_case_id: number
  test_case_id: number
  idx: number
}
export interface SseCaseCompleted {
  run_case_id: number
  test_case_id: number
  idx: number
  final_score: number | null
  latency_ms: number
  cost: number
  status: RunCaseStatus
  output_preview: string
  grades: Grade[]
}
export interface SseCaseFailed {
  run_case_id: number
  idx: number
  error: string
}
export interface SseProgress {
  completed: number
  failed: number
  total: number
  avg_score_so_far: number | null
}
export interface SseRunCompleted {
  run_id: number
  avg_score: number | null
  total_cost: number
  completed: number
  failed: number
}
export interface SseRunFailed {
  run_id: number
  error: string
}
export interface SseCancelled {
  run_id: number
}

export interface SseEventMap {
  run_started: SseRunStarted
  case_started: SseCaseStarted
  case_completed: SseCaseCompleted
  case_failed: SseCaseFailed
  progress: SseProgress
  run_completed: SseRunCompleted
  run_failed: SseRunFailed
  cancelled: SseCancelled
}

export type SseEventName = keyof SseEventMap
