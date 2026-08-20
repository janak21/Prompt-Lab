import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export function MetricTile({
  label,
  value,
  sub,
  trend,
  mono = true,
  className,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  trend?: { direction: 'up' | 'down' | 'flat'; label: string; positive?: boolean }
  mono?: boolean
  className?: string
}) {
  const trendColor =
    trend &&
    (trend.direction === 'flat'
      ? 'var(--text-tertiary)'
      : trend.positive === false
        ? 'var(--score-low)'
        : 'var(--score-high)')
  return (
    <div className={cn('flex flex-col gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3.5 py-3', className)}>
      <span className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">{label}</span>
      <span className={cn('text-2xl font-semibold tabular-nums text-[var(--text-primary)]', mono && 'font-mono')}>
        {value}
      </span>
      {(sub || trend) && (
        <div className="flex items-center gap-1.5 text-[12px] text-[var(--text-tertiary)]">
          {trend && (
            <span className="inline-flex items-center gap-0.5 font-medium" style={{ color: trendColor }}>
              {trend.direction === 'up' ? '↑' : trend.direction === 'down' ? '↓' : '→'} {trend.label}
            </span>
          )}
          {sub}
        </div>
      )}
    </div>
  )
}
