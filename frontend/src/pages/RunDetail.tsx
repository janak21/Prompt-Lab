import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Button,
  CategoryBars,
  DistributionChart,
  ErrorState,
  MetricTile,
  ProgressBar,
  ScoreBadge,
  Select,
  Skeleton,
  StatusPill,
  Table,
  TableSkeleton,
  toast,
} from '@/components/ui'
import type { Column } from '@/components/ui'
import { CategoryBadge } from '@/components/datasets/CategoryBadge'
import { categoryLabel } from '@/components/datasets/category'
import { RunCaseDrawer } from '@/components/runs/RunCaseDrawer'
import { api, ApiError } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { subscribeToRunEvents } from '@/lib/sse'
import type { Grade, RunCase, RunSummary, TestCase } from '@/lib/types'

function placeholderTestCase(id: number, datasetId: number): TestCase {
  return { id, dataset_id: datasetId, inputs: {}, solution_criteria: null, category: null, expected_format: null, created_at: '' }
}

function emptyRow(idx: number, datasetId: number): RunCase {
  return {
    id: 0,
    run_id: 0,
    test_case_id: 0,
    idx,
    rendered_prompt: null,
    output: null,
    latency_ms: null,
    input_tokens: null,
    output_tokens: null,
    cost: null,
    final_score: null,
    status: 'pending',
    error: null,
    grades: [],
    test_case: placeholderTestCase(0, datasetId),
  }
}

function fmtCost(cost: number | null) {
  if (cost == null) return '—'
  return `$${cost.toFixed(4)}`
}
const fmtDate = formatDateTime

interface LocalStats {
  avg_score: number | null
  distribution: number[]
  by_grader: Record<string, { avg_score: number; weight: number }>
  by_category: Record<string, { avg_score: number; count: number }>
}

function computeLocalStats(rows: RunCase[]): LocalStats {
  const completed = rows.filter((r) => r.status === 'completed')
  const scores = completed.map((r) => r.final_score).filter((s): s is number => s != null)
  const avg_score = scores.length ? Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 100) / 100 : null
  const distribution = new Array(10).fill(0)
  for (const s of scores) distribution[Math.min(9, Math.max(0, Math.floor(s)))] += 1

  const byGrader = new Map<string, { sum: number; weight: number; n: number }>()
  for (const r of completed) {
    for (const g of r.grades as Grade[]) {
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
    const cat = r.test_case.category ?? 'standard'
    const e = byCategory.get(cat) ?? { sum: 0, n: 0 }
    if (r.final_score != null) e.sum += r.final_score
    e.n += 1
    byCategory.set(cat, e)
  }
  const by_category: LocalStats['by_category'] = {}
  for (const [cat, v] of byCategory) by_category[cat] = { avg_score: v.n ? Math.round((v.sum / v.n) * 100) / 100 : 0, count: v.n }

  return { avg_score, distribution, by_grader, by_category }
}

