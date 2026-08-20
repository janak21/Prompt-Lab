// NOTE: ApiError is imported from '../apiError', not '../api'. api.ts does a
// top-level `await import('./mock')`; if this file statically imported
// ApiError from '../api' it would create a circular import into a module
// that's mid-evaluation on its own top-level await, deadlocking the module
// graph (main.tsx never runs, silently — no console output at all). Only
// the `ApiClient` type is imported from '../api', which is erased at
// compile time (verbatimModuleSyntax) and carries no runtime edge.
import { ApiError } from '../apiError'
import type { ApiClient } from '../api'
import type { ValidationIssue } from '../types'
import type {
  CancelRunResponse,
  CreateCaseBody,
  CreateDatasetBody,
  CreateGraderBody,
  CreatePromptBody,
  CreatePromptResponse,
  CreatePromptVersionBody,
  CreateRunBody,
  CreateRunResponse,
  Dataset,
  DatasetDetailResponse,
  ExtractVariablesResponse,
  GenerateDatasetBody,
  GenerateDatasetResponse,
  Grader,
  HealthResponse,
  ImportDatasetPayload,
  ImportDatasetResponse,
  ImportPreviewResponse,
  ModelsResponse,
  Prompt,
  PromptDetailResponse,
  PromptVersion,
  RunCompareResponse,
  RunDetailResponse,
  RunSummary,
  TestCase,
  UpdateCaseBody,
  UpdateDatasetBody,
  UpdateGraderBody,
  UpdatePromptBody,
} from '../types'
import { DEFAULT_JUDGE_MODEL, DEFAULT_MODEL, MODELS } from './seed'
import { extractVariableNames } from './rng'
import { computeStats } from './stats'
import { cancelSimulatedRun, mockSubscribeToRunEvents, startSimulatedRun } from './stream'
import { delay, nowIso, store } from './store'

function notFound(what: string): never {
  throw new ApiError(404, `${what} not found`)
}

async function getHealth(): Promise<HealthResponse> {
  return delay({ status: 'ok', api_key_present: true, db_path: 'promptlab.db (mock)', version: 'mock' })
}
async function getModels(): Promise<ModelsResponse> {
  return delay({ models: MODELS, default_model: DEFAULT_MODEL, default_judge_model: DEFAULT_JUDGE_MODEL })
}

// ---------------------------------------------------------------------------
// Prompts
// ---------------------------------------------------------------------------

async function listPrompts(): Promise<Prompt[]> {
  return delay([...store.prompts].sort((a, b) => b.updated_at.localeCompare(a.updated_at)))
}
async function createPrompt(body: CreatePromptBody): Promise<CreatePromptResponse> {
  const id = store.ids.prompt++
  const timestamp = nowIso()
  const prompt: Prompt = {
    id,
    name: body.name,
    description: body.description ?? null,
    created_at: timestamp,
    updated_at: timestamp,
    version_count: 1,
    latest_version_no: 1,
  }
  const versionId = store.ids.version++
  const version: PromptVersion = {
    id: versionId,
    prompt_id: id,
    version_no: 1,
    template: body.template,
    system_prompt: body.system_prompt ?? null,
    model: body.model ?? null,
    temperature: body.temperature ?? null,
    max_tokens: body.max_tokens ?? null,
    notes: null,
    created_at: timestamp,
    variables: extractVariableNames(body.template),
  }
  store.prompts.push(prompt)
  store.versions.push(version)
  return delay({ prompt, version })
}
async function getPrompt(id: number): Promise<PromptDetailResponse> {
  const prompt = store.prompts.find((p) => p.id === id)
  if (!prompt) notFound('Prompt')
  const versions = store.versions.filter((v) => v.prompt_id === id).sort((a, b) => b.version_no - a.version_no)
  const graders = store.graders.filter((g) => g.prompt_id === id).sort((a, b) => a.position - b.position)
  return delay({ prompt, versions, graders })
}
async function updatePrompt(id: number, body: UpdatePromptBody): Promise<Prompt> {
  const prompt = store.prompts.find((p) => p.id === id)
  if (!prompt) notFound('Prompt')
  let changed = false
  if (body.name != null) {
    prompt.name = body.name
    changed = true
  }
  if (body.description != null) {
    prompt.description = body.description
    changed = true
  }
  if (changed) prompt.updated_at = nowIso()
  return delay(prompt)
}
async function deletePrompt(id: number): Promise<void> {
  store.prompts = store.prompts.filter((p) => p.id !== id)
  store.versions = store.versions.filter((v) => v.prompt_id !== id)
  store.graders = store.graders.filter((g) => g.prompt_id !== id)
  return delay(undefined, 150)
}
async function createPromptVersion(id: number, body: CreatePromptVersionBody): Promise<PromptVersion> {
  const prompt = store.prompts.find((p) => p.id === id)
  if (!prompt) notFound('Prompt')
  const versionNo = prompt.latest_version_no + 1
  const version: PromptVersion = {
    id: store.ids.version++,
    prompt_id: id,
    version_no: versionNo,
    template: body.template,
    system_prompt: body.system_prompt ?? null,
    model: body.model ?? null,
    temperature: body.temperature ?? null,
    max_tokens: body.max_tokens ?? null,
    notes: body.notes ?? null,
    created_at: nowIso(),
    variables: extractVariableNames(body.template),
  }
  store.versions.push(version)
  prompt.version_count += 1
  prompt.latest_version_no = versionNo
  prompt.updated_at = version.created_at
  return delay(version)
}
async function getPromptVersion(id: number): Promise<PromptVersion> {
  const v = store.versions.find((x) => x.id === id)
  if (!v) notFound('Prompt version')
  return delay(v)
}
async function extractVariables(template: string): Promise<ExtractVariablesResponse> {
  return delay({ variables: extractVariableNames(template) }, 80)
}

