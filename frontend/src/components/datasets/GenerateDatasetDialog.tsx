import { useEffect, useRef, useState } from 'react'
import { Badge, Button, Dialog, Input, ProgressBar, Select, Textarea, toast } from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import type { Dataset, GenerationMode, TestCase } from '@/lib/types'
import { CategoryBadge } from './CategoryBadge'

const MODE_EXPLANATION: Record<GenerationMode, string> = {
  standard: "Realistic, well-formed inputs that exercise the prompt's normal, expected path.",
  adversarial:
    'Deliberately hostile inputs designed to break the prompt: empty fields, missing data, contradictory instructions, prompt-injection attempts, boundary-length text, wrong-language input, special characters, and hostile formatting. Use this to find where the prompt fails before your users do.',
  mixed: 'Roughly half standard, half adversarial — a realistic day-to-day mix.',
}

function TagInput({ values, onChange, placeholder }: { values: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const v = draft.trim()
    if (!v || values.includes(v)) return
    onChange([...values, v])
    setDraft('')
  }
  return (
    <div className="flex flex-col gap-1.5">
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            add()
          }
        }}
        onBlur={add}
        placeholder={placeholder}
        mono
      />
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {values.map((v) => (
            <span
              key={v}
              className="inline-flex items-center gap-1 rounded-md border border-[var(--border-default)] bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-[12px] text-[var(--text-secondary)]"
            >
              {v}
              <button
                type="button"
                aria-label={`Remove ${v}`}
                onClick={() => onChange(values.filter((x) => x !== v))}
                className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
              >
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M1.5 1.5 8.5 8.5M8.5 1.5 1.5 8.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                </svg>
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export function GenerateDatasetDialog({
  open,
  onClose,
  datasetId,
  defaultVariables,
  onGenerated,
}: {
  open: boolean
  onClose: () => void
  /** Append to this dataset, or omit to create a new one. */
  datasetId?: number
  defaultVariables?: string[]
  onGenerated: (result: { dataset: Dataset; cases: TestCase[] }) => void
}) {
  const [name, setName] = useState('')
  const [domainDescription, setDomainDescription] = useState('')
  const [variables, setVariables] = useState<string[]>(defaultVariables ?? [])
  const [count, setCount] = useState(10)
  const [mode, setMode] = useState<GenerationMode>('standard')
  const [submitting, setSubmitting] = useState(false)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<{ dataset: Dataset; cases: TestCase[] } | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const progressTimer = useRef<number | null>(null)

  useEffect(() => {
    if (open) {
      setResult(null)
      setErrors({})
      if (!datasetId) {
        setName('')
        setVariables(defaultVariables ?? [])
      } else {
        setVariables(defaultVariables ?? [])
      }
    } else if (progressTimer.current) {
      window.clearInterval(progressTimer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const startFakeProgress = () => {
    setProgress(4)
    progressTimer.current = window.setInterval(() => {
      setProgress((p) => (p < 90 ? p + Math.max(0.5, (90 - p) * 0.06) : p))
    }, 300)
  }
  const stopFakeProgress = (final: number) => {
    if (progressTimer.current) window.clearInterval(progressTimer.current)
    setProgress(final)
  }

  const submit = async () => {
    const errs: Record<string, string> = {}
    if (!datasetId && !name.trim()) errs.name = 'Dataset name is required.'
    if (!domainDescription.trim()) errs.domainDescription = 'Describe the domain so the generator knows what to produce.'
    if (variables.length === 0) errs.variables = 'List at least one variable to generate values for.'
    if (count < 1 || count > 50) errs.count = 'Count must be between 1 and 50.'
    setErrors(errs)
    if (Object.keys(errs).length > 0) return

    setSubmitting(true)
    startFakeProgress()
    try {
      const res = await api.generateDataset({
        dataset_id: datasetId,
        name: datasetId ? undefined : name.trim(),
        domain_description: domainDescription.trim(),
        variables,
        count,
        mode,
      })
      stopFakeProgress(100)
      setResult(res)
      onGenerated(res)
      toast.success(`Generated ${res.cases.length} cases`, res.dataset.name)
    } catch (e) {
      stopFakeProgress(0)
      const message = e instanceof ApiError ? e.message : 'Generation failed or timed out — your inputs are still here, try again.'
      toast.error('Generation failed', message)
      setErrors({ submit: message })
    } finally {
      setSubmitting(false)
    }
  }

  const categoryCounts = result
    ? result.cases.reduce<Record<string, number>>((acc, c) => {
        const cat = c.category ?? 'standard'
        acc[cat] = (acc[cat] ?? 0) + 1
        return acc
      }, {})
    : null

  return (
    <Dialog
      open={open}
      onClose={submitting ? () => {} : onClose}
      title="Generate dataset"
      description="Synchronous — larger counts and adversarial mode can take up to a minute."
      size="lg"
      footer={
        result ? (
          <Button variant="primary" onClick={onClose}>
            Done
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button variant="primary" onClick={submit} loading={submitting}>
              Generate
            </Button>
          </>
        )
      }
    >
      {result && categoryCounts ? (
        <div className="flex flex-col gap-4">
          <p className="text-[13px] text-[var(--text-secondary)]">
            Added {result.cases.length} case{result.cases.length === 1 ? '' : 's'} to{' '}
            <span className="font-medium text-[var(--text-primary)]">{result.dataset.name}</span>.
          </p>
          <div className="flex flex-col gap-1.5">
            <h4 className="text-[12px] font-medium text-[var(--text-tertiary)]">Category distribution</h4>
            <div className="flex flex-col gap-2">
              {Object.entries(categoryCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([cat, n]) => {
                  const pct = (n / result.cases.length) * 100
                  return (
                    <div key={cat} className="flex items-center gap-3">
                      <div className="w-36 shrink-0">
                        <CategoryBadge category={cat} />
                      </div>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-3)]">
                        <div className="h-full rounded-full bg-[var(--accent-9)]" style={{ width: `${pct}%`, opacity: 0.85 }} />
                      </div>
                      <span className="w-16 shrink-0 text-right font-mono text-[12px] tabular-nums text-[var(--text-secondary)]">
                        {n} ({pct.toFixed(0)}%)
                      </span>
                    </div>
                  )
                })}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3.5">
          {!datasetId && (
            <Input label="Dataset name" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} disabled={submitting} />
          )}
          <Textarea
            label="Domain description"
            value={domainDescription}
            onChange={(e) => setDomainDescription(e.target.value)}
            hint="What does the prompt do, and what do realistic inputs look like?"
            error={errors.domainDescription}
            minRows={3}
            disabled={submitting}
          />
          <div className="flex flex-col gap-1.5">
            <label className="text-[13px] font-medium text-[var(--text-secondary)]">Variables to generate</label>
            <TagInput values={variables} onChange={setVariables} placeholder="e.g. ticket_text — press Enter" />
            {errors.variables && <span className="text-[12px] text-[var(--danger-10)]">{errors.variables}</span>}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Count"
              type="number"
              min={1}
              max={50}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              error={errors.count}
              mono
              disabled={submitting}
            />
            <Select
              label="Mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as GenerationMode)}
              options={[
                { value: 'standard', label: 'Standard' },
                { value: 'adversarial', label: 'Adversarial' },
                { value: 'mixed', label: 'Mixed' },
              ]}
              disabled={submitting}
            />
          </div>
          <div className="flex items-start gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2.5">
            {mode === 'adversarial' && <Badge variant="danger">Hostile</Badge>}
            <p className="text-[12px] text-[var(--text-secondary)]">{MODE_EXPLANATION[mode]}</p>
          </div>

          {submitting && (
            <div className="flex flex-col gap-1.5">
              <ProgressBar value={progress} />
              <span className="text-[12px] text-[var(--text-tertiary)]">
                Generating {count} case{count === 1 ? '' : 's'}… this can take up to a minute, especially for adversarial mode.
              </span>
            </div>
          )}
          {errors.submit && <span className="text-[12px] text-[var(--danger-10)]">{errors.submit}</span>}
        </div>
      )}
    </Dialog>
  )
}
