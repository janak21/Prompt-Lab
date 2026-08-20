import type { Grade, RunCase, RunStats } from '../types'

export function computeStats(cases: RunCase[]): RunStats {
  const completed = cases.filter((c) => c.status === 'completed')
  const failed = cases.filter((c) => c.status === 'failed')
  const scores = completed.map((c) => c.final_score).filter((s): s is number => s != null)

  const avg_score = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null
  const total_cost = cases.reduce((a, c) => a + (c.cost ?? 0), 0)
  const total_latency_ms = cases.reduce((a, c) => a + (c.latency_ms ?? 0), 0)

  const byGrader = new Map<string, { sum: number; weight: number; n: number }>()
  for (const c of completed) {
    for (const g of c.grades) {
      const entry = byGrader.get(g.grader_name) ?? { sum: 0, weight: g.weight, n: 0 }
      entry.sum += g.score
      entry.n += 1
      byGrader.set(g.grader_name, entry)
    }
  }
  const by_grader: RunStats['by_grader'] = {}
  for (const [name, v] of byGrader) {
    by_grader[name] = { avg_score: Math.round((v.sum / v.n) * 100) / 100, weight: v.weight }
  }

  const byCategory = new Map<string, { sum: number; n: number }>()
  for (const c of completed) {
    const cat = c.test_case.category ?? 'standard'
    const entry = byCategory.get(cat) ?? { sum: 0, n: 0 }
    if (c.final_score != null) entry.sum += c.final_score
    entry.n += 1
    byCategory.set(cat, entry)
  }
  const by_category: RunStats['by_category'] = {}
  for (const [cat, v] of byCategory) {
    by_category[cat] = { avg_score: Math.round((v.sum / v.n) * 100) / 100, count: v.n }
  }

  const distribution = new Array(10).fill(0)
  for (const s of scores) {
    const bucket = Math.min(9, Math.floor(s))
    distribution[bucket] += 1
  }

  return {
    avg_score: avg_score != null ? Math.round(avg_score * 100) / 100 : null,
    total_cost: Math.round(total_cost * 1e6) / 1e6,
    total_latency_ms,
    total: cases.length,
    completed: completed.length,
    failed: failed.length,
    by_grader,
    by_category,
    distribution,
  } as RunStats
}

export function allGradeNames(cases: RunCase[]): string[] {
  const s = new Set<string>()
  for (const c of cases) for (const g of c.grades as Grade[]) s.add(g.grader_name)
  return [...s]
}
