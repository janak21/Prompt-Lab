import { CodeBlock, Drawer, OutcomePill, ScoreBadge } from '@/components/ui'
import { CategoryBadge } from '@/components/datasets/CategoryBadge'
import type { RunCase, TestCase } from '@/lib/types'

export interface CompareCaseRow {
  test_case: TestCase
  a: RunCase | null
  b: RunCase | null
  winner: 'a' | 'b' | 'tie'
  delta: number
}

function Side({ label, run }: { label: string; run: RunCase | null }) {
  if (!run) {
    return (
      <div className="flex flex-1 flex-col gap-2">
        <span className="text-[13px] font-medium text-[var(--text-secondary)]">{label}</span>
        <span className="text-[12px] text-[var(--text-tertiary)]">No case recorded for this run.</span>
      </div>
    )
  }
  return (
    <div className="flex flex-1 flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-medium text-[var(--text-secondary)]">{label}</span>
        <ScoreBadge score={run.final_score} size="sm" />
      </div>
      {run.status === 'failed' ? (
        <div className="rounded-md border border-[var(--danger-9)]/40 bg-[var(--score-low-bg)] px-2.5 py-2 text-[12px] text-[var(--score-low)]">
          {run.error ?? 'Failed'}
        </div>
      ) : (
        <CodeBlock code={run.output ?? '—'} language="text" collapseAfterLines={16} />
      )}
      <span className="text-[11px] text-[var(--text-tertiary)]">
        {run.latency_ms != null ? `${run.latency_ms}ms` : '—'} · {run.cost != null ? `$${run.cost.toFixed(4)}` : '—'}
      </span>
    </div>
  )
}

export function CompareCaseDrawer({
  row,
  onClose,
  aLabel,
  bLabel,
}: {
  row: CompareCaseRow | null
  onClose: () => void
  aLabel: string
  bLabel: string
}) {
  return (
    <Drawer open={!!row} onClose={onClose} title="Case comparison" width="720px">
      {row && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <CategoryBadge category={row.test_case.category} />
            <OutcomePill outcome={row.winner} />
            <span className="font-mono text-[12px] text-[var(--text-tertiary)]">
              Δ {row.delta > 0 ? '+' : ''}
              {row.delta.toFixed(1)} (A − B)
            </span>
          </div>
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3">
            {Object.entries(row.test_case.inputs).map(([k, v]) => (
              <div key={k} className="flex items-start gap-2 text-[12.5px]">
                <span className="w-28 shrink-0 truncate font-mono text-[var(--text-tertiary)]">{k}</span>
                <span className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-[var(--text-primary)]">{v}</span>
              </div>
            ))}
          </div>
          <div className="flex gap-4">
            <Side label={aLabel} run={row.a} />
            <div className="w-px shrink-0 bg-[var(--border-subtle)]" />
            <Side label={bLabel} run={row.b} />
          </div>
        </div>
      )}
    </Drawer>
  )
}
