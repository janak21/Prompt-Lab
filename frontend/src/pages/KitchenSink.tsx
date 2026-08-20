import { useState } from 'react'
import type { ReactNode } from 'react'
import {
  Badge,
  Button,
  CategoryBars,
  CodeBlock,
  CopyButton,
  Dialog,
  DistributionChart,
  Drawer,
  DropdownMenu,
  EmptyState,
  ErrorState,
  Input,
  MetricTile,
  ProgressBar,
  ScoreBadge,
  Select,
  Skeleton,
  Slider,
  Spinner,
  StatusPill,
  OutcomePill,
  Switch,
  Table,
  Tabs,
  Tag,
  Textarea,
  Tooltip,
  TableSkeleton,
  toast,
} from '@/components/ui'
import type { RunStatus } from '@/lib/types'

const SAMPLE_JSON = JSON.stringify(
  { category: 'billing', priority: 'high', suggested_reply: 'Thanks for reaching out — checking the duplicate charge now.' },
  null,
  2,
)

const LONG_CODE = Array.from({ length: 30 }, (_, i) => `line ${i + 1}: token_${i} = compute(step=${i})`).join('\n')

interface Row {
  id: number
  name: string
  score: number
  status: RunStatus
}
const ROWS: Row[] = [
  { id: 1, name: 'v3 — adversarial set', score: 7.6, status: 'completed' },
  { id: 2, name: 'v2 — production sample', score: 8.0, status: 'completed' },
  { id: 3, name: 'v1 — baseline', score: 4.5, status: 'failed' },
]

