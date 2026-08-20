import { useEffect, useRef } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { Portal } from './Portal'
import { useEscapeKey } from '@/hooks/useEscapeKey'

export interface DialogProps {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
}

const sizeClasses = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-xl' }

export function Dialog({ open, onClose, title, description, children, footer, size = 'md' }: DialogProps) {
  const ref = useRef<HTMLDivElement>(null)
  useEscapeKey(open, onClose)

  useEffect(() => {
    if (!open) return
    const prev = document.activeElement as HTMLElement | null
    ref.current?.focus()
    return () => prev?.focus()
  }, [open])

  if (!open) return null

  return (
    <Portal>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          onClick={onClose}
          aria-hidden
          className={cn(
            'absolute inset-0 bg-black/50',
            'transition-opacity duration-200 ease-[var(--ease-out)]',
            'motion-safe:animate-[fade-in_180ms_var(--ease-out)]',
          )}
        />
        <div
          ref={ref}
          role="dialog"
          aria-modal="true"
          aria-labelledby="dialog-title"
          tabIndex={-1}
          onKeyDown={(e) => e.key === 'Tab' && trapFocus(e, ref.current)}
          className={cn(
            'relative w-full rounded-xl border border-[var(--border-default)] bg-[var(--surface-2)] shadow-[var(--shadow-lg)]',
            'origin-center motion-safe:animate-[dialog-in_180ms_var(--ease-out)]',
            sizeClasses[size],
          )}
        >
          <div className="flex flex-col gap-1 border-b border-[var(--border-subtle)] px-5 py-4">
            <h2 id="dialog-title" className="text-[15px] font-semibold text-[var(--text-primary)]">
              {title}
            </h2>
            {description && <p className="text-[13px] text-[var(--text-secondary)]">{description}</p>}
          </div>
          <div className="max-h-[65vh] overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] px-5 py-3">{footer}</div>}
        </div>
      </div>
    </Portal>
  )
}

function trapFocus(e: KeyboardEvent, container: HTMLElement | null) {
  if (!container) return
  const focusables = container.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
  )
  if (focusables.length === 0) return
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}
