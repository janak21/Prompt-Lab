// ApiError lives in its own module, separate from api.ts, deliberately.
// api.ts does `await import('./mock')` at module scope (top-level await) to
// pick the mock client, and src/lib/mock/index.ts needs the ApiError class
// at runtime. If mock/index.ts imported it from '../api' directly, that's a
// circular static import into a module that's paused mid-evaluation on its
// own top-level await — the module graph never resolves, main.tsx never
// runs, and nothing lands in the console because evaluation simply never
// completes. Breaking ApiError out here removes the cycle.

import type { ErrorDetail, ValidationIssue } from './types'

/**
 * `detail` preserves whatever the server sent: a plain string for most
 * errors, or the array of Pydantic `{loc, msg, type}` issues FastAPI emits
 * for 422s. `.message` (from `Error`) is always a flattened string, safe to
 * show directly; use `getFieldError` to attach a specific issue to a field.
 */
export class ApiError extends Error {
  status: number
  detail: ErrorDetail
  constructor(status: number, detail: ErrorDetail) {
    super(typeof detail === 'string' ? detail : summarizeValidationIssues(detail))
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function summarizeValidationIssues(issues: ValidationIssue[]): string {
  if (issues.length === 0) return 'Validation failed.'
  return issues.map((i) => `${fieldPathLabel(i.loc)}: ${i.msg}`).join('; ')
}

function fieldPathLabel(loc: (string | number)[]): string {
  const parts = loc.filter((p) => p !== 'body' && p !== 'query' && p !== 'path')
  return parts.length ? parts.join('.') : 'request'
}

/**
 * Look up the validation message for a specific field, e.g.
 * `getFieldError(err.detail, 'weight')`. Matches on the last segment of
 * each issue's `loc` (Pydantic nests as `["body", "weight"]`). Returns
 * undefined for string details or when no issue targets that field.
 */
export function getFieldError(detail: ErrorDetail, field: string): string | undefined {
  if (typeof detail === 'string') return undefined
  const issue = detail.find((i) => i.loc[i.loc.length - 1] === field)
  return issue?.msg
}

export function normalizeDetail(raw: unknown, fallback: string): ErrorDetail {
  if (typeof raw === 'string') return raw
  if (Array.isArray(raw)) return raw as ValidationIssue[]
  if (raw == null) return fallback
  return String(raw)
}
