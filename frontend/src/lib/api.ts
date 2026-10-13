// Typed fetch client for the PromptLab API. One function per endpoint in
// docs/API_CONTRACT.md. In mock mode (VITE_MOCK=1) every call is served from
// src/lib/mock/ instead of hitting the network — see the dispatch at the
// bottom of this file.

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
} from './types'

import { ApiError, normalizeDetail } from './apiError'

export { ApiError, getFieldError } from './apiError'

export const MOCK_MODE = import.meta.env.VITE_MOCK === '1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError(0, 'Network error — is the PromptLab server running?')
  }

  if (res.status === 204) {
    return undefined as T
  }

  const text = await res.text()
  const data = text ? safeJsonParse(text) : undefined

  if (!res.ok) {
    const fallback = res.statusText || `Request failed with status ${res.status}`
    const raw = data && typeof data === 'object' && 'detail' in data ? (data as { detail: unknown }).detail : undefined
    throw new ApiError(res.status, normalizeDetail(raw, fallback))
  }

  return data as T
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text }
  }
}

function json(body: unknown): RequestInit {
  return { body: JSON.stringify(body) }
}

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

async function getHealth(): Promise<HealthResponse> {
  return request('/health')
}
async function getModels(refresh = false): Promise<ModelsResponse> {
  return request(refresh ? '/models?refresh=true' : '/models')
}

// ---------------------------------------------------------------------------
// Prompts
// ---------------------------------------------------------------------------

async function listPrompts(): Promise<Prompt[]> {
  return request('/prompts')
}
async function createPrompt(body: CreatePromptBody): Promise<CreatePromptResponse> {
  return request('/prompts', { method: 'POST', ...json(body) })
}
async function getPrompt(id: number): Promise<PromptDetailResponse> {
  return request(`/prompts/${id}`)
}
async function updatePrompt(id: number, body: UpdatePromptBody): Promise<Prompt> {
  return request(`/prompts/${id}`, { method: 'PATCH', ...json(body) })
}
async function deletePrompt(id: number): Promise<void> {
  return request(`/prompts/${id}`, { method: 'DELETE' })
}
async function createPromptVersion(id: number, body: CreatePromptVersionBody): Promise<PromptVersion> {
  return request(`/prompts/${id}/versions`, { method: 'POST', ...json(body) })
}
async function getPromptVersion(id: number): Promise<PromptVersion> {
  return request(`/prompt-versions/${id}`)
}
async function extractVariables(template: string): Promise<ExtractVariablesResponse> {
  return request('/prompts/extract-variables', { method: 'POST', ...json({ template }) })
}

// ---------------------------------------------------------------------------
// Graders
// ---------------------------------------------------------------------------

async function listGraders(promptId: number): Promise<Grader[]> {
  return request(`/prompts/${promptId}/graders`)
}
async function createGrader(promptId: number, body: CreateGraderBody): Promise<Grader> {
  return request(`/prompts/${promptId}/graders`, { method: 'POST', ...json(body) })
}
async function updateGrader(id: number, body: UpdateGraderBody): Promise<Grader> {
  return request(`/graders/${id}`, { method: 'PATCH', ...json(body) })
}
async function deleteGrader(id: number): Promise<void> {
  return request(`/graders/${id}`, { method: 'DELETE' })
}

// ---------------------------------------------------------------------------
// Datasets
// ---------------------------------------------------------------------------

async function listDatasets(): Promise<Dataset[]> {
  return request('/datasets')
}
async function createDataset(body: CreateDatasetBody): Promise<Dataset> {
  return request('/datasets', { method: 'POST', ...json(body) })
}
async function getDataset(id: number): Promise<DatasetDetailResponse> {
  return request(`/datasets/${id}`)
}
async function updateDataset(id: number, body: UpdateDatasetBody): Promise<Dataset> {
  return request(`/datasets/${id}`, { method: 'PATCH', ...json(body) })
}
async function deleteDataset(id: number): Promise<void> {
  return request(`/datasets/${id}`, { method: 'DELETE' })
}
async function createCase(datasetId: number, body: CreateCaseBody): Promise<TestCase> {
  return request(`/datasets/${datasetId}/cases`, { method: 'POST', ...json(body) })
}
async function updateCase(id: number, body: UpdateCaseBody): Promise<TestCase> {
  return request(`/cases/${id}`, { method: 'PATCH', ...json(body) })
}
async function deleteCase(id: number): Promise<void> {
  return request(`/cases/${id}`, { method: 'DELETE' })
}
async function generateDataset(body: GenerateDatasetBody): Promise<GenerateDatasetResponse> {
  return request('/datasets/generate', { method: 'POST', ...json(body) })
}
async function importPreview(file: File): Promise<ImportPreviewResponse> {
  const fd = new FormData()
  fd.append('file', file)
  return request('/datasets/import/preview', { method: 'POST', body: fd })
}
async function importDataset(file: File, payload: ImportDatasetPayload): Promise<ImportDatasetResponse> {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('payload', JSON.stringify(payload))
  return request('/datasets/import', { method: 'POST', body: fd })
}

// ---------------------------------------------------------------------------
// Runs
// ---------------------------------------------------------------------------

async function createRun(body: CreateRunBody): Promise<CreateRunResponse> {
  return request('/runs', { method: 'POST', ...json(body) })
}
async function listRuns(params?: { prompt_id?: number; dataset_id?: number; limit?: number }): Promise<RunSummary[]> {
  const qs = new URLSearchParams()
  if (params?.prompt_id != null) qs.set('prompt_id', String(params.prompt_id))
  if (params?.dataset_id != null) qs.set('dataset_id', String(params.dataset_id))
  if (params?.limit != null) qs.set('limit', String(params.limit))
  const suffix = qs.toString() ? `?${qs}` : ''
  return request(`/runs${suffix}`)
}
async function getRun(id: number): Promise<RunDetailResponse> {
  return request(`/runs/${id}`)
}
async function cancelRun(id: number): Promise<CancelRunResponse> {
  return request(`/runs/${id}/cancel`, { method: 'POST' })
}
async function deleteRun(id: number): Promise<void> {
  return request(`/runs/${id}`, { method: 'DELETE' })
}
async function compareRuns(a: number, b: number): Promise<RunCompareResponse> {
  return request(`/runs/compare?a=${a}&b=${b}`)
}

export const realApi = {
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

export type ApiClient = typeof realApi

// The mock client is dynamically composed at module init so that a plain
// production build never bundles seed data unless VITE_MOCK=1. Pages should
// always import `api` from this module rather than `realApi` directly.
let api: ApiClient = realApi
if (MOCK_MODE) {
  const { mockApi } = await import('./mock')
  api = mockApi
}

export { api }
