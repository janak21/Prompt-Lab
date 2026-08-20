import { useEffect, useState } from 'react'
import { cn } from '@/lib/cn'
import { GUIDE_SECTIONS } from './guide/sections'

// Flat list of every anchor id in document order, used to figure out which one is
// "current" for the sticky TOC (scrollspy) and to know the very first id to
// highlight before the user has scrolled at all.
const ALL_IDS = GUIDE_SECTIONS.flatMap((s) => [s.id, ...(s.children ?? []).map((c) => c.id)])

function useActiveSection(): string {
  const [active, setActive] = useState(ALL_IDS[0])

  useEffect(() => {
    // Track which heading is nearest the top of the scroll container, rather than
    // "first intersecting" — with many short sections, several can be on-screen at
    // once, and the reader's attention is with whichever one just crossed the top.
    const visible = new Map<string, number>()

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.id
          if (entry.isIntersecting) {
            visible.set(id, entry.boundingClientRect.top)
          } else {
            visible.delete(id)
          }
        }
        if (visible.size === 0) return
        setActive((prev) => {
          let bestId = prev
          let bestTop = Number.POSITIVE_INFINITY
          for (const [id, top] of visible) {
            const distance = Math.abs(top)
            if (distance < bestTop) {
              bestTop = distance
              bestId = id
            }
          }
          return bestId
        })
      },
      { rootMargin: '-15% 0px -70% 0px', threshold: 0 },
    )

    for (const id of ALL_IDS) {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [])

  return active
}

function TocLink({ id, label, active, indent }: { id: string; label: string; active: boolean; indent?: boolean }) {
  return (
    <a
      href={`#${id}`}
      className={cn(
        'block rounded-md px-2.5 py-1 text-[12.5px] leading-snug transition-colors duration-100',
        'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] focus-visible:outline-offset-[-2px]',
        indent && 'ml-3 border-l border-[var(--border-subtle)] pl-2.5',
        active
          ? 'font-medium text-[var(--accent-10)]'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
      )}
    >
      {label}
    </a>
  )
}

export function GuidePage() {
  const active = useActiveSection()

  return (
    <div className="flex justify-center gap-10 px-6 py-8">
      <nav
        aria-label="Guide sections"
        className="sticky top-8 hidden h-fit max-h-[calc(100vh-4rem)] w-56 shrink-0 overflow-y-auto lg:block"
      >
        <p className="mb-2 px-2.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
          On this page
        </p>
        <div className="flex flex-col gap-0.5">
          {GUIDE_SECTIONS.map((section) => (
            <div key={section.id}>
              <TocLink id={section.id} label={section.navLabel} active={active === section.id} />
              {section.children && (
                <div className="mt-0.5 flex flex-col gap-0.5">
                  {section.children.map((child) => (
                    <TocLink key={child.id} id={child.id} label={child.navLabel} active={active === child.id} indent />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </nav>

      <main className="guide-prose w-full max-w-[70ch] pb-24">
        <header className="mb-10 flex flex-col gap-2">
          <h1 className="text-[28px] font-semibold tracking-tight text-[var(--text-primary)]">Guide</h1>
          <p className="text-[15px] leading-[1.6] text-[var(--text-secondary)]">
            What PromptLab is, where to start, and what everything means — read start to finish the first time, or
            jump to a section from the table of contents.
          </p>
        </header>
        <div className="flex flex-col gap-10">
          {GUIDE_SECTIONS.map((section) => (
            <div key={section.id}>{section.render()}</div>
          ))}
        </div>
      </main>
    </div>
  )
}
