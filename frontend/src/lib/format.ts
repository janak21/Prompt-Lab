// Shared date formatting for list/detail views.
//
// `updated_at`/`created_at`/`finished_at` etc. come straight from the API as ISO
// strings, but several code paths can hand this a `null`, an empty string, or
// (historically, when the server was stale/misconfigured) a value `Date` can't
// parse. `new Date(bad).toLocaleString()` doesn't throw -- it silently returns the
// literal text "Invalid Date", which used to leak straight into the Prompts list.
// Route every date render through these helpers so a missing/unparseable value
// degrades to the same '—' placeholder used elsewhere for absent data (see
// `fmtCost` in Runs.tsx/RunDetail.tsx), never a raw "Invalid Date" string.

const MISSING = '—'

function toValidDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Date only, e.g. "Jan 5, 2026". Used in list tables (Prompts, Datasets). */
export function formatDate(iso: string | null | undefined): string {
  const d = toValidDate(iso)
  if (!d) return MISSING
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/** Date + time, e.g. "Jan 5, 3:04 PM". Used where recency matters (Runs, run detail, version history). */
export function formatDateTime(iso: string | null | undefined): string {
  const d = toValidDate(iso)
  if (!d) return MISSING
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
