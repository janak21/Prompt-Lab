import { useState } from 'react'
import { cn } from '@/lib/cn'

export function CopyButton({ text, className, label = 'Copy' }: { text: string; className?: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Fallback for contexts without clipboard permission.
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={copied ? 'Copied' : label}
      className={cn(
        'inline-flex h-6 items-center gap-1 rounded-md border border-[var(--border-default)] bg-[var(--surface-2)] px-1.5',
        'text-[11px] font-medium text-[var(--text-secondary)] transition-[background-color,color,transform] duration-150 ease-[var(--ease-out)]',
        'hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)] active:scale-[0.94]',
        'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] focus-visible:outline-offset-1',
        className,
      )}
    >
      {copied ? (
        <>
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
            <path d="M2.5 6.2 5 8.7l4.5-5.4" stroke="var(--score-high)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Copied
        </>
      ) : (
        <>
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
            <rect x="4" y="4" width="6.5" height="6.5" rx="1" stroke="currentColor" strokeWidth="1.2" />
            <path d="M2.5 7.5v-4A1 1 0 0 1 3.5 2.5h4" stroke="currentColor" strokeWidth="1.2" />
          </svg>
          {label}
        </>
      )}
    </button>
  )
}
