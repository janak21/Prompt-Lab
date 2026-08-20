import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  Select,
  Slider,
  Table,
  Textarea,
  TableSkeleton,
  toast,
} from '@/components/ui'
import type { Column } from '@/components/ui'
import { VariableTemplateEditor, extractTemplateVariables } from '@/components/prompts/VariableTemplateEditor'
import { api, ApiError } from '@/lib/api'
import { formatDate } from '@/lib/format'
import type { ModelInfo, Prompt } from '@/lib/types'

export function PromptsPage() {
  const navigate = useNavigate()
  const [prompts, setPrompts] = useState<Prompt[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)

  const load = () => {
    setError(null)
    setPrompts(null)
    api
      .listPrompts()
      .then(setPrompts)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : 'Failed to load prompts.'))
  }

  useEffect(load, [])

  const columns: Column<Prompt>[] = [
    {
      key: 'name',
      header: 'Name',
      sortValue: (p) => p.name,
      render: (p) => <span className="font-medium text-[var(--text-primary)]">{p.name}</span>,
    },
    {
      key: 'description',
      header: 'Description',
      render: (p) => (
        <span className="line-clamp-1 text-[var(--text-secondary)]">{p.description || '—'}</span>
      ),
    },
    {
      key: 'version_count',
      header: 'Versions',
      align: 'right',
      mono: true,
      sortValue: (p) => p.version_count,
      render: (p) => `${p.version_count} (v${p.latest_version_no} latest)`,
    },
    {
      key: 'updated_at',
      header: 'Updated',
      align: 'right',
      mono: true,
      sortValue: (p) => p.updated_at,
      render: (p) => formatDate(p.updated_at),
    },
  ]

  return (
    <div className="flex flex-col gap-5 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[17px] font-semibold text-[var(--text-primary)]">Prompts</h1>
          <p className="text-[13px] text-[var(--text-secondary)]">Templates, versions, and graders.</p>
        </div>
        {prompts && prompts.length > 0 && (
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            New prompt
          </Button>
        )}
      </div>

      {error ? (
        <ErrorState message="Couldn't load prompts" detail={error} onRetry={load} />
      ) : prompts === null ? (
        <TableSkeleton rows={5} cols={4} />
      ) : prompts.length === 0 ? (
        <EmptyState
          title="No prompts yet"
          description="Create a prompt template to start iterating and evaluating it against a dataset."
          action={
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              New prompt
            </Button>
          }
        />
      ) : (
        <Table
          columns={columns}
          rows={prompts}
          rowKey={(p) => p.id}
          onRowClick={(p) => navigate(`/prompts/${p.id}`)}
          initialSort={{ key: 'updated_at', direction: 'desc' }}
        />
      )}

      <CreatePromptDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(prompt) => {
          setCreateOpen(false)
          navigate(`/prompts/${prompt.id}`)
        }}
      />
    </div>
  )
}

function CreatePromptDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (prompt: Prompt) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [template, setTemplate] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState(0.2)
  const [maxTokens, setMaxTokens] = useState(1024)
  const [models, setModels] = useState<ModelInfo[] | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [nameError, setNameError] = useState<string | null>(null)
  const [templateError, setTemplateError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    api.getModels().then((r) => {
      setModels(r.models)
      setModel((m) => m || r.default_model)
    })
  }, [open])

  useEffect(() => {
    if (!open) {
      setName('')
      setDescription('')
      setTemplate('')
      setSystemPrompt('')
      setTemperature(0.2)
      setMaxTokens(1024)
      setNameError(null)
      setTemplateError(null)
    }
  }, [open])

  const variables = extractTemplateVariables(template)

  const submit = async () => {
    let hasError = false
    if (!name.trim()) {
      setNameError('Name is required.')
      hasError = true
    } else setNameError(null)
    if (!template.trim()) {
      setTemplateError('Template is required.')
      hasError = true
    } else setTemplateError(null)
    if (hasError) return

    setSubmitting(true)
    try {
      const res = await api.createPrompt({
        name: name.trim(),
        description: description.trim() || undefined,
        template,
        system_prompt: systemPrompt.trim() || undefined,
        model: model || undefined,
        temperature,
        max_tokens: maxTokens,
      })
      toast.success('Prompt created', `v1 saved for "${res.prompt.name}"`)
      onCreated(res.prompt)
    } catch (e) {
      toast.error('Couldn’t create prompt', e instanceof ApiError ? e.message : 'Unknown error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New prompt"
      description="Creates the prompt and its first version (v1)."
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={submitting}>
            Create prompt
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3.5">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} error={nameError ?? undefined} autoFocus />
        <Input
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          hint="Optional — what this prompt is for."
        />
        <div className="flex flex-col gap-1.5">
          <label className="text-[13px] font-medium text-[var(--text-secondary)]">Template</label>
          <VariableTemplateEditor value={template} onChange={setTemplate} minRows={7} placeholder="You are a helpful assistant. {{input}}" />
          {templateError && <span className="text-[12px] text-[var(--danger-10)]">{templateError}</span>}
          {variables.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
              <span className="text-[11px] text-[var(--text-tertiary)]">Detected:</span>
              {variables.map((v) => (
                <Badge key={v} variant="accent">
                  {'{{' + v + '}}'}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <Textarea
          label="System prompt"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          hint="Optional"
          minRows={2}
          mono
        />
        <div className="grid grid-cols-3 gap-3">
          <Select
            label="Model"
            options={(models ?? []).map((m) => ({ value: m.id, label: m.label }))}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={models ? undefined : 'Loading…'}
            disabled={!models}
          />
          <Slider label="Temperature" value={temperature} onChange={setTemperature} min={0} max={1} step={0.05} formatValue={(v) => v.toFixed(2)} />
          <Input
            label="Max tokens"
            type="number"
            min={1}
            value={maxTokens}
            onChange={(e) => setMaxTokens(Number(e.target.value))}
            mono
          />
        </div>
      </div>
    </Dialog>
  )
}
