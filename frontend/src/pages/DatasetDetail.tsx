import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, ErrorState, Skeleton, TableSkeleton } from '@/components/ui'
import { AddCaseDialog } from '@/components/datasets/AddCaseDialog'
import { CaseTable } from '@/components/datasets/CaseTable'
import { GenerateDatasetDialog } from '@/components/datasets/GenerateDatasetDialog'
import { ImportDatasetDialog } from '@/components/datasets/ImportDatasetDialog'
import { api, ApiError } from '@/lib/api'
import type { Dataset, DatasetSource, TestCase } from '@/lib/types'

const SOURCE_LABEL: Record<DatasetSource, string> = { generated: 'Generated', manual: 'Manual', imported: 'Imported' }
const SOURCE_VARIANT: Record<DatasetSource, 'accent' | 'neutral' | 'warning'> = {
  generated: 'accent',
  manual: 'neutral',
  imported: 'warning',
}

export function DatasetDetailPage() {
  const { id } = useParams<{ id: string }>()
  const datasetId = Number(id)
  const navigate = useNavigate()

  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [cases, setCases] = useState<TestCase[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)

  const load = () => {
    setError(null)
    setDataset(null)
    setCases(null)
    api
      .getDataset(datasetId)
      .then((res) => {
        setDataset(res.dataset)
        setCases(res.cases)
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : 'Failed to load dataset.'))
  }

  useEffect(load, [datasetId])

  const variables = useMemo(() => {
    if (dataset?.variables.length) return dataset.variables
    const vars = new Set<string>()
    for (const c of cases ?? []) for (const k of Object.keys(c.inputs)) vars.add(k)
    return [...vars]
  }, [dataset, cases])

  if (error) return <ErrorState className="m-6" message="Couldn't load dataset" detail={error} onRetry={load} />

  if (!dataset || !cases) {
    return (
      <div className="flex flex-col gap-5 p-6">
        <Skeleton className="h-6 w-64" />
        <TableSkeleton rows={6} cols={5} />
      </div>
    )
  }

  const syncMeta = (nextCases: TestCase[]) => {
    setCases(nextCases)
    const vars = new Set<string>()
    for (const c of nextCases) for (const k of Object.keys(c.inputs)) vars.add(k)
    setDataset((d) => (d ? { ...d, case_count: nextCases.length, variables: [...vars] } : d))
  }

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate('/datasets')}
              className="text-[13px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            >
              Datasets
            </button>
            <span className="text-[13px] text-[var(--text-tertiary)]">/</span>
            <h1 className="text-[17px] font-semibold text-[var(--text-primary)]">{dataset.name}</h1>
            <Badge variant={SOURCE_VARIANT[dataset.source]}>{SOURCE_LABEL[dataset.source]}</Badge>
          </div>
          {dataset.description && <p className="text-[13px] text-[var(--text-secondary)]">{dataset.description}</p>}
          <span className="font-mono text-[12px] tabular-nums text-[var(--text-tertiary)]">
            {cases.length} case{cases.length === 1 ? '' : 's'}
            {variables.length > 0 && ` · ${variables.join(', ')}`}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="outline" onClick={() => setImportOpen(true)}>
            Import
          </Button>
          <Button variant="secondary" onClick={() => setGenerateOpen(true)}>
            Generate
          </Button>
          <Button variant="primary" onClick={() => setAddOpen(true)}>
            Add case
          </Button>
        </div>
      </div>

      <CaseTable cases={cases} variables={variables} onCasesChange={syncMeta} onAddCase={() => setAddOpen(true)} />

      <GenerateDatasetDialog
        open={generateOpen}
        onClose={() => setGenerateOpen(false)}
        datasetId={dataset.id}
        defaultVariables={variables}
        onGenerated={({ dataset: d, cases: newCases }) => {
          setDataset(d)
          syncMeta([...cases, ...newCases])
          setGenerateOpen(false)
        }}
      />
      <ImportDatasetDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        datasetId={dataset.id}
        onImported={({ dataset: d, cases: newCases }) => {
          setDataset(d)
          syncMeta([...cases, ...newCases])
          setImportOpen(false)
        }}
      />
      <AddCaseDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        datasetId={dataset.id}
        variables={variables}
        onAdded={(tc) => {
          syncMeta([...cases, tc])
          setAddOpen(false)
        }}
      />
    </div>
  )
}
