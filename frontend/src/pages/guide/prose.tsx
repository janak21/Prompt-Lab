// Shared typography primitives for the Guide's long-form reading content.
//
// The rest of the app is a dense data instrument (DESIGN.md: "the data is the
// interface"); the Guide is the one place that's actually meant to be *read*, so it
// gets its own comfortable-measure prose scale instead of the dashboard's compact
// 13px/12px rhythm. Every section still lives inside `.guide-prose`, which caps line
// length -- see Guide.tsx.

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'

export function Section({ id, title, eyebrow, children }: { id: string; title: string; eyebrow?: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20 border-t border-[var(--border-subtle)] pt-10 first:border-t-0 first:pt-0">
      {eyebrow && <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--accent-10)]">{eyebrow}</p>}
      <h2 className="text-[22px] font-semibold tracking-tight text-[var(--text-primary)]">{title}</h2>
      <div className="mt-4 flex flex-col gap-4">{children}</div>
    </section>
  )
}

export function SubSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <div id={id} className="scroll-mt-20 flex flex-col gap-3 pt-2">
      <h3 className="text-[16px] font-semibold text-[var(--text-primary)]">{title}</h3>
      {children}
    </div>
  )
}

export function Lead({ children }: { children: ReactNode }) {
  return <p className="text-[16px] leading-[1.65] text-[var(--text-primary)]">{children}</p>
}

export function P({ children }: { children: ReactNode }) {
  return <p className="text-[14px] leading-[1.7] text-[var(--text-secondary)]">{children}</p>
}

export function UL({ children }: { children: ReactNode }) {
  return <ul className="flex flex-col gap-1.5 pl-5 text-[14px] leading-[1.65] text-[var(--text-secondary)]" style={{ listStyleType: 'disc' }}>{children}</ul>
}

export function OL({ children }: { children: ReactNode }) {
  return <ol className="flex flex-col gap-2 pl-5 text-[14px] leading-[1.65] text-[var(--text-secondary)]" style={{ listStyleType: 'decimal' }}>{children}</ol>
}

export function LI({ children }: { children: ReactNode }) {
  return <li className="pl-1">{children}</li>
}

export function Term({ children }: { children: ReactNode }) {
  return <code className="rounded bg-[var(--surface-2)] px-1 py-0.5 font-mono text-[0.9em] text-[var(--text-primary)]">{children}</code>
}

export function Strong({ children }: { children: ReactNode }) {
  return <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>
}

/** An internal cross-link to a real page in the app (see docs/DESIGN.md screens). */
export function AppLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="font-medium text-[var(--accent-10)] underline decoration-[var(--accent-a-40)] underline-offset-2 transition-colors duration-100 hover:decoration-[var(--accent-10)]">
      {children}
    </Link>
  )
}

/** A link out to a real URL (Anthropic's docs, primarily) -- opens in a new tab, with a
 * small glyph so it reads as "leaves the app" rather than looking like an AppLink. */
export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-[var(--accent-10)] underline decoration-[var(--accent-a-40)] underline-offset-2 transition-colors duration-100 hover:decoration-[var(--accent-10)]"
    >
      {children}
      <span aria-hidden="true" className="ml-0.5 inline-block">
        ↗
      </span>
    </a>
  )
}

type CalloutTone = 'info' | 'warning'

const CALLOUT_TONE: Record<CalloutTone, string> = {
  info: 'border-[var(--border-default)] bg-[var(--surface-1)]',
  warning: 'border-[color-mix(in_srgb,var(--score-mid)_40%,var(--border-default))] bg-[var(--score-mid-bg)]',
}

export function Callout({ tone = 'info', title, children }: { tone?: CalloutTone; title: string; children: ReactNode }) {
  return (
    <div className={cn('flex flex-col gap-1.5 rounded-lg border p-4', CALLOUT_TONE[tone])}>
      <span className="text-[12.5px] font-semibold text-[var(--text-primary)]">{title}</span>
      {/* A plain block, not flex: `children` is usually one run of inline text mixed
          with <Term>/<Strong>, and a flex container would put each text/element
          sibling on its own row instead of letting them wrap as one paragraph. */}
      <div className="text-[13.5px] leading-[1.65] text-[var(--text-secondary)] [&>p+p]:mt-2">{children}</div>
    </div>
  )
}

/** A concrete, labeled example -- used throughout so every concept is anchored to a
 * realistic instance rather than described only in the abstract. */
export function Example({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-3.5">
      {label && <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{label}</p>}
      <div className="flex flex-col gap-1.5 font-mono text-[12.5px] leading-[1.6] text-[var(--text-secondary)]">{children}</div>
    </div>
  )
}

export function ExampleRow({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex gap-2">
      <span className="shrink-0 text-[var(--text-tertiary)]">{k}</span>
      <span className="text-[var(--text-primary)]">{v}</span>
    </div>
  )
}

/** Horizontally-scrollable wrapper for any table too wide for the reading column. */
export function ProseTable({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
      <table className="w-full min-w-[560px] border-collapse text-[13px]">{children}</table>
    </div>
  )
}
