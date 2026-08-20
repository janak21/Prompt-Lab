import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export interface Column<T> {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  sortValue?: (row: T) => string | number | null
  align?: 'left' | 'right' | 'center'
  width?: string
  mono?: boolean
}

export interface TableProps<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  onRowClick?: (row: T) => void
  className?: string
  dense?: boolean
  stickyHeader?: boolean
  initialSort?: { key: string; direction: 'asc' | 'desc' }
}

export function Table<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  className,
  dense = true,
  stickyHeader = true,
  initialSort,
}: TableProps<T>) {
  const [sort, setSort] = useState(initialSort ?? null)

  const sorted = useMemo(() => {
    if (!sort) return rows
    const col = columns.find((c) => c.key === sort.key)
    if (!col?.sortValue) return rows
    const dir = sort.direction === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = col.sortValue!(a)
      const bv = col.sortValue!(b)
      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1
      if (av < bv) return -1 * dir
      if (av > bv) return 1 * dir
      return 0
    })
  }, [rows, sort, columns])

  const toggleSort = (key: string) => {
    setSort((s) => {
      if (!s || s.key !== key) return { key, direction: 'desc' }
      if (s.direction === 'desc') return { key, direction: 'asc' }
      return null
    })
  }

  return (
    <div className={cn('overflow-auto rounded-lg border border-[var(--border-subtle)]', className)}>
      <table className="w-full border-collapse text-left text-[13px]">
        <thead className={cn(stickyHeader && 'sticky top-0 z-10')}>
          <tr className="bg-[var(--surface-2)]">
            {columns.map((col) => (
              <th
                key={col.key}
                style={{ width: col.width }}
                className={cn(
                  'border-b border-[var(--border-subtle)] px-3 font-medium text-[var(--text-tertiary)]',
                  dense ? 'py-2' : 'py-2.5',
                  col.align === 'right' && 'text-right',
                  col.align === 'center' && 'text-center',
                )}
              >
                {col.sortValue ? (
                  <button
                    type="button"
                    onClick={() => toggleSort(col.key)}
                    className={cn(
                      'inline-flex items-center gap-1 transition-colors hover:text-[var(--text-primary)]',
                      'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] focus-visible:outline-offset-2 rounded-sm',
                    )}
                  >
                    {col.header}
                    <SortIcon active={sort?.key === col.key} direction={sort?.key === col.key ? sort.direction : undefined} />
                  </button>
                ) : (
                  col.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn(
                'border-b border-[var(--border-subtle)] last:border-b-0 transition-colors duration-100',
                onRowClick && 'cursor-pointer hover:bg-[var(--surface-2)]',
              )}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={cn(
                    'px-3 text-[var(--text-primary)]',
                    dense ? 'py-1.5' : 'py-2.5',
                    col.mono && 'font-mono tabular-nums',
                    col.align === 'right' && 'text-right',
                    col.align === 'center' && 'text-center',
                  )}
                >
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SortIcon({ active, direction }: { active?: boolean; direction?: 'asc' | 'desc' }) {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 10 10"
      fill="none"
      className={cn('transition-transform duration-150', active ? 'text-[var(--accent-9)]' : 'text-[var(--text-disabled)]', direction === 'asc' && 'rotate-180')}
    >
      <path d="M2 4l3 -3 3 3M2 6l3 3 3 -3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" opacity={active ? 1 : 0.6} />
    </svg>
  )
}
