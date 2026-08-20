import { forwardRef, useId } from 'react'
import type { SelectHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  label?: string
  hint?: string
  error?: string
  options: SelectOption[]
  placeholder?: string
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, options, placeholder, id, className, ...props },
  ref,
) {
  const autoId = useId()
  const selectId = id ?? autoId
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={selectId} className="text-[13px] font-medium text-[var(--text-secondary)]">
          {label}
        </label>
      )}
      <div className="relative">
        <select
          ref={ref}
          id={selectId}
          aria-invalid={!!error}
          className={cn(
            'w-full appearance-none rounded-md border border-[var(--border-default)] bg-[var(--surface-1)]',
            'h-8 pl-2.5 pr-8 text-sm text-[var(--text-primary)]',
            'transition-[border-color,box-shadow] duration-150 ease-[var(--ease-out)]',
            'focus-visible:outline-none focus-visible:border-[var(--accent-9)] focus-visible:ring-2 focus-visible:ring-[var(--accent-a-20)]',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            error && 'border-[var(--danger-9)]',
            className,
          )}
          {...props}
        >
          {placeholder && (
            <option value="" disabled hidden>
              {placeholder}
            </option>
          )}
          {options.map((o) => (
            <option key={o.value} value={o.value} disabled={o.disabled}>
              {o.label}
            </option>
          ))}
        </select>
        <svg
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]"
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
        >
          <path d="M2.5 4.5 6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      {error ? (
        <span className="text-[12px] text-[var(--danger-10)]">{error}</span>
      ) : hint ? (
        <span className="text-[12px] text-[var(--text-tertiary)]">{hint}</span>
      ) : null}
    </div>
  )
})
