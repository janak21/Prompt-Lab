import type { CSSProperties } from 'react'
import { cn } from '@/lib/cn'

export function Skeleton({ className, style }: { className?: string; style?: CSSProperties }) {
  return (
    <div
      style={style}
      className={cn(
        'animate-pulse rounded-md bg-[var(--surface-3)] motion-reduce:animate-none',
        className,
      )}
    />
  )
}

/** Skeleton rows shaped like a dense table — matches the final layout, not a spinner-in-a-box. */
export function TableSkeleton({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="flex flex-col gap-px overflow-hidden rounded-lg border border-[var(--border-subtle)]">
      <div className="flex gap-4 bg-[var(--surface-2)] px-3 py-2.5">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 bg-[var(--surface-1)] px-3 py-2.5">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-3 flex-1" style={{ animationDelay: `${(r * cols + c) * 20}ms` }} />
          ))}
        </div>
      ))}
    </div>
  )
}
