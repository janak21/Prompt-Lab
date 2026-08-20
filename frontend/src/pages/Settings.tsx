import { useEffect, useState } from 'react'
import { Badge, ErrorState, Skeleton, Table } from '@/components/ui'
import type { Column } from '@/components/ui'
import { DEFAULT_CONCURRENCY } from '@/components/runs/LaunchRunPanel'
import { api, ApiError } from '@/lib/api'
import type { HealthResponse, ModelInfo, ModelsResponse } from '@/lib/types'

export function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [models, setModels] = useState<ModelsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setError(null)
    setHealth(null)
    setModels(null)
    Promise.all([api.getHealth(), api.getModels()])
      .then(([h, m]) => {
        setHealth(h)
        setModels(m)
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : 'Failed to load settings.'))
  }

  useEffect(load, [])

  const columns: Column<ModelInfo>[] = models
    ? [
        {
          key: 'label',
          header: 'Model',
          render: (m) => (
            <span className="flex items-center gap-1.5 font-medium text-[var(--text-primary)]">
              {m.label}
              {m.id === models.default_model && <Badge variant="accent">default</Badge>}
              {m.id === models.default_judge_model && <Badge variant="neutral">default judge</Badge>}
            </span>
          ),
        },
        { key: 'id', header: 'ID', mono: true, render: (m) => m.id },
        {
          key: 'input',
          header: 'Input $ / Mtok',
          align: 'right',
          mono: true,
          sortValue: (m) => m.input_price_per_mtok,
          render: (m) => `$${m.input_price_per_mtok.toFixed(2)}`,
        },
        {
          key: 'output',
          header: 'Output $ / Mtok',
          align: 'right',
          mono: true,
          sortValue: (m) => m.output_price_per_mtok,
          render: (m) => `$${m.output_price_per_mtok.toFixed(2)}`,
        },
      ]
    : []

  if (error) return <ErrorState className="m-6" message="Couldn't load settings" detail={error} onRetry={load} />

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <h1 className="text-[17px] font-semibold text-[var(--text-primary)]">Settings</h1>
        <p className="text-[13px] text-[var(--text-secondary)]">API access, defaults, and pricing.</p>
      </div>

      <div className="flex flex-col gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
        <span className="text-[13px] font-medium text-[var(--text-primary)]">API key</span>
        {!health ? (
          <Skeleton className="h-5 w-40" />
        ) : health.api_key_present ? (
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: 'var(--score-high)' }} />
            <span className="text-[13px] text-[var(--text-secondary)]">Configured on the server.</span>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: 'var(--score-low)' }} />
              <span className="text-[13px] text-[var(--score-low)]">No API key configured — runs will fail to start.</span>
            </div>
            <p className="text-[12.5px] text-[var(--text-tertiary)]">
              Set <code className="font-mono">ANTHROPIC_API_KEY</code> in the server's environment and restart it. For
              security the key is never sent to or displayed in this UI — only its presence is reported.
            </p>
          </div>
        )}
        {health && (
          <p className="pt-1 text-[11px] text-[var(--text-tertiary)]">
            db: <span className="font-mono">{health.db_path}</span> · version <span className="font-mono">{health.version}</span>
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
        <span className="text-[13px] font-medium text-[var(--text-primary)]">Run defaults</span>
        {!models ? (
          <div className="grid grid-cols-3 gap-3">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3 pt-1">
            <div className="flex flex-col gap-0.5">
              <span className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Default model</span>
              <span className="font-mono text-[13px] text-[var(--text-primary)]">{models.default_model}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Default judge model</span>
              <span className="font-mono text-[13px] text-[var(--text-primary)]">{models.default_judge_model}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Default concurrency</span>
              <span className="font-mono text-[13px] text-[var(--text-primary)]">{DEFAULT_CONCURRENCY}</span>
            </div>
          </div>
        )}
        <p className="pt-1 text-[11px] text-[var(--text-tertiary)]">
          These prefill the run launch panel; every run can override them individually. There is no server-side settings
          endpoint to persist changes to these defaults.
        </p>
      </div>

      <div className="flex flex-col gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
        <span className="text-[13px] font-medium text-[var(--text-primary)]">Model pricing</span>
        {!models ? <Skeleton className="h-40" /> : <Table columns={columns} rows={models.models} rowKey={(m) => m.id} />}
      </div>
    </div>
  )
}