// ---------------------------------------------------------------------------
// Graders
// ---------------------------------------------------------------------------

async function listGraders(promptId: number): Promise<Grader[]> {
  return delay(store.graders.filter((g) => g.prompt_id === promptId).sort((a, b) => a.position - b.position))
}
async function createGrader(promptId: number, body: CreateGraderBody): Promise<Grader> {
  const grader: Grader = {
    id: store.ids.grader++,
    prompt_id: promptId,
    type: body.type,
    name: body.name,
    weight: body.weight ?? 1,
    config: body.config,
    enabled: body.enabled ?? true,
    position: body.position ?? store.graders.filter((g) => g.prompt_id === promptId).length,
  }
  store.graders.push(grader)
  return delay(grader)
}
async function updateGrader(id: number, body: UpdateGraderBody): Promise<Grader> {
  const grader = store.graders.find((g) => g.id === id)
  if (!grader) notFound('Grader')
  Object.assign(grader, body)
  return delay(grader)
}
async function deleteGrader(id: number): Promise<void> {
  store.graders = store.graders.filter((g) => g.id !== id)
  return delay(undefined, 150)
}

// ---------------------------------------------------------------------------
// Datasets
// ---------------------------------------------------------------------------

async function listDatasets(): Promise<Dataset[]> {
  return delay([...store.datasets].sort((a, b) => b.created_at.localeCompare(a.created_at)))
}
async function createDataset(body: CreateDatasetBody): Promise<Dataset> {
  const dataset: Dataset = {
    id: store.ids.dataset++,
    name: body.name,
    description: body.description ?? null,
    source: 'manual',
    created_at: nowIso(),
    case_count: 0,
    variables: [],
  }
  store.datasets.push(dataset)
  return delay(dataset)
}
async function getDataset(id: number): Promise<DatasetDetailResponse> {
  const dataset = store.datasets.find((d) => d.id === id)
  if (!dataset) notFound('Dataset')
  const cases = store.cases.filter((c) => c.dataset_id === id)
  return delay({ dataset, cases })
}
async function updateDataset(id: number, body: UpdateDatasetBody): Promise<Dataset> {
  const dataset = store.datasets.find((d) => d.id === id)
  if (!dataset) notFound('Dataset')
  if (body.name != null) dataset.name = body.name
  if (body.description != null) dataset.description = body.description
  return delay(dataset)
}
async function deleteDataset(id: number): Promise<void> {
  store.datasets = store.datasets.filter((d) => d.id !== id)
  store.cases = store.cases.filter((c) => c.dataset_id !== id)
  return delay(undefined, 150)
}
function recomputeDatasetMeta(datasetId: number) {
  const dataset = store.datasets.find((d) => d.id === datasetId)
  if (!dataset) return
  const cases = store.cases.filter((c) => c.dataset_id === datasetId)
  dataset.case_count = cases.length
  const vars = new Set<string>()
  for (const c of cases) for (const k of Object.keys(c.inputs)) vars.add(k)
  dataset.variables = [...vars]
}
async function createCase(datasetId: number, body: CreateCaseBody): Promise<TestCase> {
  const testCase: TestCase = {
    id: store.ids.case++,
    dataset_id: datasetId,
    inputs: body.inputs,
    solution_criteria: body.solution_criteria ?? null,
    category: body.category ?? 'standard',
    expected_format: body.expected_format ?? null,
    created_at: nowIso(),
  }
  store.cases.push(testCase)
  recomputeDatasetMeta(datasetId)
  return delay(testCase)
}
async function updateCase(id: number, body: UpdateCaseBody): Promise<TestCase> {
  const testCase = store.cases.find((c) => c.id === id)
  if (!testCase) notFound('Test case')
  if (body.inputs != null) testCase.inputs = body.inputs
  if (body.solution_criteria !== undefined) testCase.solution_criteria = body.solution_criteria ?? null
  if (body.category !== undefined) testCase.category = body.category ?? null
  if (body.expected_format !== undefined) testCase.expected_format = body.expected_format ?? null
  recomputeDatasetMeta(testCase.dataset_id)
  return delay(testCase)
}
async function deleteCase(id: number): Promise<void> {
  const testCase = store.cases.find((c) => c.id === id)
  store.cases = store.cases.filter((c) => c.id !== id)
  if (testCase) recomputeDatasetMeta(testCase.dataset_id)
  return delay(undefined, 120)
}

