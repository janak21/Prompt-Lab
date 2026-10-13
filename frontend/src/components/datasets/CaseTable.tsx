import { useState } from 'react'
import { Button, EmptyState, Select, toast } from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import type { ExpectedFormat, TestCase, UpdateCaseBody } from '@/lib/types'
import { CategoryBadge } from './CategoryBadge'
import { ALL_CATEGORY_OPTIONS, categoryLabel } from './category'

/** A cell that edits in place: click to focus, commits on blur/Enter, reverts on Escape. */
function EditableCell({
  value,
  onCommit,
  mono = true,
  placeholder,
}: {
  value: string
  onCommit: (value: string) => void
  mono?: boolean
  placeholder?: string
}) {
  const [draft, setDraft] = useState(value)
  const [editing, setEditing] = useState(false)

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => {
          setDraft(value)
          setEditing(true)
        }}
        className={`block w-full max-w-[220px] truncate rounded px-1 py-0.5 text-left transition-colors hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)] ${mono ? 'font-mono' : ''}`}
        title={value}
      >
        {value || <span className="text-[var(--text-tertiary)]">{placeholder ?? '—'}</span>}
      </button>
    )
  }

  return (
    <input
      autoFocus
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        setEditing(false)
        if (draft !== value) onCommit(draft)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.currentTarget.blur()
        } else if (e.key === 'Escape') {
          setDraft(value)
          setEditing(false)
        }
      }}
      className={`w-full max-w-[220px] rounded border border-[var(--accent-9)] bg-[var(--surface-1)] px-1 py-0.5 text-[13px] outline-none ring-2 ring-[var(--accent-a-20)] ${mono ? 'font-mono' : ''}`}
    />
  )
}

const FORMAT_OPTIONS = [
  { value: '', label: 'None' },
  { value: 'json', label: 'JSON' },
  { value: 'python', label: 'Python' },
  { value: 'regex', label: 'Regex' },
]

export function CaseTable({
  cases,
  variables,
  onCasesChange,
  onAddCase,
}: {
  cases: TestCase[]
  variables: string[]
  onCasesChange: (cases: TestCase[]) => void
  onAddCase: () => void
}) {
  const commit = async (id: number, patch: UpdateCaseBody) => {
    const prev = cases
    onCasesChange(cases.map((c) => (c.id === id ? { ...c, ...patch } : c)))
    try {
      const updated = await api.updateCase(id, patch)
      onCasesChange(prev.map((c) => (c.id === id ? updated : c)))
    } catch (e) {
      onCasesChange(prev)
      toast.error('Couldn’t save change', e instanceof ApiError ? e.message : 'Unknown error')
    }
  }

  const remove = async (id: number) => {
    const prev = cases
    onCasesChange(cases.filter((c) => c.id !== id))
    try {
      await api.deleteCase(id)
    } catch (e) {
      onCasesChange(prev)
      toast.error('Couldn’t delete case', e instanceof ApiError ? e.message : 'Unknown error')
    }
  }

  if (cases.length === 0) {
    return (
      <EmptyState
        title="No cases yet"
        description="Add a case manually, generate cases from a domain description, or import a file."
        action={
          <Button variant="primary" onClick={onAddCase}>
            Add case
          </Button>
        }
      />
    )
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
      <table className="w-full min-w-max border-collapse text-left text-[13px]">
        <thead>
          <tr className="bg-[var(--surface-2)]">
            {variables.map((v) => (
              <th key={v} className="border-b border-[var(--border-subtle)] px-3 py-2 font-mono font-medium text-[var(--text-tertiary)]">
                {v}
              </th>
            ))}
            <th className="border-b border-[var(--border-subtle)] px-3 py-2 font-medium text-[var(--text-tertiary)]">Conversation</th>
            <th className="border-b border-[var(--border-subtle)] px-3 py-2 font-medium text-[var(--text-tertiary)]">Solution criteria</th>
            <th className="border-b border-[var(--border-subtle)] px-3 py-2 font-medium text-[var(--text-tertiary)]">Category</th>
            <th className="border-b border-[var(--border-subtle)] px-3 py-2 font-medium text-[var(--text-tertiary)]">Format</th>
            <th className="border-b border-[var(--border-subtle)] px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id} className="border-b border-[var(--border-subtle)] last:border-b-0 hover:bg-[var(--surface-1)]">
              {variables.map((v) => (
                <td key={v} className="px-3 py-1.5">
                  <EditableCell
                    value={c.inputs[v] ?? ''}
                    onCommit={(val) => commit(c.id, { inputs: { ...c.inputs, [v]: val } })}
                  />
                </td>
              ))}
              <td className="px-3 py-1.5">
                <EditableCell value={JSON.stringify(c.conversation ?? [])} onCommit={(value) => {
                  try {
                    const turns = JSON.parse(value)
                    if (!Array.isArray(turns) || turns.some((t) => typeof t !== 'string') || turns.length > 20) throw new Error()
                    commit(c.id, { conversation: turns })
                  } catch {
                    toast.error('Invalid conversation', 'Use a JSON array of up to 20 user-turn strings.')
                  }
                }} />
              </td>
              <td className="px-3 py-1.5">
                <EditableCell
                  value={c.solution_criteria ?? ''}
                  mono={false}
                  placeholder="none"
                  onCommit={(val) => commit(c.id, { solution_criteria: val || undefined })}
                />
              </td>
              <td className="px-3 py-1.5">
                <div className="flex items-center gap-1.5">
                  <CategoryBadge category={c.category} />
                  <select
                    aria-label="Category"
                    value={c.category ?? 'standard'}
                    onChange={(e) => commit(c.id, { category: e.target.value })}
                    className="rounded border border-transparent bg-transparent text-[11px] text-[var(--text-tertiary)] hover:border-[var(--border-default)] focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                  >
                    {ALL_CATEGORY_OPTIONS.map((cat) => (
                      <option key={cat} value={cat}>
                        {categoryLabel(cat)}
                      </option>
                    ))}
                  </select>
                </div>
              </td>
              <td className="px-3 py-1.5">
                <Select
                  aria-label="Expected format"
                  value={c.expected_format ?? ''}
                  onChange={(e) => commit(c.id, { expected_format: (e.target.value || null) as ExpectedFormat })}
                  options={FORMAT_OPTIONS}
                  className="!h-7 !text-[12px]"
                />
              </td>
              <td className="px-3 py-1.5 text-right">
                <Button size="sm" variant="ghost" onClick={() => remove(c.id)} aria-label="Delete case">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path
                      d="M2.5 4h9M5.5 4V2.5h3V4M5 6.5v4M9 6.5v4M3.5 4l.5 8h6l.5-8"
                      stroke="currentColor"
                      strokeWidth="1.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
