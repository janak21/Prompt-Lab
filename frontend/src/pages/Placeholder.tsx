export function Placeholder({ title, note }: { title: string; note?: string }) {
  return (
    <div className="flex h-full flex-col items-start gap-2 p-8">
      <span className="rounded border border-[var(--border-default)] bg-[var(--surface-2)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-tertiary)]">
        PLACEHOLDER — to be replaced
      </span>
      <h1 className="text-xl font-semibold text-[var(--text-primary)]">{title}</h1>
      {note && <p className="max-w-lg text-sm text-[var(--text-secondary)]">{note}</p>}
    </div>
  )
}
