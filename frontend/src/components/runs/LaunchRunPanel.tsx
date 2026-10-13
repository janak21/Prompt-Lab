import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Input, Select, Slider, toast } from '@/components/ui'
import { useSubmitShortcut } from '@/hooks/useEscapeKey'
import { effectiveRunModel } from '@/lib/modelSelection'
import { api, ApiError, getFieldError } from '@/lib/api'
import type { Dataset, Grader, ModelInfo, Prompt, PromptVersion } from '@/lib/types'

export const DEFAULT_CONCURRENCY = 4

function normalizedWeights(graders: Grader[]): Array<Grader & { pct: number }> {
  const enabled = graders.filter((g) => g.enabled)
  const total = enabled.reduce((a, g) => a + g.weight, 0)
  return enabled.map((g) => ({ ...g, pct: total > 0 ? Math.round((g.weight / total) * 1000) / 10 : 0 }))
}

export function LaunchRunPanel({
  prompts,
  datasets,
  models,
  defaultModel,
  defaultJudgeModel,
  onLaunched,
}: {
  prompts: Prompt[]
  datasets: Dataset[]
  models: ModelInfo[]
  defaultModel: string
  defaultJudgeModel: string
  onLaunched: (runId: number) => void
}) {
  const navigate = useNavigate()
  const [promptId, setPromptId] = useState<number | ''>('')
  const [versions, setVersions] = useState<PromptVersion[] | null>(null)
  const [graders, setGraders] = useState<Grader[] | null>(null)
  const [versionId, setVersionId] = useState<number | ''>('')
  const [datasetId, setDatasetId] = useState<number | ''>('')
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState(0.2)
  const [maxTokens, setMaxTokens] = useState(1024)
  const [judgeModel, setJudgeModel] = useState('')
  const [concurrency, setConcurrency] = useState(DEFAULT_CONCURRENCY)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [datasetError, setDatasetError] = useState<string | undefined>(undefined)

  useEffect(() => {
    if (!promptId) {
      setVersions(null)
      setGraders(null)
      return
    }
    setVersions(null)
    setGraders(null)
    api.getPrompt(Number(promptId)).then((res) => {
      const sorted = [...res.versions].sort((a, b) => b.version_no - a.version_no)
      setVersions(sorted)
      setVersionId(sorted[0]?.id ?? '')
      setGraders(res.graders)
    })
  }, [promptId])

  const selectedVersion = versions?.find((v) => v.id === versionId) ?? null
  const selectedDataset = datasets.find((d) => d.id === datasetId) ?? null
  const resolvedModel = effectiveRunModel(model, selectedVersion?.model, defaultModel, models)

  const missingVariables = useMemo(() => {
    if (!selectedVersion || !selectedDataset) return []
    return selectedVersion.variables.filter((v) => !selectedDataset.variables.includes(v))
  }, [selectedVersion, selectedDataset])

  const canSubmit = models.length > 0 && !!promptId && !!versionId && !!datasetId && missingVariables.length === 0 && !submitting

  const submit = async () => {
    if (!canSubmit || !versionId || !datasetId) return
    setSubmitting(true)
    setSubmitError(null)
    setDatasetError(undefined)
    try {
      const res = await api.createRun({
        prompt_version_id: Number(versionId),
        dataset_id: Number(datasetId),
        model: resolvedModel || undefined,
        temperature,
        max_tokens: maxTokens,
        judge_model: judgeModel || defaultJudgeModel || undefined,
        concurrency,
      })
      toast.success('Run launched', `Run #${res.run_id} is starting.`)
      onLaunched(res.run_id)
      navigate(`/runs/${res.run_id}`)
    } catch (e) {
      const fieldError = e instanceof ApiError ? getFieldError(e.detail, 'dataset_id') : undefined
      setDatasetError(fieldError)
      const message = e instanceof ApiError ? e.message : 'Unknown error'
      // The dataset field already shows the specific issue inline — avoid repeating it in the banner/toast.
      setSubmitError(fieldError ? null : message)
      toast.error('Couldn’t launch run', message)
    } finally {
      setSubmitting(false)
    }
  }

  useSubmitShortcut(true, submit)

  const weighted = graders ? normalizedWeights(graders) : []

  return (
    <div className="flex w-[360px] shrink-0 flex-col gap-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4">
      <div>
        <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">Launch a run</h2>
        <p className="text-[12px] text-[var(--text-tertiary)]">⌘⏎ to submit</p>
      </div>

      <Select
        label="Prompt"
        options={prompts.map((p) => ({ value: String(p.id), label: p.name }))}
        placeholder="Select a prompt"
        value={promptId === '' ? '' : String(promptId)}
        onChange={(e) => setPromptId(e.target.value ? Number(e.target.value) : '')}
      />

      <Select
        label="Version"
        options={(versions ?? []).map((v) => ({ value: String(v.id), label: `v${v.version_no}${v.notes ? ` — ${v.notes}` : ''}` }))}
        placeholder={promptId ? (versions ? 'Select a version' : 'Loading…') : 'Select a prompt first'}
        value={versionId === '' ? '' : String(versionId)}
        onChange={(e) => setVersionId(e.target.value ? Number(e.target.value) : '')}
        disabled={!versions}
      />

      <Select
        label="Dataset"
        options={datasets.map((d) => ({ value: String(d.id), label: `${d.name} (${d.case_count} cases)` }))}
        placeholder="Select a dataset"
        value={datasetId === '' ? '' : String(datasetId)}
        onChange={(e) => {
          setDatasetId(e.target.value ? Number(e.target.value) : '')
          setDatasetError(undefined)
        }}
        error={datasetError}
      />

      {selectedVersion && selectedDataset && (
        <div
          className={
            missingVariables.length
              ? 'rounded-md border border-[var(--danger-9)]/40 bg-[var(--score-low-bg)] px-3 py-2 text-[12px] text-[var(--score-low)]'
              : 'rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-[12px] text-[var(--text-secondary)]'
          }
        >
          {missingVariables.length ? (
            <>
              <span className="font-medium">Dataset can't satisfy this template.</span> Missing variable
              {missingVariables.length > 1 ? 's' : ''}:{' '}
              {missingVariables.map((v) => (
                <code key={v} className="font-mono">
                  {'{{' + v + '}}'}
                </code>
              ))}
            </>
          ) : (
            <>Variable check passed — dataset provides {selectedVersion.variables.join(', ') || 'no variables'}.</>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Select
          label="Model"
          options={models.map((m) => ({ value: m.id, label: m.label }))}
          placeholder={resolvedModel ? 'Effective (' + resolvedModel + ')' : 'Configure a key in Settings'}
          value={model}
          onChange={(e) => setModel(e.target.value)}
        />
        <Select
          label="Judge model"
          options={models.map((m) => ({ value: m.id, label: m.label }))}
          placeholder={`Default (${defaultJudgeModel})`}
          value={judgeModel}
          onChange={(e) => setJudgeModel(e.target.value)}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Slider disabled={!models.find((m) => m.id === resolvedModel)?.supports_temperature} label="Temperature" value={temperature} onChange={setTemperature} min={0} max={1} step={0.05} formatValue={(v) => v.toFixed(2)} />
        <Input label="Max tokens" type="number" min={1} mono value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value))} />
      </div>

      <p className="text-[12px] text-[var(--text-tertiary)]">Run and judge models can use different providers. Temperature is omitted unless supported by the selected model.</p>
      <Input
        label="Concurrency"
        type="number"
        min={1}
        max={20}
        mono
        value={concurrency}
        onChange={(e) => setConcurrency(Number(e.target.value))}
        hint="Parallel case executions"
      />

      {graders && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium text-[var(--text-secondary)]">Graders that will run</span>
          {weighted.length === 0 ? (
            <span className="text-[12px] text-[var(--text-tertiary)]">No enabled graders on this prompt.</span>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {weighted.map((g) => (
                <Badge key={g.id} variant="neutral">
                  {g.name} <span className="font-mono opacity-70">{g.pct}%</span>
                </Badge>
              ))}
            </div>
          )}
        </div>
      )}

      {submitError && <p className="text-[12px] text-[var(--score-low)]">{submitError}</p>}

      <Button variant="primary" loading={submitting} disabled={!canSubmit} onClick={submit}>
        Launch run
      </Button>
    </div>
  )
}
