import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Dialog, EmptyState, ErrorState, Input, Table, TableSkeleton, Textarea, toast } from '@/components/ui'
import type { Column } from '@/components/ui'
import { GenerateDatasetDialog } from '@/components/datasets/GenerateDatasetDialog'
import { ImportDatasetDialog } from '@/components/datasets/ImportDatasetDialog'
import { api, ApiError } from '@/lib/api'
import type { Dataset, DatasetSource } from '@/lib/types'

const SOURCE_LABEL: Record<DatasetSource, string> = { generated: 'Generated', manual: 'Manual', imported: 'Imported' }
const SOURCE_VARIANT: Record<DatasetSource, 'accent' | 'neutral' | 'warning'> = {
  generated: 'accent',
  manual: 'neutral',
  imported: 'warning',
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export function DatasetsPage() {
  const navigate = useNavigate()
  const [datasets, setDatasets] = useState<Dataset[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [newOpen, setNewOpen] = useState(false)

  const load = () => {
    setError(null)
    setDatasets(null)
    api
      .listDatasets()
      .then(setDatasets)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : 'Failed to load datasets.'))
  }

  useEffect(load, [])

  const columns: Column<Dataset>[] = [
    { key: 'name', header: 'Name', sortValue: (d) => d.name, render: (d) => <span className="font-medium text-[var(--text-primary)]">{d.name}</span> },
    {
      key: 'source',
      header: 'Source',
      render: (d) => <Badge variant={SOURCE_VARIANT[d.source]}>{SOURCE_LABEL[d.source]}</Badge>,
    },
    { key: 'case_count', header: 'Cases', align: 'right', mono: true, sortValue: (d) => d.case_count, render: (d) => d.case_count },
    {
      key: 'variables',
      header: 'Variables',
      render: (d) =>
        d.variables.length ? (
          <span className="font-mono text-[12px] text-[var(--text-secondary)]">{d.variables.join(', ')}</span>
        ) : (
          <span className="text-[var(--text-tertiary)]">—</span>
        ),
    },
    { key: 'created_at', header: 'Created', align: 'right', mono: true, sortValue: (d) => d.created_at, render: (d) => formatDate(d.created_at) },
  ]

  const actions = (
    <div className="flex items-center gap-2">
      <Button variant="outline" onClick={() => setImportOpen(true)}>
        Import
      </Button>
      <Button variant="secondary" onClick={() => setNewOpen(true)}>
        New dataset
      </Button>
      <Button variant="primary" onClick={() => setGenerateOpen(true)}>
        Generate
      </Button>
    </div>
  )

  return (
    <div className="flex flex-col gap-5 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[17px] font-semibold text-[var(--text-primary)]">Datasets</h1>
          <p className="text-[13px] text-[var(--text-secondary)]">Test cases for evaluating prompts.</p>
        </div>
        {datasets && datasets.length > 0 && actions}
      </div>

      {error ? (
        <ErrorState message="Couldn't load datasets" detail={error} onRetry={load} />
      ) : datasets === null ? (
        <TableSkeleton rows={5} cols={5} />
      ) : datasets.length === 0 ? (
        <EmptyState
          title="No datasets yet"
          description="Generate cases from a description, add them manually, or import a file — three ways to get started."
          action={actions}
        />
      ) : (
        <Table
          columns={columns}
          rows={datasets}
          rowKey={(d) => d.id}
          onRowClick={(d) => navigate(`/datasets/${d.id}`)}
          initialSort={{ key: 'created_at', direction: 'desc' }}
        />
      )}

      <GenerateDatasetDialog
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
        onGenerated={({ dataset }) => {
          setGenerateOpen(false)
          navigate(`/datasets/${dataset.id}`)
        }}
      />
      <ImportDatasetDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={({ dataset }) => {
          setImportOpen(false)
          navigate(`/datasets/${dataset.id}`)
        }}
      />
      <NewDatasetDialog
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onCreated={(dataset) => {
          setNewOpen(false)
          navigate(`/datasets/${dataset.id}`)
        }}
      />
    </div>
  )
}

function NewDatasetDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (d: Dataset) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setName('')
      setDescription('')
      setError(null)
    }
  }, [open])

  const submit = async () => {
    if (!name.trim()) {
      setError('Name is required.')
      return
    }
    setSubmitting(true)
    try {
      const dataset = await api.createDataset({ name: name.trim(), description: description.trim() || undefined })
      toast.success('Dataset created', dataset.name)
      onCreated(dataset)
    } catch (e) {
      toast.error('Couldn’t create dataset', e instanceof ApiError ? e.message : 'Unknown error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New dataset"
      description="Creates an empty dataset — add cases manually, generate them, or import a file next."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={submitting}>
            Create
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} error={error ?? undefined} autoFocus />
        <Textarea label="Description" value={description} onChange={(e) => setDescription(e.target.value)} hint="Optional" minRows={2} />
      </div>
    </Dialog>
  )
}
