import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Badge,
  Button,
  Dialog,
  ErrorState,
  Input,
  Select,
  Skeleton,
  Slider,
  Tabs,
  Textarea,
  toast,
} from '@/components/ui'
import { GraderList } from '@/components/graders/GraderList'
import { VariableTemplateEditor, extractTemplateVariables } from '@/components/prompts/VariableTemplateEditor'
import { VersionDetailDrawer, VersionHistoryRail } from '@/components/prompts/VersionHistory'
import { api, ApiError } from '@/lib/api'
import type { ModelInfo, Prompt, PromptVersion } from '@/lib/types'

interface Draft {
  template: string
  system_prompt: string
  model: string
  temperature: number
  max_tokens: number
}

function draftFromVersion(v: PromptVersion): Draft {
  return {
    template: v.template,
    system_prompt: v.system_prompt ?? '',
    model: v.model ?? '',
    temperature: v.temperature ?? 0.2,
    max_tokens: v.max_tokens ?? 1024,
  }
}

function draftEquals(a: Draft, b: Draft): boolean {
  return (
    a.template === b.template &&
    a.system_prompt === b.system_prompt &&
    a.model === b.model &&
    a.temperature === b.temperature &&
    a.max_tokens === b.max_tokens
  )
}

export function PromptDetailPage() {
  const { id } = useParams<{ id: string }>()
  const promptId = Number(id)
  const navigate = useNavigate()

  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const [versions, setVersions] = useState<PromptVersion[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [models, setModels] = useState<ModelInfo[] | null>(null)
  const [tab, setTab] = useState('editor')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [previewVersion, setPreviewVersion] = useState<PromptVersion | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)

  const load = () => {
    setError(null)
    setPrompt(null)
    setVersions(null)
    api
      .getPrompt(promptId)
      .then((res) => {
        setPrompt(res.prompt)
        const sorted = [...res.versions].sort((a, b) => b.version_no - a.version_no)
        setVersions(sorted)
        const latest = sorted[0]
        if (latest) setDraft(draftFromVersion(latest))
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : 'Failed to load prompt.'))
  }

  useEffect(load, [promptId])
  useEffect(() => {
    api.getModels().then((r) => setModels(r.models))
  }, [])

  const latest = versions?.[0] ?? null
  const variables = useMemo(() => (draft ? extractTemplateVariables(draft.template) : []), [draft])
  const isDirty = draft && latest ? !draftEquals(draft, draftFromVersion(latest)) : false

  if (error) return <ErrorState className="m-6" message="Couldn't load prompt" detail={error} onRetry={load} />

  if (!prompt || !versions || !draft) {
    return (
      <div className="flex flex-col gap-5 p-6">
        <Skeleton className="h-6 w-64" />
        <div className="flex gap-6">
          <Skeleton className="h-96 flex-1" />
          <Skeleton className="h-96 w-64" />
        </div>
      </div>
    )
  }

  const previousOfPreview = previewVersion
    ? versions.find((v) => v.version_no === previewVersion.version_no - 1) ?? null
    : null

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate('/prompts')}
              className="text-[13px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            >
              Prompts
            </button>
            <span className="text-[13px] text-[var(--text-tertiary)]">/</span>
            <h1 className="text-[17px] font-semibold text-[var(--text-primary)]">{prompt.name}</h1>
            <Badge variant="accent">v{latest?.version_no ?? 1} current</Badge>
            <Button size="sm" variant="ghost" onClick={() => setRenameOpen(true)}>
              Edit
            </Button>
          </div>
          {prompt.description && <p className="text-[13px] text-[var(--text-secondary)]">{prompt.description}</p>}
        </div>
      </div>

      <Tabs
        tabs={[
          { id: 'editor', label: 'Editor' },
          { id: 'graders', label: 'Graders' },
        ]}
        value={tab}
        onChange={setTab}
      />

      {tab === 'editor' ? (
        <div className="flex gap-6">
          <div className="flex min-w-0 flex-1 flex-col gap-3.5">
            <Textarea
              label="System prompt"
              value={draft.system_prompt}
              onChange={(e) => setDraft({ ...draft, system_prompt: e.target.value })}
              hint="Optional"
              minRows={2}
              mono
            />
            <div className="flex flex-col gap-1.5">
              <label className="text-[13px] font-medium text-[var(--text-secondary)]">Template</label>
              <VariableTemplateEditor value={draft.template} onChange={(v) => setDraft({ ...draft, template: v })} minRows={14} />
              <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                <span className="text-[11px] text-[var(--text-tertiary)]">
                  {variables.length > 0 ? 'Detected variables:' : 'No {{variables}} detected yet.'}
                </span>
                {variables.map((v) => (
                  <Badge key={v} variant="accent">
                    {'{{' + v + '}}'}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <Select
                label="Model"
                options={(models ?? []).map((m) => ({ value: m.id, label: m.label }))}
                value={draft.model}
                onChange={(e) => setDraft({ ...draft, model: e.target.value })}
                placeholder={models ? 'Use run default' : 'Loading…'}
                disabled={!models}
              />
              <Slider
                label="Temperature"
                value={draft.temperature}
                onChange={(v) => setDraft({ ...draft, temperature: v })}
                min={0}
                max={1}
                step={0.05}
                formatValue={(v) => v.toFixed(2)}
              />
              <Input
                label="Max tokens"
                type="number"
                min={1}
                value={draft.max_tokens}
                onChange={(e) => setDraft({ ...draft, max_tokens: Number(e.target.value) })}
                mono
              />
            </div>
            <div className="flex items-center gap-2 pt-1">
              <Button
                variant="primary"
                disabled={!isDirty || !draft.template.trim()}
                onClick={() => setSaveOpen(true)}
              >
                Save as new version
              </Button>
              {isDirty && <span className="text-[12px] text-[var(--text-tertiary)]">Unsaved changes vs v{latest?.version_no}</span>}
            </div>
          </div>

          <div className="w-64 shrink-0">
            <VersionHistoryRail
              versions={versions}
              currentVersionNo={latest?.version_no ?? 1}
              onSelect={setPreviewVersion}
            />
          </div>
        </div>
      ) : (
        <GraderList promptId={promptId} />
      )}

      <VersionDetailDrawer
        open={!!previewVersion}
        onClose={() => setPreviewVersion(null)}
        version={previewVersion}
        previousVersion={previousOfPreview}
        isCurrent={previewVersion?.version_no === latest?.version_no}
        onRestore={(v) => {
          setDraft(draftFromVersion(v))
          toast('Restored into editor', `v${v.version_no}'s content is now in the draft — save it to create a new version.`)
        }}
      />

      <SaveVersionDialog
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        onConfirm={async (notes) => {
          try {
            const version = await api.createPromptVersion(promptId, {
              template: draft.template,
              system_prompt: draft.system_prompt || undefined,
              model: draft.model || undefined,
              temperature: draft.temperature,
              max_tokens: draft.max_tokens,
              notes: notes || undefined,
            })
            setVersions((cur) => (cur ? [version, ...cur] : [version]))
            setPrompt((p) => (p ? { ...p, version_count: p.version_count + 1, latest_version_no: version.version_no } : p))
            setSaveOpen(false)
            toast.success(`Saved v${version.version_no}`, notes || undefined)
          } catch (e) {
            toast.error('Couldn’t save version', e instanceof ApiError ? e.message : 'Unknown error')
          }
        }}
      />

      <RenamePromptDialog
        open={renameOpen}
        onClose={() => setRenameOpen(false)}
        prompt={prompt}
        onSaved={(p) => {
          setPrompt(p)
          setRenameOpen(false)
        }}
      />
    </div>
  )
}

function SaveVersionDialog({
  open,
  onClose,
  onConfirm,
}: {
  open: boolean
  onClose: () => void
  onConfirm: (notes: string) => Promise<void>
}) {
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) setNotes('')
  }, [open])

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Save as new version"
      description="Versions are immutable — this creates the next version number."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={submitting}
            onClick={async () => {
              setSubmitting(true)
              await onConfirm(notes)
              setSubmitting(false)
            }}
          >
            Save version
          </Button>
        </>
      }
    >
      <Textarea
        label="Notes"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        hint="Optional — what changed and why."
        minRows={3}
        autoFocus
      />
    </Dialog>
  )
}

function RenamePromptDialog({
  open,
  onClose,
  prompt,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  prompt: Prompt
  onSaved: (p: Prompt) => void
}) {
  const [name, setName] = useState(prompt.name)
  const [description, setDescription] = useState(prompt.description ?? '')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open) {
      setName(prompt.name)
      setDescription(prompt.description ?? '')
    }
  }, [open, prompt])

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Edit prompt"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={submitting}
            onClick={async () => {
              setSubmitting(true)
              try {
                const updated = await api.updatePrompt(prompt.id, { name, description })
                onSaved(updated)
              } catch (e) {
                toast.error('Couldn’t save', e instanceof ApiError ? e.message : 'Unknown error')
              } finally {
                setSubmitting(false)
              }
            }}
          >
            Save
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
    </Dialog>
  )
}