export function KitchenSinkPage() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [switchOn, setSwitchOn] = useState(true)
  const [temp, setTemp] = useState(0.2)
  const [tab, setTab] = useState('cases')
  const [loading, setLoading] = useState(false)

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-10 p-8 pb-24">
      <header>
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Kitchen Sink</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Dev-only component gallery. Not part of the shipped app — see <code className="font-mono">/kitchen-sink</code>.
        </p>
      </header>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button variant="primary" loading>
            Loading
          </Button>
          <Button variant="primary" size="sm">
            Small
          </Button>
          <Button variant="primary" size="lg">
            Large
          </Button>
          <Button
            variant="secondary"
            loading={loading}
            onClick={() => {
              setLoading(true)
              setTimeout(() => setLoading(false), 1400)
            }}
          >
            Click to load
          </Button>
        </div>
      </Section>

      <Section title="Inputs">
        <div className="grid max-w-lg grid-cols-2 gap-4">
          <Input label="Prompt name" placeholder="Support Ticket Triage" />
          <Select label="Model" placeholder="Select a model" options={[{ value: 'a', label: 'Claude Haiku 4.5' }, { value: 'b', label: 'Claude Sonnet 4.5' }]} />
          <Input label="With error" defaultValue="bad value" error="This field is required" />
          <Input label="With hint" placeholder="e.g. 5" hint="Between 1 and 20" />
        </div>
        <Textarea className="mt-4 max-w-lg" label="Template" mono minRows={3} defaultValue={'Classify the ticket:\n"""\n{{ticket_text}}\n"""'} />
        <div className="mt-4 flex max-w-sm flex-col gap-4">
          <Slider label="Temperature" value={temp} onChange={setTemp} formatValue={(v) => v.toFixed(2)} />
          <Switch checked={switchOn} onChange={setSwitchOn} label="Use solution criteria" />
        </div>
      </Section>

      <Section title="Badges, tags, scores, status">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>Neutral</Badge>
          <Badge variant="accent">Accent</Badge>
          <Badge variant="success">Success</Badge>
          <Badge variant="warning">Warning</Badge>
          <Badge variant="danger">Danger</Badge>
          <Tag onRemove={() => {}}>ticket_text</Tag>
          <Tag onRemove={() => {}}>tier</Tag>
          <ScoreBadge score={8.4} />
          <ScoreBadge score={5.1} />
          <ScoreBadge score={2.3} />
          <ScoreBadge score={null} />
          <StatusPill status="pending" />
          <StatusPill status="running" />
          <StatusPill status="completed" />
          <StatusPill status="failed" />
          <StatusPill status="cancelled" />
          <OutcomePill outcome="a" />
          <OutcomePill outcome="b" />
          <OutcomePill outcome="tie" />
        </div>
      </Section>

      <Section title="Metric tiles">
        <div className="grid grid-cols-4 gap-3">
          <MetricTile label="Avg score" value="7.6" trend={{ direction: 'up', label: '+1.2', positive: true }} />
          <MetricTile label="Total cost" value="$0.042" />
          <MetricTile label="Completed" value="42/45" sub={<span>3 failed</span>} />
          <MetricTile label="Latency p50" value="1.2s" trend={{ direction: 'down', label: '-300ms', positive: true }} />
        </div>
      </Section>

      <Section title="Tabs">
        <Tabs
          tabs={[
            { id: 'cases', label: 'Cases', count: 45 },
            { id: 'graders', label: 'Graders', count: 4 },
            { id: 'json', label: 'Raw JSON' },
          ]}
          value={tab}
          onChange={setTab}
        />
        <div className="pt-3 text-sm text-[var(--text-secondary)]">Active tab: {tab}</div>
      </Section>

      <Section title="Table (sortable, sticky header)">
        <Table
          rows={ROWS}
          rowKey={(r) => r.id}
          columns={[
            { key: 'name', header: 'Run', render: (r) => r.name, sortValue: (r) => r.name },
            { key: 'score', header: 'Score', render: (r) => <ScoreBadge score={r.score} size="sm" />, sortValue: (r) => r.score, align: 'right' },
            { key: 'status', header: 'Status', render: (r) => <StatusPill status={r.status} /> },
          ]}
        />
      </Section>

      <Section title="Skeletons, empty & error states">
        <div className="flex flex-col gap-4">
          <div className="flex gap-3">
            <Skeleton className="h-8 w-32" />
            <Skeleton className="h-8 w-8 rounded-full" />
          </div>
          <TableSkeleton rows={3} cols={3} />
          <EmptyState
            title="No datasets yet"
            description="Generate an adversarial set, add cases manually, or import a CSV."
            action={<Button variant="primary">Create dataset</Button>}
          />
          <ErrorState message="Failed to load runs" detail="Network error — is the PromptLab server running?" onRetry={() => toast('Retrying…')} />
        </div>
      </Section>

      <Section title="Progress & spinners">
        <div className="flex max-w-xs flex-col gap-3">
          <ProgressBar value={62} />
          <div className="flex items-center gap-2">
            <Spinner /> <span className="text-sm text-[var(--text-secondary)]">Generating dataset…</span>
          </div>
        </div>
      </Section>

      <Section title="Code block & copy">
        <div className="flex flex-col gap-3">
          <CodeBlock code={SAMPLE_JSON} language="json" title="output.json" />
          <CodeBlock code={LONG_CODE} language="text" title="long output (collapsed)" collapseAfterLines={8} />
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm">rendered_prompt.txt</span>
            <CopyButton text="copy me" />
          </div>
        </div>
      </Section>

      <Section title="Charts">
        <div className="grid grid-cols-2 gap-8">
          <div>
            <p className="mb-2 text-[13px] font-medium text-[var(--text-secondary)]">Score distribution</p>
            <DistributionChart distribution={[1, 0, 2, 3, 4, 6, 9, 11, 7, 2]} />
          </div>
          <div>
            <p className="mb-2 text-[13px] font-medium text-[var(--text-secondary)]">Per-category</p>
            <CategoryBars
              items={[
                { label: 'standard', value: 8.4, count: 12 },
                { label: 'prompt_injection', value: 3.2, count: 4 },
                { label: 'ambiguous', value: 5.9, count: 6 },
                { label: 'boundary_length', value: 7.1, count: 3 },
              ]}
            />
          </div>
        </div>
      </Section>

      <Section title="Tooltip & dropdown menu">
        <div className="flex items-center gap-4">
          <Tooltip content="Copies the rendered prompt to your clipboard">
            <Button variant="secondary">Hover me</Button>
          </Tooltip>
          <Tooltip content="Adjacent tooltip — instant after the first" side="right">
            <Button variant="secondary">Then me</Button>
          </Tooltip>
          <DropdownMenu
            trigger={<Button variant="secondary">Actions ▾</Button>}
            items={[
              { id: 'dup', label: 'Duplicate', onSelect: () => toast('Duplicated') },
              { id: 'export', label: 'Export', onSelect: () => toast('Exported') },
              { id: 'del', label: 'Delete', danger: true, onSelect: () => toast.error('Deleted') },
            ]}
          />
        </div>
      </Section>

      <Section title="Dialog, drawer, toast">
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => setDialogOpen(true)}>
            Open dialog
          </Button>
          <Button variant="secondary" onClick={() => setDrawerOpen(true)}>
            Open drawer
          </Button>
          <Button variant="secondary" onClick={() => toast.success('Run started', 'Streaming results now.')}>
            Fire toast
          </Button>
        </div>
        <Dialog
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
          title="Save as new version"
          description="This creates version 4. Existing versions stay immutable."
          footer={
            <>
              <Button variant="ghost" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  setDialogOpen(false)
                  toast.success('Version 4 saved')
                }}
              >
                Save version
              </Button>
            </>
          }
        >
          <Textarea label="What changed" placeholder="Hardened against prompt injection…" minRows={3} />
        </Dialog>
        <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Case detail — #12">
          <div className="flex flex-col gap-3">
            <CodeBlock code={SAMPLE_JSON} language="json" title="output" />
            <p className="text-sm text-[var(--text-secondary)]">esc closes this drawer.</p>
          </div>
        </Drawer>
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="border-b border-[var(--border-subtle)] pb-2 text-[13px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
        {title}
      </h2>
      {children}
    </section>
  )
}
