import { cloneElement, isValidElement, useRef, useState } from 'react'
import type { ReactElement, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/cn'

// Once one tooltip is open, hovering an adjacent one should skip the delay
// and the entrance animation — this module-level timestamp implements that.
let lastTooltipCloseAt = 0
const INSTANT_WINDOW_MS = 400
const OPEN_DELAY_MS = 400

export interface TooltipProps {
  content: ReactNode
  children: ReactElement
  side?: 'top' | 'bottom' | 'left' | 'right'
}

export function Tooltip({ content, children, side = 'top' }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const [instant, setInstant] = useState(false)
  const [coords, setCoords] = useState({ x: 0, y: 0 })
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const triggerRef = useRef<HTMLElement | null>(null)

  const place = () => {
    const el = triggerRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const map = {
      top: { x: r.left + r.width / 2, y: r.top - 8 },
      bottom: { x: r.left + r.width / 2, y: r.bottom + 8 },
      left: { x: r.left - 8, y: r.top + r.height / 2 },
      right: { x: r.right + 8, y: r.top + r.height / 2 },
    }
    setCoords(map[side])
  }

  const show = () => {
    const wasInstant = Date.now() - lastTooltipCloseAt < INSTANT_WINDOW_MS
    setInstant(wasInstant)
    place()
    if (wasInstant) {
      setOpen(true)
    } else {
      timer.current = setTimeout(() => {
        place()
        setOpen(true)
      }, OPEN_DELAY_MS)
    }
  }

  const hide = () => {
    if (timer.current) clearTimeout(timer.current)
    if (open) lastTooltipCloseAt = Date.now()
    setOpen(false)
  }

  if (!isValidElement(children)) return children

  const trigger = cloneElement(children as ReactElement<Record<string, unknown>>, {
    ref: (node: HTMLElement) => {
      triggerRef.current = node
    },
    onMouseEnter: show,
    onMouseLeave: hide,
    onFocus: show,
    onBlur: hide,
  })

  const originMap = {
    top: { transform: 'translate(-50%, -100%)', origin: 'bottom center' },
    bottom: { transform: 'translate(-50%, 0)', origin: 'top center' },
    left: { transform: 'translate(-100%, -50%)', origin: 'right center' },
    right: { transform: 'translate(0, -50%)', origin: 'left center' },
  }[side]

  return (
    <>
      {trigger}
      {open &&
        createPortal(
          <div
            role="tooltip"
            style={{ position: 'fixed', left: coords.x, top: coords.y, transform: originMap.transform, transformOrigin: originMap.origin }}
            className={cn(
              'z-[100] pointer-events-none rounded-md border border-[var(--border-default)] bg-[var(--surface-3)]',
              'px-2 py-1 text-[12px] text-[var(--text-primary)] shadow-[var(--shadow-md)]',
              instant ? '' : 'motion-safe:animate-[pop-in_125ms_var(--ease-out)]',
            )}
          >
            {content}
          </div>,
          document.body,
        )}
    </>
  )
}
