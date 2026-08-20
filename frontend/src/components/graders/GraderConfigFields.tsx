import { useEffect, useState } from 'react'
import { Input, Select, Switch, Textarea } from '@/components/ui'
import type { ModelInfo } from '@/lib/types'
import type {
  GraderConfigBudget,
  GraderConfigCodeSyntax,
  GraderConfigJsonSchema,
  GraderConfigLlmJudge,
  GraderConfigStringMatch,
  GraderType,
} from '@/lib/types'
import { api } from '@/lib/api'

export type AnyGraderConfig =
  | GraderConfigLlmJudge
  | GraderConfigCodeSyntax
  | GraderConfigStringMatch
  | GraderConfigJsonSchema
  | GraderConfigBudget

export function defaultConfigFor(type: GraderType): AnyGraderConfig {
  switch (type) {
    case 'llm_judge':
      return { rubric: '', use_solution_criteria: true }
    case 'code_syntax':
      return { format: 'auto' }
    case 'string_match':
      return { must_contain: [], must_not_contain: [], regex: null, case_sensitive: false }
    case 'json_schema':
      return { schema: {} }
    case 'budget':
      return {}
  }
}

/** Validates a config client-side; returns a field->message map (empty = valid). */
export function validateConfig(type: GraderType, config: AnyGraderConfig): Record<string, string> {
  const errors: Record<string, string> = {}
  if (type === 'llm_judge') {
    const c = config as GraderConfigLlmJudge
    if (!c.rubric?.trim()) errors.rubric = 'Rubric is required.'
  }
  if (type === 'string_match') {
    const c = config as GraderConfigStringMatch
    if (c.regex) {
      try {
        new RegExp(c.regex)
      } catch (e) {
        errors.regex = e instanceof Error ? e.message : 'Invalid regular expression.'
      }
    }
  }
  if (type === 'json_schema') {
    const c = config as GraderConfigJsonSchema
    if (!c.schema || typeof c.schema !== 'object' || Object.keys(c.schema).length === 0) {
      errors.schema = 'Provide a non-empty JSON Schema object.'
    }
  }
  if (type === 'budget') {
    const c = config as GraderConfigBudget
    if (c.max_latency_ms == null && c.max_cost_usd == null && c.max_output_tokens == null) {
      errors.budget = 'Set at least one ceiling, or this grader always scores 10.'
    }
  }
  return errors
}

export function GraderConfigFields({
  type,
  config,
  onChange,
  errors = {},
}: {
  type: GraderType
  config: AnyGraderConfig
  onChange: (config: AnyGraderConfig) => void
  errors?: Record<string, string>
}) {
  if (type === 'llm_judge') return <LlmJudgeFields config={config as GraderConfigLlmJudge} onChange={onChange} errors={errors} />
  if (type === 'code_syntax') return <CodeSyntaxFields config={config as GraderConfigCodeSyntax} onChange={onChange} />
  if (type === 'string_match') return <StringMatchFields config={config as GraderConfigStringMatch} onChange={onChange} errors={errors} />
  if (type === 'json_schema') return <JsonSchemaFields config={config as GraderConfigJsonSchema} onChange={onChange} errors={errors} />
  return <BudgetFields config={config as GraderConfigBudget} onChange={onChange} errors={errors} />
}

function LlmJudgeFields({
  config,
  onChange,
  errors,
}: {
  config: GraderConfigLlmJudge
  onChange: (c: GraderConfigLlmJudge) => void
  errors: Record<string, string>
}) {
  const [models, setModels] = useState<ModelInfo[] | null>(null)
  useEffect(() => {
    api.getModels().then((r) => setModels(r.models))
  }, [])
  return (
    <div className="flex flex-col gap-3">
      <Textarea
        label="Rubric"
        value={config.rubric}
        onChange={(e) => onChange({ ...config, rubric: e.target.value })}
        hint="What should the judge model look for? Be specific — this is the grading instruction."
        error={errors.rubric}
        minRows={4}
      />
      <Switch
        checked={config.use_solution_criteria}
        onChange={(v) => onChange({ ...config, use_solution_criteria: v })}
        label="Include each case's solution_criteria in the judge prompt"
      />
      <Select
        label="Judge model"
        options={(models ?? []).map((m) => ({ value: m.id, label: m.label }))}
        value={config.judge_model ?? ''}
        onChange={(e) => onChange({ ...config, judge_model: e.target.value || undefined })}
        placeholder={models ? 'Use run default' : 'Loading…'}
        disabled={!models}
      />
    </div>
  )
}

