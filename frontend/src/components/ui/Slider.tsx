import { useId } from 'react'
import { cn } from '@/lib/cn'

export interface SliderProps {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  label?: string
  formatValue?: (v: number) => string
  disabled?: boolean
  id?: string
}

export function Slider({ value, onChange, min = 0, max = 1, step = 0.01, label, formatValue, disabled, id }: SliderProps) {
  const autoId = useId()
  const sliderId = id ?? autoId
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div className="flex flex-col gap-1.5">
      {(label || formatValue) && (
        <div className="flex items-center justify-between">
          {label && (
            <label htmlFor={sliderId} className="text-[13px] font-medium text-[var(--text-secondary)]">
              {label}
            </label>
          )}
          <span className="font-mono text-[12px] tabular-nums text-[var(--text-primary)]">
            {formatValue ? formatValue(value) : value}
          </span>
        </div>
      )}
      <input
        id={sliderId}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className={cn(
          'h-1.5 w-full cursor-pointer appearance-none rounded-full outline-none disabled:opacity-50 disabled:cursor-not-allowed',
          '[&::-webkit-slider-runnable-track]:h-1.5 [&::-webkit-slider-runnable-track]:rounded-full',
          '[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5',
          '[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-[var(--accent-9)]',
          '[&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-[var(--surface-0)]',
          '[&::-webkit-slider-thumb]:-mt-1 [&::-webkit-slider-thumb]:transition-transform [&::-webkit-slider-thumb]:duration-150',
          '[&::-webkit-slider-thumb]:active:scale-90',
          'focus-visible:[&::-webkit-slider-thumb]:outline-2 focus-visible:[&::-webkit-slider-thumb]:outline-[var(--focus-ring)]',
        )}
        style={{
          background: `linear-gradient(to right, var(--accent-9) ${pct}%, var(--surface-4) ${pct}%)`,
        }}
      />
    </div>
  )
}
