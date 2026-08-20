import { useRef } from 'react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

// {{variable}} tokens — must match the server's extraction regex exactly
// (see lib/mock/rng.ts extractVariableNames) so what's highlighted here is
// what the backend will actually treat as a template variable.
const VAR_RE = /\{\{\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\}\}/g
const VAR_CAPTURE_RE = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g

export function extractTemplateVariables(template: string): string[] {
  const found = new Set<string>()
  let m: RegExpExecArray | null
  const re = new RegExp(VAR_CAPTURE_RE)
  while ((m = re.exec(template))) found.add(m[1])
  return [...found]
}

function renderHighlighted(text: string): ReactNode[] {
  const parts: ReactNode[] = []
  let last = 0
  let key = 0
  const re = new RegExp(VAR_RE)
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    parts.push(
      <span
        key={key++}
        className="rounded-[3px]"
        style={{ color: 'var(--accent-10)', backgroundColor: 'var(--accent-a-20)' }}
      >
        {m[0]}
      </span>,
    )
    last = m.index + m[0].length
  }
  parts.push(text.slice(last))
  // A trailing newline in a <textarea> isn't reflected in scrollHeight unless
  // the mirrored text also ends with one — keeps the overlay's last line
  // aligned with the textarea's own after pressing Enter at the end.
  parts.push('\n')
  return parts
}

/**
 * A monospace template textarea with live `{{variable}}` syntax highlighting.
 *
 * Technique: a transparent-text textarea sits on top of a same-metrics
 * highlight layer underneath. The real textarea holds the real value (so
 * selection, copy, and IME all work normally) — only its glyph color is
 * transparent, letting the colored overlay show through. Scroll position is
 * synced on every scroll event so long templates stay aligned while
 * scrolling; the two layers share font, padding, and line-height exactly so
 * this holds at any scroll offset, not just at the top.
 */
export function VariableTemplateEditor({
  value,
  onChange,
  readOnly,
  minRows = 12,
  placeholder,
  id,
  className,
}: {
  value: string
  onChange?: (v: string) => void
  readOnly?: boolean
  minRows?: number
  placeholder?: string
  id?: string
  className?: string
}) {
  const overlayRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const syncScroll = () => {
    if (overlayRef.current && textareaRef.current) {
      overlayRef.current.scrollTop = textareaRef.current.scrollTop
      overlayRef.current.scrollLeft = textareaRef.current.scrollLeft
    }
  }

  const lineHeightPx = 20
  const minHeight = minRows * lineHeightPx + 16

  return (
    <div
      className={cn(
        'relative rounded-md border border-[var(--border-default)] bg-[var(--surface-1)]',
        'transition-[border-color,box-shadow] duration-150 ease-[var(--ease-out)]',
        'focus-within:border-[var(--accent-9)] focus-within:ring-2 focus-within:ring-[var(--accent-a-20)]',
        readOnly && 'opacity-90',
        className,
      )}
    >
      <div
        ref={overlayRef}
        aria-hidden
        className={cn(
          'pointer-events-none absolute inset-0 overflow-hidden whitespace-pre-wrap break-words',
          'px-2.5 py-2 font-mono text-[13px] leading-5 text-[var(--text-primary)]',
        )}
        style={{ minHeight }}
      >
        {renderHighlighted(value)}
      </div>
      <textarea
        ref={textareaRef}
        id={id}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        onScroll={syncScroll}
        readOnly={readOnly}
        spellCheck={false}
        placeholder={placeholder}
        rows={minRows}
        className={cn(
          'relative w-full resize-y bg-transparent px-2.5 py-2 font-mono text-[13px] leading-5',
          'text-transparent caret-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]',
          'focus:outline-none disabled:cursor-not-allowed',
        )}
        style={{ WebkitTextFillColor: 'transparent', minHeight }}
      />
    </div>
  )
}
