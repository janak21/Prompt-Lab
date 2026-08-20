import { CodeBlock, CopyButton, Drawer, ScoreBadge, Spinner } from '@/components/ui'
import { CategoryBadge } from '@/components/datasets/CategoryBadge'
import type { RunCase } from '@/lib/types'

function fmtMs(ms: number | null) {
  if (ms == null) return '—'
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`
}
function fmtCost(cost: number | null) {
  if (cost == null) return '—'
  return `$${cost.toFixed(4)}`
}

export function RunCaseDrawer({
  row,
  onClose,
  loadingDetail,
}: {
  row: RunCase | null
  onClose: () => void
  loadingDetail?: boolean
}) {
  return (
    <Drawer open={!!row} onClose={onClose} title={row ? `Case #${row.idx + 1}` : 'Case'} width="640px">
      {row && (
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center gap-2">
            <CategoryBadge category={row.test_case.category} />
            <ScoreBadge score={row.final_score} />
            <span className="text-[12px] text-[var(--text-tertiary)]">
              {fmtMs(row.latency_ms)} · {fmtCost(row.cost)} ·{' '}
              {row.input_tokens != null && row.output_tokens != null
                ? `${row.input_tokens} in / ${row.output_tokens} out tok`
                : 'token counts unavailable'}
            </span>
          </div>

          {row.status === 'failed' && row.error && (
            <div className="rounded-md border border-[var(--danger-9)]/40 bg-[var(--score-low-bg)] px-3 py-2 text-[12.5px] text-[var(--score-low)]">
              {row.error}
            </div>
          )}

          <div className="flex flex-col gap-2">
            <span className="text-[13px] font-medium text-[var(--text-secondary)]">Inputs</span>
            <div className="flex flex-col gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-3">
              {Object.keys(row.test_case.inputs).length === 0 ? (
                <span className="text-[12px] text-[var(--text-tertiary)]">
                  No inputs recorded — the source dataset case may have been deleted.
                </span>
              ) : (
                Object.entries(row.test_case.inputs).map(([k, v]) => (
                  <div key={k} className="flex items-start gap-2 text-[12.5px]">
                    <span className="w-28 shrink-0 truncate font-mono text-[var(--text-tertiary)]" title={k}>
                      {k}
                    </span>
                    <span className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-[var(--text-primary)] selection:bg-[var(--accent-a-40)]">
                      {v}
                    </span>
                  </div>
                ))
              )}
              {row.test_case.solution_criteria && (
                <div className="mt-1 flex items-start gap-2 border-t border-[var(--border-subtle)] pt-1.5 text-[12.5px]">
                  <span className="w-28 shrink-0 text-[var(--text-tertiary)]">Criteria</span>
                  <span className="min-w-0 flex-1 whitespace-pre-wrap break-words text-[var(--text-secondary)]">
                    {row.test_case.solution_criteria}
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-[13px] font-medium text-[var(--text-secondary)]">Rendered prompt</span>
            {row.rendered_prompt ? (
              <CodeBlock code={row.rendered_prompt} language="text" collapseAfterLines={20} />
            ) : loadingDetail ? (
              <div className="flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-4 text-[12.5px] text-[var(--text-tertiary)]">
                <Spinner size={14} /> Loading full detail…
              </div>
            ) : (
              <span className="text-[12px] text-[var(--text-tertiary)]">Not available.</span>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-medium text-[var(--text-secondary)]">Output</span>
              {row.output && <CopyButton text={row.output} />}
            </div>
            {row.output ? (
              <CodeBlock code={row.output} language="text" collapseAfterLines={20} />
            ) : loadingDetail ? (
              <div className="flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-4 text-[12.5px] text-[var(--text-tertiary)]">
                <Spinner size={14} /> Loading full detail…
              </div>
            ) : (
              <span className="text-[12px] text-[var(--text-tertiary)]">
                {row.status === 'failed' ? 'Case failed — no output produced.' : 'Not available.'}
              </span>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-[13px] font-medium text-[var(--text-secondary)]">Grades</span>
            {row.grades.length === 0 ? (
              <span className="text-[12px] text-[var(--text-tertiary)]">No grades recorded for this case.</span>
            ) : (
              <div className="flex flex-col gap-2">
                {row.grades.map((g) => (
                  <div key={g.grader_name} className="rounded-lg border border-[var(--border-subtle)] p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[13px] font-medium text-[var(--text-primary)]">{g.grader_name}</span>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[11px] text-[var(--text-tertiary)]">weight {g.weight}</span>
                        <ScoreBadge score={g.score} size="sm" />
                      </div>
                    </div>
                    {g.reasoning && (
                      <p className="mt-1.5 whitespace-pre-wrap text-[12.5px] text-[var(--text-secondary)]">{g.reasoning}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Drawer>
  )
}
