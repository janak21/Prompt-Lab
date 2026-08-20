import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export type BadgeVariant = 'neutral' | 'accent' | 'success' | 'warning' | 'danger'

const variantClasses: Record<BadgeVariant, string> = {
  neutral: 'bg-[var(--surface-3)] text-[var(--text-secondary)] border-[var(--border-default)]',
  accent: 'bg-[var(--accent-a-20)] text-[var(--accent-10)] border-transparent',
  success: 'bg-[var(--score-high-bg)] text-[var(--score-high)] border-transparent',
  warning: 'bg-[var(--score-mid-bg)] text-[var(--score-mid)] border-transparent',
  danger: 'bg-[var(--score-low-bg)] text-[var(--score-low)] border-transparent',
}

export function Badge({ variant = 'neutral', children, className }: { variant?: BadgeVariant; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium leading-none',
        variantClasses[variant],
        className,
      )}
    >
      {children}
    </span>
  )
}

/** A removable chip, used for detected {{variables}}. */
export function Tag({ children, onRemove, mono = true }: { children: ReactNode; onRemove?: () => void; mono?: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border border-[var(--border-default)] bg-[var(--surface-2)]',
        'px-1.5 py-0.5 text-[12px] text-[var(--text-secondary)]',
        mono && 'font-mono',
      )}
    >
      {children}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove"
          className="rounded-sm text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M1.5 1.5 8.5 8.5M8.5 1.5 1.5 8.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
        </button>
      )}
    </span>
  )
}
