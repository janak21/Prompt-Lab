import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  /** Every empty state needs a real next action, not just "No data". */
  action: ReactNode
  className?: string
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-start gap-3 rounded-lg border border-dashed border-[var(--border-default)]',
        'bg-[var(--surface-1)] px-6 py-8',
        className,
      )}
    >
      {icon && <div className="text-[var(--text-tertiary)]">{icon}</div>}
      <div className="flex flex-col gap-1">
        <h3 className="text-sm font-medium text-[var(--text-primary)]">{title}</h3>
        {description && <p className="max-w-md text-[13px] text-[var(--text-secondary)]">{description}</p>}
      </div>
      {action}
    </div>
  )
}
