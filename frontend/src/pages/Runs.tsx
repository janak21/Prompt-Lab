import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { EmptyState, ErrorState, ScoreBadge, StatusPill, Table, TableSkeleton } from '@/components/ui'
import type { Column } from '@/components/ui'
import { LaunchRunPanel } from '@/components/runs/LaunchRunPanel'
import { api, ApiError } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import type { Dataset, ModelInfo, Prompt, RunSummary } from '@/lib/types'

function fmtCost(cost: number | null) {
  if (cost == null) return '—'
  return `$${cost.toFixed(4)}`
}
const fmtDate = formatDateTime

export function RunsPage() {
  const navigate = useNavigate()
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [prompts, setPrompts] = useState<Prompt[] | null>(null)
  const [datasets, setDatasets] = useState<Dataset[] | null>(null)
  const [models, setModels] = useState<{ items: ModelInfo[]; defaultModel: string; defaultJudgeModel: string } | null>(null)

  const load = () => {
    setError(null)
    setRuns(null)
    api
      .listRuns({ limit: 100 })
      .then(setRuns)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : 'Failed to load runs.'))
  }

  useEffect(load, [])
  useEffect(() => {
    api.listPrompts().then(setPrompts)
    api.listDatasets().then(setDatasets)
    api.getModels().then((r) => setModels({ items: r.models, defaultModel: r.default_model, defaultJudgeModel: r.default_judge_model }))
  }, [])

  const columns: Column<RunSummary>[] = [
    {
      key: 'prompt',
      header: 'Prompt',
      sortValue: (r) => r.prompt_name,
      render: (r) => (
        <span className="font-medium text-[var(--text-primary)]">
          {r.prompt_name} <span className="font-mono text-[var(--text-tertiary)]">v{r.version_no}</span>
        </span>
      ),
    },
    { key: 'dataset', header: 'Dataset', sortValue: (r) => r.dataset_name, render: (r) => r.dataset_name },
    { key: 'model', header: 'Model', mono: true, sortValue: (r) => r.model, render: (r) => r.model },
    { key: 'status', header: 'Status', sortValue: (r) => r.status, render: (r) => <StatusPill status={r.status} /> },
    {
      key: 'avg_score',
      header: 'Avg score',
      align: 'right',
      sortValue: (r) => r.avg_score ?? -1,
      render: (r) => <ScoreBadge score={r.avg_score} size="sm" />,
    },
    {
      key: 'progress',
      header: 'Cases',
      align: 'right',
      mono: true,
      sortValue: (r) => r.total,
      render: (r) => `${r.completed}/${r.total}${r.failed ? ` (${r.failed} failed)` : ''}`,
    },
    { key: 'cost', header: 'Cost', align: 'right', mono: true, sortValue: (r) => r.total_cost ?? -1, render: (r) => fmtCost(r.total_cost) },
    { key: 'when', header: 'When', align: 'right', mono: true, sortValue: (r) => r.created_at, render: (r) => fmtDate(r.created_at) },
  ]

  return (
    <div className="flex flex-col gap-5 p-6">
      <div>
        <h1 className="text-[17px] font-semibold text-[var(--text-primary)]">Runs</h1>
        <p className="text-[13px] text-[var(--text-secondary)]">Evaluate a prompt version against a dataset.</p>
      </div>

      <div className="flex items-start gap-5">
        <div className="min-w-0 flex-1">
          {error ? (
            <ErrorState message="Couldn't load runs" detail={error} onRetry={load} />
          ) : runs === null ? (
            <TableSkeleton rows={6} cols={8} />
          ) : runs.length === 0 ? (
            <EmptyState
              title="No runs yet"
              description="Launch a run from the panel to evaluate a prompt version against a dataset."
              action={<span className="text-[12px] text-[var(--text-tertiary)]">Use the launch panel →</span>}
            />
          ) : (
            <Table
              columns={columns}
              rows={runs}
              rowKey={(r) => r.id}
              onRowClick={(r) => navigate(`/runs/${r.id}`)}
              initialSort={{ key: 'when', direction: 'desc' }}
            />
          )}
        </div>

        {prompts && datasets && models ? (
          <LaunchRunPanel
            prompts={prompts}
            datasets={datasets}
            models={models.items}
            defaultModel={models.defaultModel}
            defaultJudgeModel={models.defaultJudgeModel}
            onLaunched={() => load()}
          />
        ) : (
          <div className="h-96 w-[360px] shrink-0 animate-pulse rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]" />
        )}
      </div>
    </div>
  )
}