const GENERATED_CATEGORIES = [
  'empty_input', 'missing_field', 'ambiguous', 'contradictory', 'boundary_length',
  'wrong_language', 'special_characters', 'prompt_injection', 'out_of_domain', 'hostile_formatting',
] as const

async function generateDataset(body: GenerateDatasetBody): Promise<GenerateDatasetResponse> {
  let dataset: Dataset
  if (body.dataset_id) {
    const existing = store.datasets.find((d) => d.id === body.dataset_id)
    if (!existing) notFound('Dataset')
    dataset = existing
  } else {
    dataset = {
      id: store.ids.dataset++,
      name: body.name ?? 'Generated dataset',
      description: body.domain_description,
      source: 'generated',
      created_at: nowIso(),
      case_count: 0,
      variables: body.variables,
    }
    store.datasets.push(dataset)
  }

  const cases: TestCase[] = []
  for (let i = 0; i < body.count; i++) {
    const category =
      body.mode === 'standard'
        ? 'standard'
        : body.mode === 'adversarial'
          ? GENERATED_CATEGORIES[i % GENERATED_CATEGORIES.length]
          : i % 2 === 0
            ? 'standard'
            : GENERATED_CATEGORIES[i % GENERATED_CATEGORIES.length]
    const inputs: Record<string, string> = {}
    for (const v of body.variables) {
      inputs[v] = category === 'empty_input' ? '' : `Generated ${v} value for case ${i + 1} (${category}).`
    }
    const tc: TestCase = {
      id: store.ids.case++,
      dataset_id: dataset.id,
      inputs,
      solution_criteria: `Auto-generated case exercising the "${category}" scenario for: ${body.domain_description.slice(0, 80)}`,
      category,
      expected_format: null,
      created_at: nowIso(),
    }
    store.cases.push(tc)
    cases.push(tc)
  }
  recomputeDatasetMeta(dataset.id)
  return delay({ dataset, cases }, 1400)
}

