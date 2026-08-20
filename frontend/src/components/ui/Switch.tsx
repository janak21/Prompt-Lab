import { useId } from 'react'
import { cn } from '@/lib/cn'

export interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label?: string
  disabled?: boolean
  id?: string
}

export function Switch({ checked, onChange, label, disabled, id }: SwitchProps) {
  const autoId = useId()
  const switchId = id ?? autoId
  return (
    <label htmlFor={switchId} className={cn('inline-flex items-center gap-2 select-none', disabled ? 'opacity-50' : 'cursor-pointer')}>
      <button
        id={switchId}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-5 w-8 shrink-0 rounded-full transition-colors duration-150 ease-[var(--ease-out)]',
          'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] focus-visible:outline-offset-2',
          checked ? 'bg-[var(--accent-9)]' : 'bg-[var(--surface-4)]',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm',
            'transition-transform duration-150 ease-[var(--ease-out)]',
            checked && 'translate-x-3',
          )}
        />
      </button>
      {label && <span className="text-sm text-[var(--text-primary)]">{label}</span>}
    </label>
  )
}
