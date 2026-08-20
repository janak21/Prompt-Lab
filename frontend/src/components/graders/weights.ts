import type { Grader } from '@/lib/types'

/**
 * Raw weights are unintuitive (what does "3" mean?) — normalize enabled
 * graders' weights to a percentage of the enabled total so the UI can show
 * "60%" next to a raw weight of 3 (out of 3+1+1). Disabled graders don't
 * contribute to the denominator and show 0%.
 */
export function normalizedContribution(graders: Pick<Grader, 'id' | 'weight' | 'enabled'>[]): Record<number, number> {
  const enabledTotal = graders.filter((g) => g.enabled).reduce((sum, g) => sum + Math.max(0, g.weight), 0)
  const out: Record<number, number> = {}
  for (const g of graders) {
    if (!g.enabled || enabledTotal <= 0) {
      out[g.id] = 0
      continue
    }
    out[g.id] = (Math.max(0, g.weight) / enabledTotal) * 100
  }
  return out
}
