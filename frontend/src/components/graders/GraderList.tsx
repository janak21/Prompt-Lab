import { useEffect, useState } from 'react'
import { Badge, Button, Dialog, Drawer, EmptyState, ErrorState, Input, Select, Switch, TableSkeleton, toast } from '@/components/ui'
import { api, ApiError, getFieldError } from '@/lib/api'
import type { ErrorDetail, Grader, GraderType } from '@/lib/types'
import type { AnyGraderConfig } from './GraderConfigFields'
import { GraderConfigFields, defaultConfigFor, validateConfig } from './GraderConfigFields'
import { normalizedContribution } from './weights'

const TYPE_LABEL: Record<GraderType, string> = {
  llm_judge: 'LLM Judge',
  code_syntax: 'Code Syntax',
  string_match: 'String Match',
  json_schema: 'JSON Schema',
  budget: 'Budget',
  tool_calls: 'Tool Calls',
}

/**
 * Maps a 422 from grader create/update onto the same field->message shape
 * `validateConfig` produces, so a server-side rejection (unknown config
 * keys, an always-skip config, an uncompilable regex, an invalid JSON
 * Schema) lands on the same input as a client-side one — quiet and inline,
 * not a banner. Returns {} when the issue doesn't name a field we render
 * (e.g. an unrecognized config key), so the caller falls back to a toast.
 */
function graderConfigFieldErrors(type: GraderType, detail: ErrorDetail): Record<string, string> {
  if (type === 'llm_judge') {
    const msg = getFieldError(detail, 'rubric')
    return msg ? { rubric: msg } : {}
  }
  if (type === 'string_match') {
    const msg = getFieldError(detail, 'regex')
    return msg ? { regex: msg } : {}
  }
  if (type === 'json_schema') {
    const msg = getFieldError(detail, 'schema')
    return msg ? { schema: msg } : {}
  }
  if (type === 'budget') {
    // BudgetFields shows one shared message regardless of which ceiling triggered it.
    const msg =
      getFieldError(detail, 'budget') ??
      getFieldError(detail, 'max_latency_ms') ??
      getFieldError(detail, 'max_cost_usd') ??
      getFieldError(detail, 'max_output_tokens')
    return msg ? { budget: msg } : {}
  }
  return {}
}

