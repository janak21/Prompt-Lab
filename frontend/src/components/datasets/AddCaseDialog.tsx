import { useEffect, useState } from 'react'
import { Button, Dialog, Input, Select, Textarea, toast } from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import type { ExpectedFormat, TestCase } from '@/lib/types'
import { ALL_CATEGORY_OPTIONS, categoryLabel } from './category'

export function AddCaseDialog({
  open,
  onClose,
  datasetId,
  variables,
  onAdded,
}: {
  open: boolean
  onClose: () => void
  datasetId: number
  variables: string[]
  onAdded: (testCase: TestCase) => void
}) {
  const [inputs, setInputs] = useState<Record<string, string>>({})
  const [extraVarNames, setExtraVarNames] = useState<string[]>([])
  const [newVarName, setNewVarName] = useState('')
  const [solutionCriteria, setSolutionCriteria] = useState('')
  const [category, setCategory] = useState('standard')
  const [expectedFormat, setExpectedFormat] = useState<ExpectedFormat>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setInputs(Object.fromEntries(variables.map((v) => [v, ''])))
      setExtraVarNames([])
      setNewVarName('')
      setSolutionCriteria('')
      setCategory('standard')
      setExpectedFormat(null)
      setError(null)
    }
  }, [open, variables])

  const allVars = [...variables, ...extraVarNames]
  const addVariable = () => {
    const v = newVarName.trim()
    if (!v || allVars.includes(v)) return
    setExtraVarNames((cur) => [...cur, v])
    setInputs((cur) => ({ ...cur, [v]: '' }))
    setNewVarName('')
  }

  const submit = async () => {
    if (allVars.length > 0 && allVars.every((v) => !inputs[v]?.trim())) {
      setError('Fill in at least one input variable.')
      return
    }
    setSubmitting(true)
    try {
      const tc = await api.createCase(datasetId, {
        inputs,
        solution_criteria: solutionCriteria.trim() || undefined,
        category,
        expected_format: expectedFormat ?? undefined,
      })
      toast.success('Case added')
      onAdded(tc)
    } catch (e) {
      toast.error('Couldn’t add case', e instanceof ApiError ? e.message : 'Unknown error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add case"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={submitting}>
            Add case
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3.5">
        {allVars.length === 0 && (
          <p className="text-[12px] text-[var(--text-tertiary)]">This dataset has no variables yet — add one below.</p>
        )}
        {allVars.map((v) => (
          <Input
            key={v}
            label={v}
            mono
            value={inputs[v] ?? ''}
            onChange={(e) => setInputs((cur) => ({ ...cur, [v]: e.target.value }))}
          />
        ))}
        <div className="flex items-end gap-2">
          <Input
            label="Add variable"
            value={newVarName}
            onChange={(e) => setNewVarName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                addVariable()
              }
            }}
            placeholder="e.g. ticket_text"
            mono
            className="flex-1"
          />
          <Button variant="outline" onClick={addVariable} type="button">
            Add
          </Button>
        </div>
        {error && <span className="text-[12px] text-[var(--danger-10)]">{error}</span>}
        <Textarea
          label="Solution criteria"
          value={solutionCriteria}
          onChange={(e) => setSolutionCriteria(e.target.value)}
          hint="Optional — what a correct output looks like, used by the llm_judge grader."
          minRows={2}
        />
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            options={ALL_CATEGORY_OPTIONS.map((c) => ({ value: c, label: categoryLabel(c) }))}
          />
          <Select
            label="Expected format"
            value={expectedFormat ?? ''}
            onChange={(e) => setExpectedFormat((e.target.value || null) as ExpectedFormat)}
            options={[
              { value: '', label: 'None' },
              { value: 'json', label: 'JSON' },
              { value: 'python', label: 'Python' },
              { value: 'regex', label: 'Regex' },
            ]}
          />
        </div>
      </div>
    </Dialog>
  )
}
