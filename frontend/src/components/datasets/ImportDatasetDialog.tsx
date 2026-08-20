import { useEffect, useRef, useState } from 'react'
import { Badge, Button, Dialog, Input, Select, Spinner, toast } from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import type { Dataset, ImportPreviewResponse, TestCase } from '@/lib/types'

type Step = 'drop' | 'mapping'

export function ImportDatasetDialog({
  open,
  onClose,
  datasetId,
  onImported,
}: {
  open: boolean
  onClose: () => void
  /** Append to this dataset, or omit to create a new one. */
  datasetId?: number
  onImported: (result: { dataset: Dataset; cases: TestCase[] }) => void
}) {
  const [step, setStep] = useState<Step>('drop')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [name, setName] = useState('')
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [solutionCriteriaColumn, setSolutionCriteriaColumn] = useState('')
  const [categoryColumn, setCategoryColumn] = useState('')
  const [expectedFormatColumn, setExpectedFormatColumn] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) {
      setStep('drop')
      setFile(null)
      setPreview(null)
      setPreviewError(null)
      setName('')
      setMapping({})
      setSolutionCriteriaColumn('')
      setCategoryColumn('')
      setExpectedFormatColumn('')
    }
  }, [open])

  const loadFile = async (f: File) => {
    setFile(f)
    setName(f.name.replace(/\.(csv|json|jsonl)$/i, ''))
    setLoadingPreview(true)
    setPreviewError(null)
    try {
      const res = await api.importPreview(f)
      setPreview(res)
      const initialMapping: Record<string, string> = {}
      for (const col of res.columns) initialMapping[col] = col
      setMapping(initialMapping)
      setStep('mapping')
    } catch (e) {
      const message =
        e instanceof ApiError
          ? e.status === 413
            ? 'File is too large to import.'
            : e.status === 422
              ? `Could not read this file: ${e.message}`
              : e.message
          : 'Failed to read file.'
      setPreviewError(message)
    } finally {
      setLoadingPreview(false)
    }
  }

  const submit = async () => {
    if (!file) return
    const usedVars = new Set(Object.values(mapping).filter(Boolean))
    if (usedVars.size === 0) {
      toast.error('Map at least one column', 'Pick a variable name for at least one column.')
      return
    }
    setSubmitting(true)
    try {
      const finalMapping: Record<string, string> = {}
      for (const [col, varName] of Object.entries(mapping)) if (varName.trim()) finalMapping[col] = varName.trim()
      const res = await api.importDataset(file, {
        dataset_id: datasetId,
        name: datasetId ? undefined : name.trim() || file.name,
        mapping: finalMapping,
        solution_criteria_column: solutionCriteriaColumn || undefined,
        category_column: categoryColumn || undefined,
        expected_format_column: expectedFormatColumn || undefined,
      })
      toast.success(`Imported ${res.cases.length} cases`, res.dataset.name)
      onImported(res)
    } catch (e) {
      toast.error('Import failed', e instanceof ApiError ? e.message : 'Unknown error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Import dataset" size="lg">
      {step === 'drop' && (
        <div className="flex flex-col gap-3">
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              const f = e.dataTransfer.files[0]
              if (f) loadFile(f)
            }}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors duration-150 ${
              dragOver ? 'border-[var(--accent-9)] bg-[var(--accent-a-10)]' : 'border-[var(--border-default)] bg-[var(--surface-2)]'
            }`}
          >
            {loadingPreview ? (
              <>
                <Spinner size={20} />
                <span className="text-[13px] text-[var(--text-secondary)]">Reading {file?.name}…</span>
              </>
            ) : (
              <>
                <svg width="28" height="28" viewBox="0 0 28 28" fill="none" className="text-[var(--text-tertiary)]">
                  <path
                    d="M14 4v14M14 4l-5 5M14 4l5 5M6 20v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className="text-[13px] font-medium text-[var(--text-primary)]">Drop a CSV, JSON, or JSONL file</span>
                <span className="text-[12px] text-[var(--text-tertiary)]">or click to browse</span>
              </>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.json,.jsonl"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) loadFile(f)
            }}
          />
          {previewError && (
            <div className="rounded-md border border-[var(--danger-9)]/30 bg-[var(--score-low-bg)] px-3 py-2 text-[13px] text-[var(--danger-10)]">
              {previewError}
            </div>
          )}
        </div>
      )}

      {step === 'mapping' && preview && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Badge variant="neutral">{preview.format.toUpperCase()}</Badge>
            <span className="text-[12px] text-[var(--text-tertiary)]">
              {preview.total_rows} row{preview.total_rows === 1 ? '' : 's'} detected — showing the first {preview.rows.length}
            </span>
          </div>
          {!datasetId && <Input label="Dataset name" value={name} onChange={(e) => setName(e.target.value)} />}

          <div className="flex flex-col gap-1.5">
            <label className="text-[13px] font-medium text-[var(--text-secondary)]">Column → variable mapping</label>
            <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
              <table className="w-full border-collapse text-left text-[12.5px]">
                <thead>
                  <tr className="bg-[var(--surface-2)]">
                    {preview.columns.map((c) => (
                      <th key={c} className="border-b border-[var(--border-subtle)] px-3 py-2 font-medium text-[var(--text-tertiary)]">
                        <div className="flex flex-col gap-1">
                          <span className="font-mono text-[var(--text-primary)]">{c}</span>
                          <Input
                            aria-label={`Variable name for column ${c}`}
                            value={mapping[c] ?? ''}
                            onChange={(e) => setMapping((m) => ({ ...m, [c]: e.target.value }))}
                            placeholder="skip"
                            className="!h-6 !text-[12px]"
                            mono
                          />
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, i) => (
                    <tr key={i} className="border-b border-[var(--border-subtle)] last:border-b-0">
                      {preview.columns.map((c) => (
                        <td key={c} className="max-w-[180px] truncate px-3 py-1.5 font-mono text-[var(--text-secondary)]">
                          {String(row[c] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Select
              label="Solution criteria column"
              value={solutionCriteriaColumn}
              onChange={(e) => setSolutionCriteriaColumn(e.target.value)}
              options={preview.columns.map((c) => ({ value: c, label: c }))}
              placeholder="None"
            />
            <Select
              label="Category column"
              value={categoryColumn}
              onChange={(e) => setCategoryColumn(e.target.value)}
              options={preview.columns.map((c) => ({ value: c, label: c }))}
              placeholder="None"
            />
            <Select
              label="Expected format column"
              value={expectedFormatColumn}
              onChange={(e) => setExpectedFormatColumn(e.target.value)}
              options={preview.columns.map((c) => ({ value: c, label: c }))}
              placeholder="None"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setStep('drop')} disabled={submitting}>
              Back
            </Button>
            <Button variant="primary" onClick={submit} loading={submitting}>
              Import {preview.total_rows} case{preview.total_rows === 1 ? '' : 's'}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  )
}