export function GraderList({ promptId }: { promptId: number }) {
  const [graders, setGraders] = useState<Grader[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [editing, setEditing] = useState<Grader | null>(null)

  const load = () => {
    setError(null)
    setGraders(null)
    api
      .listGraders(promptId)
      .then((g) => setGraders([...g].sort((a, b) => a.position - b.position)))
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : 'Failed to load graders.'))
  }

  useEffect(load, [promptId])

  const patchGrader = async (id: number, patch: Partial<Grader>, optimistic = true) => {
    const prev = graders
    if (optimistic && graders) {
      setGraders(graders.map((g) => (g.id === id ? { ...g, ...patch } : g)))
    }
    try {
      const updated = await api.updateGrader(id, patch)
      setGraders((cur) => (cur ? cur.map((g) => (g.id === id ? updated : g)) : cur))
    } catch (e) {
      setGraders(prev ?? null)
      toast.error('Couldn’t update grader', e instanceof ApiError ? e.message : 'Unknown error')
    }
  }

  const move = async (id: number, direction: -1 | 1) => {
    if (!graders) return
    const idx = graders.findIndex((g) => g.id === id)
    const swapIdx = idx + direction
    if (idx < 0 || swapIdx < 0 || swapIdx >= graders.length) return
    const a = graders[idx]
    const b = graders[swapIdx]
    const next = [...graders]
    next[idx] = { ...b, position: a.position }
    next[swapIdx] = { ...a, position: b.position }
    next.sort((x, y) => x.position - y.position)
    setGraders(next)
    try {
      await Promise.all([api.updateGrader(a.id, { position: b.position }), api.updateGrader(b.id, { position: a.position })])
    } catch (e) {
      load()
      toast.error('Couldn’t reorder graders', e instanceof ApiError ? e.message : 'Unknown error')
    }
  }

  const remove = async (grader: Grader) => {
    if (!graders) return
    const prev = graders
    setGraders(graders.filter((g) => g.id !== grader.id))
    try {
      await api.deleteGrader(grader.id)
      toast.success('Grader removed', grader.name)
    } catch (e) {
      setGraders(prev)
      toast.error('Couldn’t remove grader', e instanceof ApiError ? e.message : 'Unknown error')
    }
  }

  if (error) return <ErrorState message="Couldn't load graders" detail={error} onRetry={load} />
  if (graders === null) return <TableSkeleton rows={3} cols={5} />

  const contribution = normalizedContribution(graders)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-[13px] text-[var(--text-secondary)]">
          Scores are weighted averages. Gating graders independently decide whether a case passes.
        </p>
        <Button variant="primary" onClick={() => setAddOpen(true)}>
          Add grader
        </Button>
      </div>

      {graders.length === 0 ? (
        <EmptyState
          title="No graders configured"
          description="Add at least one grader so runs against this prompt produce a score."
          action={
            <Button variant="primary" onClick={() => setAddOpen(true)}>
              Add grader
            </Button>
          }
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {graders.map((g, i) => (
            <li
              key={g.id}
              className="flex items-center gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2.5"
            >
              <div className="flex flex-col gap-0.5">
                <button
                  type="button"
                  disabled={i === 0}
                  onClick={() => move(g.id, -1)}
                  aria-label="Move up"
                  className="flex h-4 w-4 items-center justify-center text-[var(--text-tertiary)] hover:text-[var(--text-primary)] disabled:opacity-30 disabled:pointer-events-none"
                >
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path d="M2 6l3-3 3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                <button
                  type="button"
                  disabled={i === graders.length - 1}
                  onClick={() => move(g.id, 1)}
                  aria-label="Move down"
                  className="flex h-4 w-4 items-center justify-center text-[var(--text-tertiary)] hover:text-[var(--text-primary)] disabled:opacity-30 disabled:pointer-events-none"
                >
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </div>

              <Switch checked={g.enabled} onChange={(v) => patchGrader(g.id, { enabled: v })} />

              <div className="flex min-w-0 flex-1 items-center gap-2">
                <span className="truncate text-[13px] font-medium text-[var(--text-primary)]">{g.name}</span>
                <Badge variant="neutral">{TYPE_LABEL[g.type]}</Badge>
                {g.gating && <Badge variant="neutral">Gate</Badge>}
              </div>

              <div className="flex items-center gap-2">
                <Input
                  aria-label="Weight"
                  type="number"
                  min={0}
                  step={0.5}
                  value={g.weight}
                  onChange={(e) => patchGrader(g.id, { weight: Number(e.target.value) })}
                  className="!h-7 w-16"
                  mono
                />
                <span
                  className="w-12 shrink-0 text-right font-mono text-[12px] tabular-nums text-[var(--text-tertiary)]"
                  title="Normalized contribution to the final score"
                >
                  {g.enabled ? `${contribution[g.id].toFixed(0)}%` : '—'}
                </span>
              </div>

              <Button size="sm" variant="outline" onClick={() => setEditing(g)}>
                Configure
              </Button>
              <Button size="sm" variant="ghost" onClick={() => remove(g)} aria-label={`Remove ${g.name}`}>
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
            </li>
          ))}
        </ul>
      )}

      <AddGraderDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        promptId={promptId}
        onCreated={(g) => {
          setGraders((cur) => (cur ? [...cur, g] : [g]))
          setAddOpen(false)
        }}
      />

      <EditGraderDrawer
        grader={editing}
        onClose={() => setEditing(null)}
        onSaved={(g) => {
          setGraders((cur) => (cur ? cur.map((x) => (x.id === g.id ? g : x)) : cur))
          setEditing(null)
        }}
      />
    </div>
  )
}

