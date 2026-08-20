import { cn } from '@/lib/cn'

/** Score-quality colour for a 0-10 bucket midpoint. */
function bucketColor(bucketIndex: number): string {
  const mid = bucketIndex + 0.5
  if (mid < 4) return 'var(--score-low)'
  if (mid < 7.5) return 'var(--score-mid)'
  return 'var(--score-high)'
}

/** Score distribution histogram — 10 buckets, 0-1 .. 9-10. */
export function DistributionChart({ distribution, className }: { distribution: number[]; className?: string }) {
  const max = Math.max(1, ...distribution)
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {/* items-end on the row leaves each column's own height indefinite (content-sized),
          so a percentage height on the bar resolves to auto -> 0. Stretch the columns to the
          row's definite h-28 instead, then push each bar to the bottom with justify-end. */}
      <div className="flex h-28 items-stretch gap-1">
        {distribution.map((count, i) => (
          <div key={i} className="group relative flex h-full flex-1 flex-col items-center justify-end gap-1">
            <span className="text-[10px] tabular-nums text-[var(--text-tertiary)] opacity-0 transition-opacity group-hover:opacity-100">
              {count}
            </span>
            <div
              className="w-full shrink-0 rounded-t-[3px] transition-[height] duration-200 ease-[var(--ease-out)]"
              style={{
                height: `${Math.max(2, (count / max) * 100)}%`,
                backgroundColor: bucketColor(i),
                opacity: count === 0 ? 0.25 : 0.85,
              }}
            />
          </div>
        ))}
      </div>
      <div className="flex gap-1 text-[10px] tabular-nums text-[var(--text-tertiary)]">
        {distribution.map((_, i) => (
          <span key={i} className="flex-1 text-center">
            {i}
          </span>
        ))}
      </div>
    </div>
  )
}

export interface CategoryBar {
  label: string
  value: number
  count?: number
  max?: number
}

/** Horizontal per-category / per-grader bar chart. */
export function CategoryBars({ items, max = 10, className }: { items: CategoryBar[]; max?: number; className?: string }) {
  return (
    <div className={cn('flex flex-col gap-2.5', className)}>
      {items.map((item) => {
        const pct = Math.max(0, Math.min(100, (item.value / (item.max ?? max)) * 100))
        const color = item.value < 4 ? 'var(--score-low)' : item.value < 7.5 ? 'var(--score-mid)' : 'var(--score-high)'
        return (
          <div key={item.label} className="flex items-center gap-3">
            <span className="w-36 shrink-0 truncate text-[12.5px] text-[var(--text-secondary)]" title={item.label}>
              {item.label}
            </span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-3)]">
              <div
                className="h-full rounded-full transition-[width] duration-300 ease-[var(--ease-out)]"
                style={{ width: `${pct}%`, backgroundColor: color }}
              />
            </div>
            <span className="w-14 shrink-0 text-right font-mono text-[12.5px] tabular-nums text-[var(--text-primary)]">
              {item.value.toFixed(1)}
            </span>
            {item.count != null && (
              <span className="w-10 shrink-0 text-right font-mono text-[11px] tabular-nums text-[var(--text-tertiary)]">
                n={item.count}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
