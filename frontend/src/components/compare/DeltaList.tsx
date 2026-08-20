import { cn } from '@/lib/cn'

export interface DeltaItem {
  label: string
  a: number | null
  b: number | null
  delta: number
}

/** Per-grader / per-category delta rows. Delta is always a - b, labelled explicitly. */
export function DeltaList({ items, aLabel, bLabel }: { items: DeltaItem[]; aLabel: string; bLabel: string }) {
  if (items.length === 0) {
    return <span className="text-[12px] text-[var(--text-tertiary)]">No overlapping data between the two runs.</span>
  }
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3 px-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">
        <span className="flex-1">Name</span>
        <span className="w-16 text-right" title={aLabel}>
          A
        </span>
        <span className="w-16 text-right" title={bLabel}>
          B
        </span>
        <span className="w-20 text-right">Δ (A − B)</span>
      </div>
      {items.map((item) => {
        const color = item.delta > 0.05 ? 'var(--win)' : item.delta < -0.05 ? 'var(--loss)' : 'var(--tie)'
        return (
          <div key={item.label} className="flex items-center gap-3 rounded-md px-1 py-1 text-[12.5px] hover:bg-[var(--surface-2)]">
            <span className="flex-1 truncate text-[var(--text-primary)]" title={item.label}>
              {item.label}
            </span>
            <span className="w-16 text-right font-mono tabular-nums text-[var(--text-secondary)]">{item.a != null ? item.a.toFixed(1) : '—'}</span>
            <span className="w-16 text-right font-mono tabular-nums text-[var(--text-secondary)]">{item.b != null ? item.b.toFixed(1) : '—'}</span>
            <span className={cn('w-20 text-right font-mono tabular-nums font-semibold')} style={{ color }}>
              {item.delta > 0 ? '+' : ''}
              {item.delta.toFixed(1)}
            </span>
          </div>
        )
      })}
    </div>
  )
}