function AddGraderDialog({
  open,
  onClose,
  promptId,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  promptId: number
  onCreated: (g: Grader) => void
}) {
  const [type, setType] = useState<GraderType>('llm_judge')
  const [gating, setGating] = useState(false)
  const [passThreshold, setPassThreshold] = useState(8)
  const [name, setName] = useState('LLM Judge')
  const [weight, setWeight] = useState(1)
  const [config, setConfig] = useState<AnyGraderConfig>(defaultConfigFor('llm_judge'))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    setType('llm_judge')
    setName('LLM Judge')
    setWeight(1)
    setGating(false)
    setPassThreshold(8)
    setConfig(defaultConfigFor('llm_judge'))
    setErrors({})
  }, [open])

  const changeType = (t: GraderType) => {
    setType(t)
    setConfig(defaultConfigFor(t))
    setName(TYPE_LABEL[t])
    setErrors({})
  }

  const submit = async () => {
    const errs = validateConfig(type, config)
    setErrors(errs)
    if (Object.keys(errs).length > 0) return
    setSubmitting(true)
    try {
      const grader = await api.createGrader(promptId, { type, name: name.trim() || TYPE_LABEL[type], weight, config, gating, pass_threshold: passThreshold })
      toast.success('Grader added', grader.name)
      onCreated(grader)
    } catch (e) {
      if (e instanceof ApiError) {
        const fieldErrors = graderConfigFieldErrors(type, e.detail)
        if (Object.keys(fieldErrors).length > 0) {
          setErrors((cur) => ({ ...cur, ...fieldErrors }))
        } else {
          toast.error('Couldn’t add grader', e.message)
        }
      } else {
        toast.error('Couldn’t add grader', 'Unknown error')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add grader"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={submitting}>
            Add grader
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3.5">
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Type"
            value={type}
            onChange={(e) => changeType(e.target.value as GraderType)}
            options={Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label }))}
          />
          <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <Input label="Weight" type="number" min={0} step={0.5} value={weight} onChange={(e) => setWeight(Number(e.target.value))} mono />
        <Switch label="Gating — require this grader to pass" checked={gating} onChange={setGating} />
        {gating && type === 'llm_judge' && <Input label="Pass threshold (0–10)" type="number" min={0} max={10} step={0.1} value={passThreshold} onChange={(e) => setPassThreshold(Number(e.target.value))} mono />}
        <GraderConfigFields type={type} config={config} onChange={setConfig} errors={errors} />
      </div>
    </Dialog>
  )
}

function EditGraderDrawer({
  grader,
  onClose,
  onSaved,
}: {
  grader: Grader | null
  onClose: () => void
  onSaved: (g: Grader) => void
}) {
  const [config, setConfig] = useState<AnyGraderConfig>(defaultConfigFor('llm_judge'))
  const [gating, setGating] = useState(false)
  const [passThreshold, setPassThreshold] = useState(8)
  const [name, setName] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (grader) {
      setConfig(grader.config as AnyGraderConfig)
      setName(grader.name)
      setGating(grader.gating ?? false)
      setPassThreshold(grader.pass_threshold ?? 8)
      setErrors({})
    }
  }, [grader])

  if (!grader) return null

  const submit = async () => {
    const errs = validateConfig(grader.type, config)
    setErrors(errs)
    if (Object.keys(errs).length > 0) return
    setSubmitting(true)
    try {
      const updated = await api.updateGrader(grader.id, { name: name.trim() || grader.name, config, gating, pass_threshold: passThreshold })
      toast.success('Grader updated', updated.name)
      onSaved(updated)
    } catch (e) {
      if (e instanceof ApiError) {
        const fieldErrors = graderConfigFieldErrors(grader.type, e.detail)
        if (Object.keys(fieldErrors).length > 0) {
          setErrors((cur) => ({ ...cur, ...fieldErrors }))
        } else {
          toast.error('Couldn’t save grader', e.message)
        }
      } else {
        toast.error('Couldn’t save grader', 'Unknown error')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Drawer
      open={!!grader}
      onClose={onClose}
      title={`Configure — ${TYPE_LABEL[grader.type]}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={submitting}>
            Save
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3.5">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <Switch label="Gating — require this grader to pass" checked={gating} onChange={setGating} />
        {gating && grader.type === 'llm_judge' && <Input label="Pass threshold (0–10)" type="number" min={0} max={10} step={0.1} value={passThreshold} onChange={(e) => setPassThreshold(Number(e.target.value))} mono />}
        <GraderConfigFields type={grader.type} config={config} onChange={setConfig} errors={errors} />
      </div>
    </Drawer>
  )
}
