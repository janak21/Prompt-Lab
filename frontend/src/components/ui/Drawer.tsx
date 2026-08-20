import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { Portal } from './Portal'
import { useEscapeKey } from '@/hooks/useEscapeKey'

export interface DrawerProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  width?: string
}

export function Drawer({ open, onClose, title, children, footer, width = '520px' }: DrawerProps) {
  const ref = useRef<HTMLDivElement>(null)
  useEscapeKey(open, onClose)

  useEffect(() => {
    if (open) ref.current?.focus()
  }, [open])

  if (!open) return null

  return (
    <Portal>
      <div className="fixed inset-0 z-50">
        <div
          onClick={onClose}
          aria-hidden
          className="absolute inset-0 bg-black/50 motion-safe:animate-[fade-in_200ms_var(--ease-out)]"
        />
        <div
          ref={ref}
          role="dialog"
          aria-modal="true"
          aria-labelledby="drawer-title"
          tabIndex={-1}
          style={{ width }}
          className={cn(
            'absolute right-0 top-0 flex h-full max-w-full flex-col border-l border-[var(--border-default)]',
            'bg-[var(--surface-1)] shadow-[var(--shadow-lg)]',
            'motion-safe:animate-[drawer-in_260ms_var(--ease-drawer)]',
          )}
        >
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-3.5">
            <h2 id="drawer-title" className="text-[14px] font-semibold text-[var(--text-primary)]">
              {title}
            </h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className={cn(
                'flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-tertiary)]',
                'transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]',
                'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]',
              )}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2.5 2.5 11.5 11.5M11.5 2.5 2.5 11.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] px-5 py-3">{footer}</div>}
        </div>
      </div>
    </Portal>
  )
}