function CodeSyntaxFields({ config, onChange }: { config: GraderConfigCodeSyntax; onChange: (c: GraderConfigCodeSyntax) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Select
        label="Format"
        value={config.format}
        onChange={(e) => onChange({ format: e.target.value as GraderConfigCodeSyntax['format'] })}
        options={[
          { value: 'auto', label: 'Auto (per-case)' },
          { value: 'json', label: 'JSON' },
          { value: 'python', label: 'Python' },
          { value: 'regex', label: 'Regex' },
        ]}
      />
      <p className="text-[12px] text-[var(--text-tertiary)]">
        {config.format === 'auto'
          ? 'Auto reads each test case’s own expected_format and validates the output against that, case by case.'
          : `Every case's output is validated as ${config.format}, regardless of its own expected_format.`}
      </p>
    </div>
  )
}

function TagListEditor({ label, values, onChange }: { label: string; values: string[]; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const v = draft.trim()
    if (!v) return
    onChange([...values, v])
    setDraft('')
  }
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[13px] font-medium text-[var(--text-secondary)]">{label}</label>
      <div className="flex gap-1.5">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          placeholder="Add a string, press Enter"
          mono
        />
      </div>
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {values.map((v, i) => (
            <span
              key={`${v}-${i}`}
              className="inline-flex items-center gap-1 rounded-md border border-[var(--border-default)] bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-[12px] text-[var(--text-secondary)]"
            >
              {v}
              <button
                type="button"
                aria-label={`Remove ${v}`}
                onClick={() => onChange(values.filter((_, idx) => idx !== i))}
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

function StringMatchFields({
  config,
  onChange,
  errors,
}: {
  config: GraderConfigStringMatch
  onChange: (c: GraderConfigStringMatch) => void
  errors: Record<string, string>
}) {
  return (
    <div className="flex flex-col gap-3">
      <TagListEditor label="Must contain" values={config.must_contain} onChange={(v) => onChange({ ...config, must_contain: v })} />
      <TagListEditor
        label="Must not contain"
        values={config.must_not_contain}
        onChange={(v) => onChange({ ...config, must_not_contain: v })}
      />
      <Input
        label="Regex (optional)"
        value={config.regex ?? ''}
        onChange={(e) => onChange({ ...config, regex: e.target.value || null })}
        error={errors.regex}
        hint="Validated in-browser as you type."
        mono
      />
      <Switch
        checked={config.case_sensitive}
        onChange={(v) => onChange({ ...config, case_sensitive: v })}
        label="Case sensitive"
      />
    </div>
  )
}

function JsonSchemaFields({
  config,
  onChange,
  errors,
}: {
  config: GraderConfigJsonSchema
  onChange: (c: GraderConfigJsonSchema) => void
  errors: Record<string, string>
}) {
  const [text, setText] = useState(() => JSON.stringify(config.schema, null, 2))
  const [parseError, setParseError] = useState<string | null>(null)

  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[13px] font-medium text-[var(--text-secondary)]">JSON Schema</label>
      <Textarea
        value={text}
        mono
        minRows={8}
        onChange={(e) => {
          const v = e.target.value
          setText(v)
          try {
            const parsed = JSON.parse(v)
            setParseError(null)
            onChange({ schema: parsed })
          } catch (err) {
            setParseError(err instanceof Error ? err.message : 'Invalid JSON')
          }
        }}
      />
      {parseError ? (
        <span className="text-[12px] text-[var(--danger-10)]">{parseError}</span>
      ) : errors.schema ? (
        <span className="text-[12px] text-[var(--danger-10)]">{errors.schema}</span>
      ) : (
        <span className="text-[12px] text-[var(--score-high)]">Valid JSON</span>
      )}
    </div>
  )
}

function BudgetFields({
  config,
  onChange,
  errors,
}: {
  config: GraderConfigBudget
  onChange: (c: GraderConfigBudget) => void
  errors: Record<string, string>
}) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[12px] text-[var(--text-tertiary)]">
        Unset ceilings are ignored. Scores 10 if every ceiling you set holds, else 0.
      </p>
      <Input
        label="Max latency (ms)"
        type="number"
        min={0}
        value={config.max_latency_ms ?? ''}
        onChange={(e) => onChange({ ...config, max_latency_ms: e.target.value === '' ? undefined : Number(e.target.value) })}
        mono
      />
      <Input
        label="Max cost (USD)"
        type="number"
        min={0}
        step={0.001}
        value={config.max_cost_usd ?? ''}
        onChange={(e) => onChange({ ...config, max_cost_usd: e.target.value === '' ? undefined : Number(e.target.value) })}
        mono
      />
      <Input
        label="Max output tokens"
        type="number"
        min={0}
        value={config.max_output_tokens ?? ''}
        onChange={(e) => onChange({ ...config, max_output_tokens: e.target.value === '' ? undefined : Number(e.target.value) })}
        mono
      />
      {errors.budget && <span className="text-[12px] text-[var(--danger-10)]">{errors.budget}</span>}
    </div>
  )
}
