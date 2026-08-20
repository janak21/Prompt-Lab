import { forwardRef, useId, useRef, useState } from 'react'
import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

const fieldBase =
  'w-full rounded-md border border-[var(--border-default)] bg-[var(--surface-1)] text-[var(--text-primary)] ' +
  'placeholder:text-[var(--text-tertiary)] transition-[border-color,box-shadow] duration-150 ease-[var(--ease-out)] ' +
  'focus-visible:outline-none focus-visible:border-[var(--accent-9)] focus-visible:ring-2 focus-visible:ring-[var(--accent-a-20)] ' +
  'disabled:opacity-50 disabled:cursor-not-allowed'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  hint?: string
  error?: string
  mono?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, mono, id, className, ...props },
  ref,
) {
  const autoId = useId()
  const inputId = id ?? autoId
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={inputId} className="text-[13px] font-medium text-[var(--text-secondary)]">
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        aria-invalid={!!error}
        aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
        className={cn(
          fieldBase,
          'h-8 px-2.5 text-sm',
          mono && 'font-mono',
          error && 'border-[var(--danger-9)] focus-visible:border-[var(--danger-9)] focus-visible:ring-[color-mix(in_srgb,var(--danger-9)_20%,transparent)]',
          className,
        )}
        {...props}
      />
      {error ? (
        <span id={`${inputId}-error`} className="text-[12px] text-[var(--danger-10)]">
          {error}
        </span>
      ) : hint ? (
        <span id={`${inputId}-hint`} className="text-[12px] text-[var(--text-tertiary)]">
          {hint}
        </span>
      ) : null}
    </div>
  )
})

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  hint?: string
  error?: string
  mono?: boolean
  autoGrow?: boolean
  minRows?: number
  maxRows?: number
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, mono, autoGrow = true, minRows = 3, maxRows = 24, id, className, onInput, style, ...props },
  ref,
) {
  const autoId = useId()
  const inputId = id ?? autoId
  const innerRef = useRef<HTMLTextAreaElement | null>(null)

  const setRefs = (node: HTMLTextAreaElement | null) => {
    innerRef.current = node
    if (typeof ref === 'function') ref(node)
    else if (ref) (ref as { current: HTMLTextAreaElement | null }).current = node
  }

  const resize = (el: HTMLTextAreaElement) => {
    if (!autoGrow) return
    el.style.height = 'auto'
    const lineHeight = 20
    const min = minRows * lineHeight + 16
    const max = maxRows * lineHeight + 16
    el.style.height = `${Math.min(max, Math.max(min, el.scrollHeight))}px`
  }

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={inputId} className="text-[13px] font-medium text-[var(--text-secondary)]">
          {label}
        </label>
      )}
      <textarea
        ref={setRefs}
        id={inputId}
        rows={minRows}
        aria-invalid={!!error}
        className={cn(
          fieldBase,
          'px-2.5 py-2 text-sm leading-5 resize-none',
          mono && 'font-mono',
          error && 'border-[var(--danger-9)]',
          className,
        )}
        style={{ ...style }}
        onInput={(e) => {
          resize(e.currentTarget)
          onInput?.(e)
        }}
        {...props}
      />
      {error ? (
        <span className="text-[12px] text-[var(--danger-10)]">{error}</span>
      ) : hint ? (
        <span className="text-[12px] text-[var(--text-tertiary)]">{hint}</span>
      ) : null}
    </div>
  )
})

/** Small helper for consumers that want a controlled auto-grow textarea without a ref dance. */
export function useAutoGrowValue(initial = '') {
  const [value, setValue] = useState(initial)
  return { value, setValue }
}