async function importPreview(file: File): Promise<ImportPreviewResponse> {
  const text = await file.text()
  const format: ImportPreviewResponse['format'] = file.name.endsWith('.jsonl')
    ? 'jsonl'
    : file.name.endsWith('.json')
      ? 'json'
      : 'csv'
  let rows: Record<string, unknown>[] = []
  let columns: string[] = []
  try {
    if (format === 'csv') {
      const lines = text.trim().split('\n')
      columns = lines[0].split(',').map((c) => c.trim())
      rows = lines.slice(1, 11).map((line) => {
        const vals = line.split(',')
        return Object.fromEntries(columns.map((c, i) => [c, vals[i]?.trim() ?? '']))
      })
    } else if (format === 'jsonl') {
      const parsed = text.trim().split('\n').map((l) => JSON.parse(l))
      rows = parsed.slice(0, 10)
      columns = rows.length ? Object.keys(rows[0]) : []
    } else {
      const parsed = JSON.parse(text)
      const arr = Array.isArray(parsed) ? parsed : [parsed]
      rows = arr.slice(0, 10)
      columns = rows.length ? Object.keys(rows[0]) : []
    }
  } catch {
    throw new ApiError(422, [
      { loc: ['body', 'file'], msg: 'Could not parse file — check the format and try again.', type: 'value_error' },
    ] satisfies ValidationIssue[])
  }
  return delay({ format, columns, rows, total_rows: rows.length }, 400)
}
async function importDataset(file: File, payload: ImportDatasetPayload): Promise<ImportDatasetResponse> {
  const preview = await importPreview(file)
  let dataset: Dataset
  if (payload.dataset_id != null) {
    const existing = store.datasets.find((d) => d.id === payload.dataset_id)
    if (!existing) notFound('Dataset')
    dataset = existing
  } else {
    dataset = {
      id: store.ids.dataset++,
      name: payload.name ?? file.name,
      description: `Imported from ${file.name}`,
      source: 'imported',
      created_at: nowIso(),
      case_count: 0,
      variables: Object.values(payload.mapping),
    }
    store.datasets.push(dataset)
  }
  const cases: TestCase[] = preview.rows.map((row) => {
    const inputs: Record<string, string> = {}
    for (const [col, varName] of Object.entries(payload.mapping)) inputs[varName] = String(row[col] ?? '')
    return {
      id: store.ids.case++,
      dataset_id: dataset.id,
      inputs,
      solution_criteria: payload.solution_criteria_column ? String(row[payload.solution_criteria_column] ?? '') : null,
      category: payload.category_column ? String(row[payload.category_column] ?? 'standard') : 'standard',
      expected_format: payload.expected_format_column ? (String(row[payload.expected_format_column] ?? '') as never) : null,
      created_at: nowIso(),
    }
  })
  store.cases.push(...cases)
  recomputeDatasetMeta(dataset.id)
  return delay({ dataset, cases }, 500)
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

async function createRun(body: CreateRunBody): Promise<CreateRunResponse> {
  const version = store.versions.find((v) => v.id === body.prompt_version_id)
  if (!version) notFound('Prompt version')
  const dataset = store.datasets.find((d) => d.id === body.dataset_id)
  if (!dataset) notFound('Dataset')

  const missing = version.variables.filter((v) => !dataset.variables.includes(v))
  if (missing.length) {
    throw new ApiError(
      422,
      missing.map(
        (v): ValidationIssue => ({
          loc: ['body', 'dataset_id'],
          msg: `Dataset is missing variable "${v}" required by the template.`,
          type: 'value_error.missing_variable',
        }),
      ),
    )
  }

  const prompt = store.prompts.find((p) => p.id === version.prompt_id)!
  const id = store.ids.run++
  const summary: RunSummary = {
    id,
    prompt_id: version.prompt_id,
    prompt_name: prompt.name,
    prompt_version_id: version.id,
    version_no: version.version_no,
    dataset_id: dataset.id,
    dataset_name: dataset.name,
    model: body.model ?? version.model ?? DEFAULT_MODEL,
    judge_model: body.judge_model ?? DEFAULT_JUDGE_MODEL,
    temperature: body.temperature ?? version.temperature ?? 0.2,
    status: 'pending',
    avg_score: null,
    total_cost: null,
    total: 0,
    completed: 0,
    failed: 0,
    started_at: null,
    finished_at: null,
    created_at: nowIso(),
    error: null,
  }
  store.runs.push(summary)

  const testCases = store.cases.filter((c) => c.dataset_id === dataset.id)
  const graders = store.graders.filter((g) => g.prompt_id === version.prompt_id)
  // Kick off the simulation on a short delay so the client can subscribe first.
  setTimeout(() => startSimulatedRun(id, version.template, testCases, graders), 150)

  return delay({ run_id: id, status: 'pending' }, 120)
}

async function listRuns(params?: { prompt_id?: number; dataset_id?: number; limit?: number }): Promise<RunSummary[]> {
  let runs = [...store.runs]
  if (params?.prompt_id != null) runs = runs.filter((r) => r.prompt_id === params.prompt_id)
  if (params?.dataset_id != null) runs = runs.filter((r) => r.dataset_id === params.dataset_id)
  runs.sort((a, b) => b.created_at.localeCompare(a.created_at))
  if (params?.limit != null) runs = runs.slice(0, params.limit)
  return delay(runs)
}
async function getRun(id: number): Promise<RunDetailResponse> {
  const run = store.runs.find((r) => r.id === id)
  if (!run) notFound('Run')
  const cases = store.runCases.filter((c) => c.run_id === id).sort((a, b) => a.idx - b.idx)
  return delay({ run, stats: computeStats(cases), cases })
}
async function cancelRun(id: number): Promise<CancelRunResponse> {
  cancelSimulatedRun(id)
  return delay({ status: 'cancelled' }, 100)
}
async function deleteRun(id: number): Promise<void> {
  store.runs = store.runs.filter((r) => r.id !== id)
  store.runCases = store.runCases.filter((c) => c.run_id !== id)
  return delay(undefined, 150)
}
async function compareRuns(a: number, b: number): Promise<RunCompareResponse> {
  const runA = store.runs.find((r) => r.id === a)
  const runB = store.runs.find((r) => r.id === b)
  if (!runA || !runB) notFound('Run')
  if (runA.dataset_id !== runB.dataset_id) {
    throw new ApiError(400, 'Cannot compare runs that used different datasets.')
  }
  const casesA = store.runCases.filter((c) => c.run_id === a)
  const casesB = store.runCases.filter((c) => c.run_id === b)
  const statsA = computeStats(casesA)
  const statsB = computeStats(casesB)

  const testCases = store.cases.filter((c) => c.dataset_id === runA.dataset_id).sort((x, y) => x.id - y.id)
  let winsA = 0
  let winsB = 0
  let ties = 0
  const cases = testCases.map((tc) => {
    const ca = casesA.find((c) => c.test_case_id === tc.id) ?? null
    const cb = casesB.find((c) => c.test_case_id === tc.id) ?? null
    const sa = ca?.final_score ?? null
    const sb = cb?.final_score ?? null
    let winner: 'a' | 'b' | 'tie' = 'tie'
    let delta = 0
    if (sa != null && sb != null) {
      delta = Math.round((sa - sb) * 100) / 100
      if (Math.abs(delta) < 0.05) {
        winner = 'tie'
        ties += 1
      } else if (delta > 0) {
        winner = 'a'
        winsA += 1
      } else {
        winner = 'b'
        winsB += 1
      }
    } else {
      ties += 1
    }
    return { test_case: tc, a: ca, b: cb, winner, delta }
  })

  const by_grader: Record<string, number> = {}
  for (const name of new Set([...Object.keys(statsA.by_grader), ...Object.keys(statsB.by_grader)])) {
    by_grader[name] = Math.round(((statsA.by_grader[name]?.avg_score ?? 0) - (statsB.by_grader[name]?.avg_score ?? 0)) * 100) / 100
  }
  const by_category: Record<string, number> = {}
  for (const name of new Set([...Object.keys(statsA.by_category), ...Object.keys(statsB.by_category)])) {
    by_category[name] = Math.round(((statsA.by_category[name]?.avg_score ?? 0) - (statsB.by_category[name]?.avg_score ?? 0)) * 100) / 100
  }

  return delay({
    a: { run: runA, stats: statsA },
    b: { run: runB, stats: statsB },
    deltas: {
      avg_score: Math.round(((statsA.avg_score ?? 0) - (statsB.avg_score ?? 0)) * 100) / 100,
      total_cost: Math.round((statsA.total_cost - statsB.total_cost) * 1e6) / 1e6,
      by_grader,
      by_category,
    },
    cases,
    wins: { a: winsA, b: winsB, tie: ties },
  })
}

export const mockApi: ApiClient = {
  getHealth,
  getModels,
  listPrompts,
  createPrompt,
  getPrompt,
  updatePrompt,
  deletePrompt,
  createPromptVersion,
  getPromptVersion,
  extractVariables,
  listGraders,
  createGrader,
  updateGrader,
  deleteGrader,
  listDatasets,
  createDataset,
  getDataset,
  updateDataset,
  deleteDataset,
  createCase,
  updateCase,
  deleteCase,
  generateDataset,
  importPreview,
  importDataset,
  createRun,
  listRuns,
  getRun,
  cancelRun,
  deleteRun,
  compareRuns,
}

export { mockSubscribeToRunEvents }
