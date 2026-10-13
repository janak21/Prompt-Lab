import { useState } from 'react'
import { Button, Dialog, Textarea } from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import type { Dataset } from '@/lib/types'

export function MockToolsDialog({ dataset, open, onClose, onSaved }: { dataset: Dataset; open: boolean; onClose: () => void; onSaved: (dataset: Dataset) => void }) {
  const [text, setText] = useState(() => JSON.stringify(dataset.tools ?? [], null, 2))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const tools = JSON.parse(text)
      if (!Array.isArray(tools)) throw new Error('Use a JSON array of tool definitions.')
      onSaved(await api.updateDataset(dataset.id, { tools }))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Could not save tools.')
    } finally {
      setSaving(false)
    }
  }
  return <Dialog open={open} onClose={onClose} title="Mock tools" size="lg" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={saving} onClick={save}>Save tools</Button></>}>
    <Textarea label="Tool definitions (JSON)" mono minRows={12} value={text} onChange={(e) => setText(e.target.value)} error={error} hint={'Each tool has name, input_schema (an object JSON Schema), optional description, and a canned response. Example: [{"name":"refund","input_schema":{"type":"object"},"response":{"ok":true}}]'} />
  </Dialog>
}
