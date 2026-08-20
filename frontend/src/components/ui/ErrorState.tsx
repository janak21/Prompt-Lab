import { cn } from '@/lib/cn'
import { Button } from './Button'

export interface ErrorStateProps {
  message: string
  detail?: string
  onRetry?: () => void
  className?: string
}

export function ErrorState({ message, detail, onRetry, className }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-start gap-3 rounded-lg border border-[var(--danger-9)]/30 bg-[var(--score-low-bg)] px-4 py-4',
        className,
      )}
    >
      <div className="flex items-start gap-2.5">
        <svg className="mt-0.5 shrink-0 text-[var(--danger-9)]" width="16" height="16" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.4" />
          <path d="M8 5v3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
          <circle cx="8" cy="11" r="0.8" fill="currentColor" />
        </svg>
        <div className="flex flex-col gap-0.5">
          <span className="text-sm font-medium text-[var(--text-primary)]">{message}</span>
          {detail && <span className="text-[13px] text-[var(--text-secondary)]">{detail}</span>}
        </div>
      </div>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}
