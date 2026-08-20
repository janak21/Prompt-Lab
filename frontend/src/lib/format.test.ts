// Run with: node --test src/lib/format.test.ts   (Node 24 strips TS types natively).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatDate, formatDateTime } from './format.ts'

test('formatDate renders a valid ISO string', () => {
  assert.equal(formatDate('2026-01-05T12:00:00Z'), 'Jan 5, 2026')
})

test('formatDate falls back to em-dash for null/undefined/empty', () => {
  assert.equal(formatDate(null), '—')
  assert.equal(formatDate(undefined), '—')
  assert.equal(formatDate(''), '—')
})

test('formatDate falls back to em-dash instead of "Invalid Date" for unparseable input', () => {
  assert.equal(formatDate('not-a-date'), '—')
  assert.notEqual(formatDate('not-a-date'), 'Invalid Date')
})

test('formatDateTime renders a valid ISO string', () => {
  const result = formatDateTime('2026-01-05T12:00:00Z')
  assert.match(result, /Jan 5/)
  assert.notEqual(result, '—')
})

test('formatDateTime falls back to em-dash for null/undefined/empty/unparseable', () => {
  assert.equal(formatDateTime(null), '—')
  assert.equal(formatDateTime(undefined), '—')
  assert.equal(formatDateTime(''), '—')
  assert.equal(formatDateTime('garbage'), '—')
})
