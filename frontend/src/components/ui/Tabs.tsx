import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { cn } from '@/lib/cn'

export interface TabItem {
  id: string
  label: string
  count?: number
}

export interface TabsProps {
  tabs: TabItem[]
  value: string
  onChange: (id: string) => void
  className?: string
}

export function Tabs({ tabs, value, onChange, className }: TabsProps) {
  const listRef = useRef<HTMLDivElement>(null)
  const [indicator, setIndicator] = useState({ left: 0, width: 0 })

  useEffect(() => {
    const list = listRef.current
    if (!list) return
    const active = list.querySelector<HTMLElement>(`[data-tab-id="${CSS.escape(value)}"]`)
    if (active) {
      setIndicator({ left: active.offsetLeft, width: active.offsetWidth })
    }
  }, [value, tabs])

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const idx = tabs.findIndex((t) => t.id === value)
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      onChange(tabs[(idx + 1) % tabs.length].id)
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      onChange(tabs[(idx - 1 + tabs.length) % tabs.length].id)
    }
  }

  return (
    <div
      ref={listRef}
      role="tablist"
      onKeyDown={onKeyDown}
      className={cn('relative flex items-center gap-1 border-b border-[var(--border-subtle)]', className)}
    >
      {tabs.map((tab) => {
        const active = tab.id === value
        return (
          <button
            key={tab.id}
            role="tab"
            data-tab-id={tab.id}
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(tab.id)}
            className={cn(
              'relative flex items-center gap-1.5 px-3 py-2 text-[13px] font-medium transition-colors duration-150',
              'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] focus-visible:outline-offset-[-2px] rounded-t-sm',
              active ? 'text-[var(--text-primary)]' : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]',
            )}
          >
            {tab.label}
            {tab.count != null && (
              <span className="rounded-full bg-[var(--surface-3)] px-1.5 text-[11px] tabular-nums text-[var(--text-tertiary)]">
                {tab.count}
              </span>
            )}
          </button>
        )
      })}
      <span
        aria-hidden
        className="absolute bottom-0 h-[2px] bg-[var(--accent-9)] transition-[transform,width] duration-200 ease-[var(--ease-out)]"
        style={{ width: indicator.width, transform: `translateX(${indicator.left}px)` }}
      />
    </div>
  )
}
