import { useState } from 'react'
import { cn } from '@/lib/cn'
import { CopyButton } from './CopyButton'

export interface CodeBlockProps {
  code: string
  language?: string
  className?: string
  /** Lines beyond this are collapsed behind an explicit "Show more" — never silently truncated. */
  collapseAfterLines?: number
  title?: string
}

export function CodeBlock({ code, language, className, collapseAfterLines = 16, title }: CodeBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const lines = code.split('\n')
  const isLong = lines.length > collapseAfterLines
  const shown = expanded || !isLong ? code : lines.slice(0, collapseAfterLines).join('\n')

  return (
    <div className={cn('overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]', className)}>
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-3 py-1.5">
        <span className="font-mono text-[11px] text-[var(--text-tertiary)]">{title ?? language ?? 'text'}</span>
        <CopyButton text={code} />
      </div>
      <div className="relative">
        <pre className="max-w-full overflow-x-auto px-3 py-2.5 text-[12.5px] leading-5">
          <code className="font-mono whitespace-pre text-[var(--text-primary)] selection:bg-[var(--accent-a-40)]">{shown}</code>
        </pre>
        {isLong && !expanded && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-[var(--surface-2)] to-transparent" />
        )}
      </div>
      {isLong && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className={cn(
            'w-full border-t border-[var(--border-subtle)] px-3 py-1.5 text-center text-[12px] font-medium',
            'text-[var(--text-secondary)] transition-colors duration-150 hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]',
            'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] focus-visible:outline-offset-[-2px]',
          )}
        >
          {expanded ? 'Show less' : `Show ${lines.length - collapseAfterLines} more lines`}
        </button>
      )}
    </div>
  )
}
