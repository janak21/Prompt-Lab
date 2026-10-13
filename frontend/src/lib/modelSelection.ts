import type { ModelInfo } from './types.ts'

export function effectiveRunModel(override: string, saved: string | null | undefined, fallback: string, models: Pick<ModelInfo, 'id'>[]): string {
  return override || (models.some((m) => m.id === saved) ? saved ?? fallback : fallback)
}
