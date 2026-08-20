import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { useTheme } from '@/hooks/useTheme'
import { MOCK_MODE } from '@/lib/api'

function icon(paths: ReactNode) {
  return function Icon({ className }: { className?: string }) {
    return (
      <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none">
        {paths}
      </svg>
    )
  }
}

const PromptIcon = icon(
  <path d="M3 2.5h7l3 3v8a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1Z M9.5 2.5v3h3 M4.5 8h6 M4.5 10.5h4" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />,
)
const DatasetIcon = icon(
  <path d="M2.5 4c0-1 2.5-1.5 5.5-1.5S13.5 3 13.5 4s-2.5 1.5-5.5 1.5S2.5 5 2.5 4Z M2.5 4v8c0 1 2.5 1.5 5.5 1.5s5.5-.5 5.5-1.5V4 M2.5 8c0 1 2.5 1.5 5.5 1.5s5.5-.5 5.5-1.5" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />,
)
const RunIcon = icon(<path d="M3 2.5v11l10-5.5-10-5.5Z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />)
const CompareIcon = icon(<path d="M5.5 2.5v11M10.5 2.5v11M2.5 5.5h6M7.5 10.5h6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />)
const SettingsIcon = icon(
  <>
    <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.2" />
    <path d="M8 2.5v1.5M8 12v1.5M13.5 8H12M4 8H2.5M11.6 4.4l-1 1M5.4 10.6l-1 1M11.6 11.6l-1-1M5.4 5.4l-1-1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </>,
)
const SunIcon = icon(
  <>
    <circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.2" />
    <path d="M8 1.5v1.3M8 13.2v1.3M14.5 8h-1.3M2.8 8H1.5M12.7 3.3l-.9.9M4.2 11.8l-.9.9M12.7 12.7l-.9-.9M4.2 4.2l-.9-.9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
  </>,
)
const MoonIcon = icon(<path d="M13 9.3A5.3 5.3 0 0 1 6.7 3 5.5 5.5 0 1 0 13 9.3Z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />)

const NAV_ITEMS = [
  { to: '/prompts', label: 'Prompts', icon: PromptIcon },
  { to: '/datasets', label: 'Datasets', icon: DatasetIcon },
  { to: '/runs', label: 'Runs', icon: RunIcon },
  { to: '/compare', label: 'Compare', icon: CompareIcon },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]

export function AppShell({ children }: { children: ReactNode }) {
  const { theme, toggle } = useTheme()

  return (
    <div className="flex h-full bg-[var(--surface-0)]">
      <aside className="flex w-56 shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--surface-1)]">
        <div className="flex h-12 items-center gap-2 border-b border-[var(--border-subtle)] px-4">
          <div className="flex h-5 w-5 items-center justify-center rounded-[5px] bg-[var(--accent-9)] text-[11px] font-bold text-[var(--accent-contrast)]">
            P
          </div>
          <span className="text-[13px] font-semibold tracking-tight text-[var(--text-primary)]">PromptLab</span>
          {MOCK_MODE && (
            <span className="ml-auto rounded border border-[var(--border-default)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-tertiary)]">
              MOCK
            </span>
          )}
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 p-2">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors duration-100',
                  'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] focus-visible:outline-offset-[-2px]',
                  isActive
                    ? 'bg-[var(--accent-a-10)] text-[var(--accent-10)]'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--text-primary)]',
                )
              }
            >
              <item.icon className="shrink-0" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-[var(--border-subtle)] p-2">
          <button
            type="button"
            onClick={toggle}
            className={cn(
              'flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium',
              'text-[var(--text-secondary)] transition-colors duration-100 hover:bg-[var(--surface-2)] hover:text-[var(--text-primary)]',
              'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] focus-visible:outline-offset-[-2px]',
            )}
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
            {theme === 'dark' ? 'Light theme' : 'Dark theme'}
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  )
}
