import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/cn'

export type ToastVariant = 'default' | 'success' | 'error'

interface ToastItem {
  id: number
  title: string
  description?: string
  variant: ToastVariant
}

type Listener = (toasts: ToastItem[]) => void
let toasts: ToastItem[] = []
const listeners = new Set<Listener>()
let seq = 1

function emit() {
  for (const l of listeners) l(toasts)
}

function push(title: string, description: string | undefined, variant: ToastVariant) {
  const id = seq++
  toasts = [...toasts, { id, title, description, variant }]
  emit()
  setTimeout(() => dismiss(id), 4000)
}

function dismiss(id: number) {
  toasts = toasts.filter((t) => t.id !== id)
  emit()
}

export const toast = Object.assign(
  (title: string, description?: string) => push(title, description, 'default'),
  {
    success: (title: string, description?: string) => push(title, description, 'success'),
    error: (title: string, description?: string) => push(title, description, 'error'),
  },
)

const variantAccent: Record<ToastVariant, string> = {
  default: 'var(--border-strong)',
  success: 'var(--score-high)',
  error: 'var(--danger-9)',
}

/** Mount once, anywhere in the tree (e.g. in App.tsx). Call `toast()` from anywhere after that. */
export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>(toasts)

  useEffect(() => {
    listeners.add(setItems)
    return () => {
      listeners.delete(setItems)
    }
  }, [])

  return createPortal(
    <div className="fixed bottom-4 right-4 z-[200] flex w-[340px] flex-col gap-2">
      {items.map((t) => (
        <div
          key={t.id}
          role="status"
          style={{ borderLeftColor: variantAccent[t.variant] }}
          className={cn(
            'rounded-lg border border-l-[3px] border-[var(--border-default)] bg-[var(--surface-3)] px-3.5 py-3',
            'shadow-[var(--shadow-md)] motion-safe:animate-[toast-in_220ms_var(--ease-out)]',
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex flex-col gap-0.5">
              <span className="text-[13px] font-medium text-[var(--text-primary)]">{t.title}</span>
              {t.description && <span className="text-[12px] text-[var(--text-secondary)]">{t.description}</span>}
            </div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss"
              className="shrink-0 text-[var(--text-tertiary)] transition-colors hover:text-[var(--text-primary)] focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        </div>
      ))}
    </div>,
    document.body,
  )
}
