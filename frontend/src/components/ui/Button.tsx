import { forwardRef } from 'react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { Spinner } from './Spinner'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline'
export type ButtonSize = 'sm' | 'md' | 'lg' | 'icon'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  icon?: ReactNode
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'bg-[var(--accent-9)] text-[var(--accent-contrast)] hover:bg-[var(--accent-10)] disabled:bg-[var(--accent-9)]',
  secondary:
    'bg-[var(--surface-3)] text-[var(--text-primary)] border border-[var(--border-default)] hover:bg-[var(--surface-4)]',
  outline:
    'bg-transparent text-[var(--text-primary)] border border-[var(--border-default)] hover:bg-[var(--surface-2)]',
  ghost: 'bg-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--text-primary)]',
  danger: 'bg-[var(--danger-9)] text-white hover:bg-[var(--danger-10)]',
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-7 px-2.5 text-[13px] gap-1.5 rounded-md',
  md: 'h-8 px-3 text-sm gap-1.5 rounded-md',
  lg: 'h-10 px-4 text-sm gap-2 rounded-lg',
  icon: 'h-8 w-8 rounded-md justify-center',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading, icon, disabled, className, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center font-medium select-none whitespace-nowrap',
        'transition-[transform,background-color,color,box-shadow] duration-150 ease-[var(--ease-out)]',
        'active:scale-[0.97]',
        'disabled:opacity-50 disabled:pointer-events-none',
        'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] focus-visible:outline-offset-2',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    >
      {loading ? (
        <Spinner size={size === 'lg' ? 16 : 14} className={children ? '' : undefined} />
      ) : (
        icon
      )}
      {children}
    </button>
  )
})