export function RunDetailPage() {
  const { id } = useParams<{ id: string }>()
  const runId = Number(id)
  const navigate = useNavigate()

  const [run, setRun] = useState<RunSummary | null>(null)
  const [initError, setInitError] = useState<string | null>(null)
  const [rows, setRows] = useState<RunCase[] | null>(null)
  const [progress, setProgress] = useState({ completed: 0, failed: 0, total: 0, avg_score_so_far: null as number | null })
  const [cancelling, setCancelling] = useState(false)
  const [drawerIdx, setDrawerIdx] = useState<number | null>(null)
  const [loadingDrawerDetail, setLoadingDrawerDetail] = useState(false)
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')

  const rowsRef = useRef<RunCase[] | null>(null)
  rowsRef.current = rows

  const patchRow = (idx: number, patch: Partial<RunCase>) => {
    setRows((cur) => {
      if (!cur) return cur
      const next = [...cur]
      if (!next[idx]) return cur
      next[idx] = { ...next[idx], ...patch }
      return next
    })
  }

  const refreshFull = (datasetId: number) => {
    api
      .getRun(runId)
      .then((res) => {
        setRun(res.run)
        setRows((cur) => {
          const total = res.run.total || cur?.length || res.cases.length
          const base = cur && cur.length === total ? [...cur] : Array.from({ length: total }, (_, i) => emptyRow(i, datasetId))
          for (const c of res.cases) {
            if (c.idx < base.length) base[c.idx] = c
          }
          return base
        })
      })
      .catch(() => {
        /* best-effort refresh; live state already reflects what we know */
      })
  }

  useEffect(() => {
    let cancelled = false
    setRun(null)
    setRows(null)
    setInitError(null)
    setDrawerIdx(null)

    api
      .getRun(runId)
      .then(async (res) => {
        if (cancelled) return
        setRun(res.run)
        setProgress({
          completed: res.run.completed,
          failed: res.run.failed,
          total: res.run.total,
          avg_score_so_far: res.run.avg_score,
        })

        let datasetCases: TestCase[] = []
        try {
          const ds = await api.getDataset(res.run.dataset_id)
          datasetCases = ds.cases
        } catch {
          // dataset may have been deleted — fall back to placeholders/embedded test_case data
        }
        if (cancelled) return

        const total = res.run.total || res.cases.length
        const initial = Array.from({ length: total }, (_, i) => {
          const guessed = datasetCases[i]
          return guessed ? { ...emptyRow(i, res.run.dataset_id), test_case_id: guessed.id, test_case: guessed } : emptyRow(i, res.run.dataset_id)
        })
        for (const c of res.cases) {
          if (c.idx < initial.length) initial[c.idx] = c
        }
        setRows(initial)

        const byId = new Map(datasetCases.map((c) => [c.id, c]))

        const stream = subscribeToRunEvents(runId, {
          run_started: (data) => {
            setProgress((p) => ({ ...p, total: data.total }))
            setRun((r) => (r ? { ...r, status: 'running', total: data.total } : r))
          },
          case_started: (data) => {
            const known = byId.get(data.test_case_id)
            patchRow(data.idx, {
              id: data.run_case_id,
              test_case_id: data.test_case_id,
              status: 'running',
              test_case: known ?? rowsRef.current?.[data.idx]?.test_case ?? placeholderTestCase(data.test_case_id, res.run.dataset_id),
            })
          },
          case_completed: (data) => {
            const known = byId.get(data.test_case_id)
            patchRow(data.idx, {
              id: data.run_case_id,
              test_case_id: data.test_case_id,
              status: data.status,
              final_score: data.final_score,
              latency_ms: data.latency_ms,
              cost: data.cost,
              output: data.output_preview,
              grades: data.grades,
              test_case: known ?? rowsRef.current?.[data.idx]?.test_case ?? placeholderTestCase(data.test_case_id, res.run.dataset_id),
            })
          },
          case_failed: (data) => {
            patchRow(data.idx, { id: data.run_case_id, status: 'failed', error: data.error })
          },
          progress: (data) => {
            setProgress({ completed: data.completed, failed: data.failed, total: data.total, avg_score_so_far: data.avg_score_so_far })
          },
          run_completed: (data) => {
            setRun((r) => (r ? { ...r, status: 'completed', avg_score: data.avg_score, total_cost: data.total_cost, completed: data.completed, failed: data.failed, finished_at: new Date().toISOString() } : r))
            refreshFull(res.run.dataset_id)
          },
          run_failed: (data) => {
            setRun((r) => (r ? { ...r, status: 'failed', error: data.error } : r))
            refreshFull(res.run.dataset_id)
          },
          cancelled: () => {
            setRun((r) => (r ? { ...r, status: 'cancelled' } : r))
            refreshFull(res.run.dataset_id)
          },
          onError: () => {
            // sse.ts handles reconnection; nothing to surface here unless it gives up
          },
        })

        return () => stream.close()
      })
      .catch((e: unknown) => {
        if (!cancelled) setInitError(e instanceof ApiError ? e.message : 'Failed to load run.')
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  const isLive = run ? run.status === 'pending' || run.status === 'running' : false
  const localStats = useMemo(() => computeLocalStats(rows ?? []), [rows])

  const categories = useMemo(() => {
    const s = new Set<string>()
    for (const r of rows ?? []) s.add(r.test_case.category ?? 'standard')
    return [...s]
  }, [rows])

  const filteredRows = useMemo(() => {
    return (rows ?? []).filter((r) => {
      if (statusFilter !== 'all' && r.status !== statusFilter) return false
      if (categoryFilter !== 'all' && (r.test_case.category ?? 'standard') !== categoryFilter) return false
      return true
    })
  }, [rows, statusFilter, categoryFilter])

  const drawerRow = drawerIdx != null ? (rows ?? []).find((r) => r.idx === drawerIdx) ?? null : null

  const openDrawer = (row: RunCase) => {
    setDrawerIdx(row.idx)
    if (!row.rendered_prompt && row.status !== 'pending' && row.status !== 'running' && run) {
      setLoadingDrawerDetail(true)
      api
        .getRun(runId)
        .then((res) => {
          const full = res.cases.find((c) => c.idx === row.idx)
          if (full) patchRow(row.idx, full)
        })
        .finally(() => setLoadingDrawerDetail(false))
    }
  }

  const cancel = async () => {
    if (!run) return
    setCancelling(true)
    try {
      await api.cancelRun(run.id)
      toast('Cancelling run…')
    } catch (e) {
      toast.error('Couldn’t cancel', e instanceof ApiError ? e.message : 'Unknown error')
    } finally {
      setCancelling(false)
    }
  }

  const columns: Column<RunCase>[] = [
    { key: 'idx', header: '#', width: '44px', mono: true, sortValue: (r) => r.idx, render: (r) => r.idx + 1 },
    {
      key: 'category',
      header: 'Category',
      sortValue: (r) => categoryLabel(r.test_case.category),
      render: (r) => <CategoryBadge category={r.test_case.category} />,
    },
    {
      key: 'status',
      header: 'Status',
      sortValue: (r) => r.status,
      render: (r) => <StatusPill status={r.status} />,
    },
    {
      key: 'score',
      header: 'Score',
      align: 'right',
      sortValue: (r) => r.final_score ?? -1,
      render: (r) => <ScoreBadge score={r.final_score} size="sm" />,
    },
    {
      key: 'latency',
      header: 'Latency',
      align: 'right',
      mono: true,
      sortValue: (r) => r.latency_ms ?? -1,
      render: (r) => (r.latency_ms != null ? `${r.latency_ms}ms` : '—'),
    },
    {
      key: 'cost',
      header: 'Cost',
      align: 'right',
      mono: true,
      sortValue: (r) => r.cost ?? -1,
      render: (r) => fmtCost(r.cost),
    },
    {
      key: 'output',
      header: 'Output preview',
      render: (r) => (
        <span className="line-clamp-1 max-w-[360px] text-[var(--text-secondary)]">
          {r.status === 'failed' ? r.error ?? 'Failed' : r.output || (r.status === 'pending' ? '—' : '')}
        </span>
      ),
    },
  ]

  if (initError) return <ErrorState className="m-6" message="Couldn't load run" detail={initError} onRetry={() => navigate(0)} />

  if (!run || !rows) {
    return (
      <div className="flex flex-col gap-5 p-6">
        <Skeleton className="h-6 w-72" />
        <div className="grid grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
        <TableSkeleton rows={8} cols={7} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5 p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate('/runs')}
              className="text-[13px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            >
              Runs
            </button>
            <span className="text-[13px] text-[var(--text-tertiary)]">/</span>
            <h1 className="text-[17px] font-semibold text-[var(--text-primary)]">
              {run.prompt_name} <span className="text-[var(--text-tertiary)]">v{run.version_no}</span>
            </h1>
            <StatusPill status={run.status} />
          </div>
          <p className="text-[13px] text-[var(--text-secondary)]">
            {run.dataset_name} · <span className="font-mono">{run.model}</span> · judge{' '}
            <span className="font-mono">{run.judge_model}</span> · started {fmtDate(run.started_at)}
          </p>
        </div>
        {isLive && (
          <Button variant="danger" loading={cancelling} onClick={cancel}>
            Cancel run
          </Button>
        )}
      </div>

      {run.status === 'failed' && run.error && <ErrorState message="Run failed" detail={run.error} />}

      {isLive && (
        <div className="flex flex-col gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-medium text-[var(--text-primary)]">
              {progress.completed + progress.failed} / {progress.total || '…'} cases
            </span>
            <span className="text-[12px] text-[var(--text-tertiary)]">Running average updates live</span>
          </div>
          <ProgressBar value={progress.completed + progress.failed} max={progress.total || 1} />
          <div className="grid grid-cols-4 gap-3">
            <MetricTile label="Completed" value={progress.completed} />
            <MetricTile label="Failed" value={progress.failed} />
            <MetricTile label="Avg score so far" value={progress.avg_score_so_far != null ? progress.avg_score_so_far.toFixed(1) : '—'} />
            <MetricTile label="Total" value={progress.total || '—'} />
          </div>
        </div>
      )}

      <div className="grid grid-cols-4 gap-3">
        <MetricTile label="Average score" value={localStats.avg_score != null ? <ScoreBadge score={localStats.avg_score} size="lg" /> : '—'} />
        <MetricTile label="Completed" value={run.completed || progress.completed} />
        <MetricTile label="Failed" value={run.failed || progress.failed} />
        <MetricTile label="Total cost" value={fmtCost(run.total_cost ?? null)} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
          <span className="text-[13px] font-medium text-[var(--text-primary)]">Score distribution</span>
          {localStats.distribution.every((n) => n === 0) ? (
            <span className="py-6 text-center text-[12px] text-[var(--text-tertiary)]">No scored cases yet.</span>
          ) : (
            <DistributionChart distribution={localStats.distribution} />
          )}
        </div>
        <div className="flex flex-col gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
          <span className="text-[13px] font-medium text-[var(--text-primary)]">Per-grader average</span>
          {Object.keys(localStats.by_grader).length === 0 ? (
            <span className="py-6 text-center text-[12px] text-[var(--text-tertiary)]">No grader data yet.</span>
          ) : (
            <CategoryBars items={Object.entries(localStats.by_grader).map(([label, v]) => ({ label, value: v.avg_score }))} />
          )}
        </div>
      </div>

      {/* Per-category is the point of the product — full width, more prominence than grader/distribution. */}
      <div className="flex flex-col gap-3 rounded-lg border border-[var(--accent-9)]/30 bg-[var(--surface-1)] p-5">
        <div className="flex flex-col gap-0.5">
          <span className="text-[15px] font-semibold text-[var(--text-primary)]">Per-category performance</span>
          <span className="text-[12.5px] text-[var(--text-tertiary)]">Which kind of input does this prompt fail on?</span>
        </div>
        {Object.keys(localStats.by_category).length === 0 ? (
          <span className="py-6 text-center text-[12px] text-[var(--text-tertiary)]">No category data yet.</span>
        ) : (
          <CategoryBars
            items={Object.entries(localStats.by_category)
              .sort((a, b) => a[1].avg_score - b[1].avg_score)
              .map(([cat, v]) => ({ label: categoryLabel(cat), value: v.avg_score, count: v.count }))}
          />
        )}
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-[13px] font-medium text-[var(--text-primary)]">Cases</span>
          <div className="flex items-center gap-2">
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              options={[
                { value: 'all', label: 'All statuses' },
                { value: 'pending', label: 'Pending' },
                { value: 'running', label: 'Running' },
                { value: 'completed', label: 'Completed' },
                { value: 'failed', label: 'Failed' },
              ]}
            />
            <Select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              options={[{ value: 'all', label: 'All categories' }, ...categories.map((c) => ({ value: c, label: categoryLabel(c) }))]}
            />
          </div>
        </div>
        <Table
          columns={columns}
          rows={filteredRows}
          rowKey={(r) => r.idx}
          onRowClick={openDrawer}
          initialSort={{ key: 'idx', direction: 'asc' }}
        />
      </div>

      <RunCaseDrawer row={drawerRow} onClose={() => setDrawerIdx(null)} loadingDetail={loadingDrawerDetail} />
    </div>
  )
}
