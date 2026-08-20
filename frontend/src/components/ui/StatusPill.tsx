import { cn } from '@/lib/cn'
import type { RunStatus } from '@/lib/types'

const LABEL: Record<RunStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

const colorVar: Record<RunStatus, string> = {
  pending: 'var(--status-pending)',
  running: 'var(--status-running)',
  completed: 'var(--status-completed)',
  failed: 'var(--status-failed)',
  cancelled: 'var(--status-cancelled)',
}
const bgVar: Record<RunStatus, string> = {
  pending: 'var(--status-pending-bg)',
  running: 'var(--status-running-bg)',
  completed: 'var(--status-completed-bg)',
  failed: 'var(--status-failed-bg)',
  cancelled: 'var(--status-cancelled-bg)',
}

export function StatusPill({ status, className }: { status: RunStatus; className?: string }) {
  return (
    <span
      className={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-medium', className)}
      style={{ color: colorVar[status], backgroundColor: bgVar[status] }}
    >
      <span
        className={cn('h-1.5 w-1.5 rounded-full', status === 'running' && 'animate-pulse')}
        style={{ backgroundColor: colorVar[status] }}
      />
      {LABEL[status]}
    </span>
  )
}

const OUTCOME_LABEL = { a: 'Win', b: 'Loss', tie: 'Tie' } as const

/** For A/B compare rows, seen from variant A's perspective. */
export function OutcomePill({ outcome, className }: { outcome: 'a' | 'b' | 'tie'; className?: string }) {
  const color = outcome === 'a' ? 'var(--win)' : outcome === 'b' ? 'var(--loss)' : 'var(--tie)'
  const bg = outcome === 'a' ? 'var(--win-bg)' : outcome === 'b' ? 'var(--loss-bg)' : 'var(--tie-bg)'
  return (
    <span
      className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide', className)}
      style={{ color, backgroundColor: bg }}
    >
      {OUTCOME_LABEL[outcome]}
    </span>
  )
}
