import type { Grade, RunCase } from '../../lib/types.ts'

interface LocalStats {
  pass_rate: number | null
  avg_score: number | null
  distribution: number[]
  by_grader: Record<string, { avg_score: number; weight: number }>
  by_category: Record<string, { avg_score: number; count: number }>
}

export function computeLocalStats(rows: RunCase[]): LocalStats {
  const completed = rows.filter((r) => r.status === 'completed' || r.status === 'failed')
  const scores = completed.map((r) => r.final_score).filter((s): s is number => s != null)
  const avg_score = scores.length ? Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 100) / 100 : null
  const distribution = new Array(10).fill(0)
  for (const s of scores) distribution[Math.min(9, Math.max(0, Math.floor(s)))] += 1

  const byGrader = new Map<string, { sum: number; weight: number; n: number }>()
  for (const r of completed) {
    for (const g of r.grades as Grade[]) {
      if (g.details._status && g.details._status !== 'scored') continue
      const e = byGrader.get(g.grader_name) ?? { sum: 0, weight: g.weight, n: 0 }
      e.sum += g.score
      e.n += 1
      byGrader.set(g.grader_name, e)
    }
  }
  const by_grader: LocalStats['by_grader'] = {}
  for (const [name, v] of byGrader) by_grader[name] = { avg_score: Math.round((v.sum / v.n) * 100) / 100, weight: v.weight }

  const byCategory = new Map<string, { sum: number; n: number }>()
  for (const r of completed) {
    if (r.final_score == null) continue
    const cat = r.test_case.category ?? 'uncategorized'
    const e = byCategory.get(cat) ?? { sum: 0, n: 0 }
    if (r.final_score != null) e.sum += r.final_score
    e.n += 1
    byCategory.set(cat, e)
  }
  const by_category: LocalStats['by_category'] = {}
  for (const [cat, v] of byCategory) by_category[cat] = { avg_score: v.n ? Math.round((v.sum / v.n) * 100) / 100 : 0, count: v.n }

  const pass_rate = rows.length ? rows.filter((r) => r.passed === undefined ? r.status === 'completed' : r.passed === true).length / rows.length : null
  return { avg_score, pass_rate, distribution, by_grader, by_category }
}
