import { cn } from '@/lib/cn'

function quality(score: number): 'low' | 'mid' | 'high' {
  if (score < 4) return 'low'
  if (score < 7.5) return 'mid'
  return 'high'
}

const colorVar: Record<string, string> = {
  low: 'var(--score-low)',
  mid: 'var(--score-mid)',
  high: 'var(--score-high)',
}
const bgVar: Record<string, string> = {
  low: 'var(--score-low-bg)',
  mid: 'var(--score-mid-bg)',
  high: 'var(--score-high-bg)',
}

/** Score is always shown as a number — colour is never the only signal. */
export function ScoreBadge({
  score,
  max = 10,
  size = 'md',
  className,
}: {
  score: number | null
  max?: number
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  if (score == null) {
    return (
      <span className={cn('font-mono tabular-nums text-[var(--text-tertiary)]', className)}>—</span>
    )
  }
  const q = quality(score)
  const sizeClasses = size === 'sm' ? 'text-[12px] px-1.5 py-0.5' : size === 'lg' ? 'text-base px-2.5 py-1' : 'text-[13px] px-2 py-0.5'
  return (
    <span
      className={cn('inline-flex items-center rounded-md font-mono font-semibold tabular-nums', sizeClasses, className)}
      style={{ color: colorVar[q], backgroundColor: bgVar[q] }}
    >
      {score.toFixed(1)}
      <span className="ml-0.5 opacity-60">/{max}</span>
    </span>
  )
}
