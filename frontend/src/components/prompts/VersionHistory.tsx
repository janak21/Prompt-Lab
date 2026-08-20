import { Badge, Button, Drawer } from '@/components/ui'
import { cn } from '@/lib/cn'
import type { PromptVersion } from '@/lib/types'
import { diffLines } from './diff'

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function VersionHistoryRail({
  versions,
  currentVersionNo,
  onSelect,
}: {
  versions: PromptVersion[]
  currentVersionNo: number
  onSelect: (version: PromptVersion) => void
}) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="px-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">
        Version history
      </h3>
      <ul className="flex flex-col gap-0.5">
        {versions.map((v) => {
          const isCurrent = v.version_no === currentVersionNo
          return (
            <li key={v.id}>
              <button
                type="button"
                onClick={() => onSelect(v)}
                className={cn(
                  'flex w-full flex-col items-start gap-0.5 rounded-md border border-transparent px-2.5 py-2 text-left',
                  'transition-colors duration-100 hover:bg-[var(--surface-2)]',
                  'focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] focus-visible:outline-offset-[-2px]',
                )}
              >
                <div className="flex w-full items-center gap-2">
                  <span className="font-mono text-[13px] font-medium text-[var(--text-primary)]">v{v.version_no}</span>
                  {isCurrent && <Badge variant="accent">Current</Badge>}
                  <span className="ml-auto font-mono text-[11px] tabular-nums text-[var(--text-tertiary)]">
                    {formatDate(v.created_at)}
                  </span>
                </div>
                <span className="line-clamp-1 text-[12px] text-[var(--text-secondary)]">
                  {v.notes || <span className="italic text-[var(--text-tertiary)]">No notes</span>}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function DiffView({ before, after }: { before: string; after: string }) {
  const lines = diffLines(before, after)
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]">
      <pre className="max-h-[50vh] overflow-auto px-3 py-2.5 text-[12.5px] leading-5">
        <code className="font-mono">
          {lines.map((line, i) => (
            <div
              key={i}
              className={cn(
                'whitespace-pre-wrap px-1.5 -mx-1.5',
                line.type === 'added' && 'bg-[var(--score-high-bg)] text-[var(--score-high)]',
                line.type === 'removed' && 'bg-[var(--score-low-bg)] text-[var(--score-low)] line-through decoration-[1px]',
                line.type === 'unchanged' && 'text-[var(--text-secondary)]',
              )}
            >
              <span className="mr-2 select-none opacity-60">
                {line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' '}
              </span>
              {line.text || ' '}
            </div>
          ))}
        </code>
      </pre>
    </div>
  )
}

/** Read-only preview of a past version, with a line diff against the previous version. */
export function VersionDetailDrawer({
  open,
  onClose,
  version,
  previousVersion,
  isCurrent,
  onRestore,
}: {
  open: boolean
  onClose: () => void
  version: PromptVersion | null
  previousVersion: PromptVersion | null
  isCurrent: boolean
  onRestore: (version: PromptVersion) => void
}) {
  if (!version) return null
  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={`Version ${version.version_no}${isCurrent ? ' (current)' : ''}`}
      width="640px"
      footer={
        !isCurrent && (
          <Button
            variant="secondary"
            onClick={() => {
              onRestore(version)
              onClose()
            }}
          >
            Restore into editor
          </Button>
        )
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-[var(--text-secondary)]">
          <span>
            Model: <span className="font-mono text-[var(--text-primary)]">{version.model ?? 'default'}</span>
          </span>
          <span>
            Temperature: <span className="font-mono tabular-nums text-[var(--text-primary)]">{version.temperature ?? 'default'}</span>
          </span>
          <span>
            Max tokens: <span className="font-mono tabular-nums text-[var(--text-primary)]">{version.max_tokens ?? 'default'}</span>
          </span>
        </div>
        {version.notes && (
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-[13px] text-[var(--text-secondary)]">
            {version.notes}
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <h4 className="text-[12px] font-medium text-[var(--text-tertiary)]">
            {previousVersion ? `Diff vs v${previousVersion.version_no}` : 'Template (first version — nothing to diff)'}
          </h4>
          <DiffView before={previousVersion?.template ?? ''} after={version.template} />
        </div>
        {version.system_prompt && (
          <div className="flex flex-col gap-1.5">
            <h4 className="text-[12px] font-medium text-[var(--text-tertiary)]">System prompt</h4>
            <DiffView before={previousVersion?.system_prompt ?? ''} after={version.system_prompt} />
          </div>
        )}
      </div>
    </Drawer>
  )
}
