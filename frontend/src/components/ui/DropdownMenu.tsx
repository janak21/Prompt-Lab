import { cloneElement, isValidElement, useEffect, useRef, useState } from 'react'
import type { ReactElement, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/cn'

export interface DropdownItem {
  id: string
  label: ReactNode
  onSelect: () => void
  danger?: boolean
  disabled?: boolean
  icon?: ReactNode
}

export interface DropdownMenuProps {
  trigger: ReactElement
  items: DropdownItem[]
  align?: 'start' | 'end'
}

export function DropdownMenu({ trigger, items, align = 'end' }: DropdownMenuProps) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [activeIdx, setActiveIdx] = useState(0)
  const triggerRef = useRef<HTMLElement | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const openMenu = () => {
    const el = triggerRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setPos({ x: align === 'end' ? r.right : r.left, y: r.bottom + 4 })
    setActiveIdx(0)
    setOpen(true)
  }

  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node) && !triggerRef.current?.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveIdx((i) => Math.min(items.length - 1, i + 1))
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIdx((i) => Math.max(0, i - 1))
      }
      if (e.key === 'Enter') {
        const item = items[activeIdx]
        if (item && !item.disabled) {
          item.onSelect()
          setOpen(false)
        }
      }
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, items, activeIdx])

  if (!isValidElement(trigger)) return trigger

  const clonedTrigger = cloneElement(trigger as ReactElement<Record<string, unknown>>, {
    ref: (node: HTMLElement) => {
      triggerRef.current = node
    },
    onClick: (e: MouseEvent) => {
      ;(trigger.props as Record<string, unknown> & { onClick?: (e: MouseEvent) => void }).onClick?.(e)
      if (open) setOpen(false)
      else openMenu()
    },
    'aria-haspopup': 'menu',
    'aria-expanded': open,
  })

  return (
    <>
      {clonedTrigger}
      {open &&
        createPortal(
          <div
            ref={menuRef}
            role="menu"
            style={{ position: 'fixed', left: align === 'end' ? undefined : pos.x, right: align === 'end' ? window.innerWidth - pos.x : undefined, top: pos.y, transformOrigin: `top ${align === 'end' ? 'right' : 'left'}` }}
            className={cn(
              'z-[100] min-w-[180px] rounded-md border border-[var(--border-default)] bg-[var(--surface-3)] p-1',
              'shadow-[var(--shadow-md)] motion-safe:animate-[pop-in_150ms_var(--ease-out)]',
            )}
          >
            {items.map((item, i) => (
              <button
                key={item.id}
                role="menuitem"
                disabled={item.disabled}
                onMouseEnter={() => setActiveIdx(i)}
                onClick={() => {
                  item.onSelect()
                  setOpen(false)
                }}
                className={cn(
                  'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-[13px]',
                  'transition-colors duration-100 disabled:opacity-40 disabled:pointer-events-none',
                  item.danger ? 'text-[var(--danger-10)]' : 'text-[var(--text-primary)]',
                  i === activeIdx ? 'bg-[var(--surface-4)]' : '',
                )}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  )
}
