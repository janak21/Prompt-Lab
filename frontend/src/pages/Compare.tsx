import { useEffect, useMemo, useState } from 'react'
import { CategoryBadge } from '@/components/datasets/CategoryBadge'
import { categoryLabel } from '@/components/datasets/category'
import { CompareCaseDrawer } from '@/components/compare/CompareCaseDrawer'
import type { CompareCaseRow } from '@/components/compare/CompareCaseDrawer'
import { DeltaList } from '@/components/compare/DeltaList'
import {
  EmptyState,
  ErrorState,
  MetricTile,
  OutcomePill,
  ScoreBadge,
  Select,
  Skeleton,
  Table,
} from '@/components/ui'
import type { Column } from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import type { RunCompareResponse, RunSummary } from '@/lib/types'

function fmtCost(v: number) {
  const sign = v > 0 ? '+' : ''
  return `${sign}$${v.toFixed(4)}`
}
function fmtScore(v: number) {
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}`
}
function deltaColor(v: number) {
  return v > 0.05 ? 'var(--win)' : v < -0.05 ? 'var(--loss)' : 'var(--tie)'
}

export function ComparePage() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [runsError, setRunsError] = useState<string | null>(null)
  const [aId, setAId] = useState<number | ''>('')
  const [bId, setBId] = useState<number | ''>('')
  const [result, setResult] = useState<RunCompareResponse | null>(null)
  const [compareError, setCompareError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [drawerRow, setDrawerRow] = useState<CompareCaseRow | null>(null)

  const loadRuns = () => {
    setRunsError(null)
    setRuns(null)
    api
      .listRuns({ limit: 200 })
      .then((r) => setRuns(r.filter((x) => x.status === 'completed')))
      .catch((e: unknown) => setRunsError(e instanceof ApiError ? e.message : 'Failed to load runs.'))
  }
  useEffect(loadRuns, [])

  const runA = runs?.find((r) => r.id === aId) ?? null
  // Only runs on the same dataset as A are offered for B — the API 400s otherwise.
  const bOptions = useMemo(() => {
    if (!runs) return []
    return runs.filter((r) => r.id !== aId && (!runA || r.dataset_id === runA.dataset_id))
  }, [runs, aId, runA])

  useEffect(() => {
    if (bId && !bOptions.some((r) => r.id === bId)) setBId('')
  }, [bOptions, bId])

  useEffect(() => {
    if (!aId || !bId) {
      setResult(null)
      return
    }
    setLoading(true)
    setCompareError(null)
    api
      .compareRuns(Number(aId), Number(bId))
      .then(setResult)
      .catch((e: unknown) => setCompareError(e instanceof ApiError ? e.message : 'Failed to compare runs.'))
      .finally(() => setLoading(false))
  }, [aId, bId])

  const aLabel = runA ? `${runA.prompt_name} v${runA.version_no} (A)` : 'A'
  const bLabel = result ? `${result.b.run.prompt_name} v${result.b.run.version_no} (B)` : 'B'

  const graderDeltas = result
    ? Object.keys({ ...result.a.stats.by_grader, ...result.b.stats.by_grader }).map((name) => ({
        label: name,
        a: result.a.stats.by_grader[name]?.avg_score ?? null,
        b: result.b.stats.by_grader[name]?.avg_score ?? null,
        delta: result.deltas.by_grader[name] ?? 0,
      }))
    : []
  const categoryDeltas = result
    ? Object.keys({ ...result.a.stats.by_category, ...result.b.stats.by_category }).map((cat) => ({
        label: categoryLabel(cat),
        a: result.a.stats.by_category[cat]?.avg_score ?? null,
        b: result.b.stats.by_category[cat]?.avg_score ?? null,
        delta: result.deltas.by_category[cat] ?? 0,
      }))
    : []

  const columns: Column<RunCompareResponse['cases'][number]>[] = result
    ? [
        {
          key: 'category',
          header: 'Category',
          sortValue: (r) => categoryLabel(r.test_case.category),
          render: (r) => <CategoryBadge category={r.test_case.category} />,
        },
        {
          key: 'a',
          header: 'A',
          align: 'right',
          sortValue: (r) => r.a?.final_score ?? -1,
          render: (r) => <ScoreBadge score={r.a?.final_score ?? null} size="sm" />,
        },
        {
          key: 'b',
          header: 'B',
          align: 'right',
          sortValue: (r) => r.b?.final_score ?? -1,
          render: (r) => <ScoreBadge score={r.b?.final_score ?? null} size="sm" />,
        },
        {
          key: 'delta',
          header: 'Δ (A − B)',
          align: 'right',
          mono: true,
          sortValue: (r) => r.delta,
          render: (r) => (
            <span className="font-semibold" style={{ color: deltaColor(r.delta) }}>
              {fmtScore(r.delta)}
            </span>
          ),
        },
        { key: 'gates', header: 'Pass A / B', render: (r) => (r.a?.passed == null ? '—' : r.a.passed ? 'Pass' : 'Fail') + ' / ' + (r.b?.passed == null ? '—' : r.b.passed ? 'Pass' : 'Fail') },
        { key: 'winner', header: 'Score outcome', align: 'right', sortValue: (r) => r.winner, render: (r) => <OutcomePill outcome={r.winner} /> },
      ]
    : []

  return (
    <div className="flex flex-col gap-5 p-6">
      <div>
        <h1 className="text-[17px] font-semibold text-[var(--text-primary)]">Compare</h1>
        <p className="text-[13px] text-[var(--text-secondary)]">
          Compare two completed runs on the same dataset. Delta is always <span className="font-mono">A − B</span>.
        </p>
      </div>

      {runsError ? (
        <ErrorState message="Couldn't load runs" detail={runsError} onRetry={loadRuns} />
      ) : runs === null ? (
        <div className="grid grid-cols-2 gap-3">
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
        </div>
      ) : runs.length < 2 ? (
        <EmptyState
          title="Need at least two completed runs"
          description="Launch runs on the Runs page, then come back here to compare two that used the same dataset."
          action={<span className="text-[12px] text-[var(--text-tertiary)]">Go to Runs</span>}
        />
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Run A"
            value={aId === '' ? '' : String(aId)}
            onChange={(e) => setAId(e.target.value ? Number(e.target.value) : '')}
            placeholder="Select a run"
            options={runs.map((r) => ({ value: String(r.id), label: `${r.prompt_name} v${r.version_no} — ${r.dataset_name} — ${r.model}` }))}
          />
          <Select
            label="Run B"
            value={bId === '' ? '' : String(bId)}
            onChange={(e) => setBId(e.target.value ? Number(e.target.value) : '')}
            placeholder={aId ? (bOptions.length ? 'Select a run on the same dataset' : 'No other runs on this dataset') : 'Select run A first'}
            disabled={!aId || bOptions.length === 0}
            options={bOptions.map((r) => ({ value: String(r.id), label: `${r.prompt_name} v${r.version_no} — ${r.model}` }))}
          />
        </div>
      )}

      {compareError && <ErrorState message="Couldn't compare runs" detail={compareError} />}

      {loading && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
          <Skeleton className="h-48" />
        </div>
      )}

      {result && !loading && (
        <>
          <div className="grid grid-cols-5 gap-3">
            <MetricTile label="Pass rate delta" value={result.deltas.pass_rate != null ? (result.deltas.pass_rate * 100).toFixed(1) + ' pp' : '—'} sub={'A ' + (result.a.stats.pass_rate != null ? (result.a.stats.pass_rate * 100).toFixed(1) + '%' : '—') + ' · B ' + (result.b.stats.pass_rate != null ? (result.b.stats.pass_rate * 100).toFixed(1) + '%' : '—')} />
            <MetricTile
              label="Avg score delta"
              value={
                <span style={{ color: deltaColor(result.deltas.avg_score) }}>{fmtScore(result.deltas.avg_score)}</span>
              }
              sub={`A ${result.a.stats.avg_score?.toFixed(1) ?? '—'} · B ${result.b.stats.avg_score?.toFixed(1) ?? '—'}`}
            />
            <MetricTile
              label="Cost delta"
              value={result.a.stats.cost_complete === false || result.b.stats.cost_complete === false ? 'Unknown / incomplete' : <span style={{ color: result.deltas.total_cost > 0 ? 'var(--score-low)' : 'var(--score-high)' }}>{fmtCost(result.deltas.total_cost)}</span>}
              sub={'A ' + (result.a.stats.cost_complete === false ? 'unknown' : '$' + result.a.stats.total_cost.toFixed(4)) + ' · B ' + (result.b.stats.cost_complete === false ? 'unknown' : '$' + result.b.stats.total_cost.toFixed(4))}
            />
            <MetricTile label="Wins A" value={<span style={{ color: 'var(--win)' }}>{result.wins.a}</span>} />
            <MetricTile label="Wins B / Ties" value={<span>{result.wins.b} <span className="text-[var(--text-tertiary)]">/ {result.wins.tie}</span></span>} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
              <span className="text-[13px] font-medium text-[var(--text-primary)]">Per-grader delta</span>
              <DeltaList items={graderDeltas} aLabel={aLabel} bLabel={bLabel} />
            </div>
            <div className="flex flex-col gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
              <span className="text-[13px] font-medium text-[var(--text-primary)]">Per-category delta</span>
              <DeltaList items={categoryDeltas} aLabel={aLabel} bLabel={bLabel} />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-3 text-[12px] text-[var(--text-tertiary)]">
              <span>
                <span className="font-medium text-[var(--text-primary)]">A</span> = {aLabel}
              </span>
              <span>
                <span className="font-medium text-[var(--text-primary)]">B</span> = {bLabel}
              </span>
            </div>
            <Table
              columns={columns}
              rows={result.cases}
              rowKey={(r) => r.test_case.id}
              onRowClick={(r) => setDrawerRow(r)}
              initialSort={{ key: 'delta', direction: 'asc' }}
            />
          </div>
        </>
      )}

      <CompareCaseDrawer row={drawerRow} onClose={() => setDrawerRow(null)} aLabel={aLabel} bLabel={bLabel} />
    </div>
  )
}
