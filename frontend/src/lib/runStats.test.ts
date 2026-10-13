import assert from 'node:assert/strict'
import test from 'node:test'
import { computeLocalStats } from '../components/runs/stats.ts'
import type { RunCase } from './types.ts'

function row(patch: Partial<RunCase>): RunCase {
  return { id: 1, run_id: 1, test_case_id: 1, idx: 0, rendered_prompt: '', output: '', latency_ms: 1, input_tokens: 1, output_tokens: 1, cost: 0, final_score: 10, status: 'completed', error: null, grades: [], test_case: { id: 1, dataset_id: 1, inputs: {}, solution_criteria: null, category: null, expected_format: null, created_at: '' }, ...patch }
}

test('gate failure stays in averages and distribution, but reduces pass rate', () => {
  const stats = computeLocalStats([row({ passed: true }), row({ status: 'failed', passed: false })])
  assert.equal(stats.avg_score, 10)
  assert.equal(stats.pass_rate, 0.5)
  assert.equal(stats.distribution[9], 2)
  assert.equal(stats.by_category.uncategorized.count, 2)
})

test('inconclusive gates do not pass and unscored grades do not lower averages', () => {
  const stats = computeLocalStats([row({ passed: null, final_score: null, grades: [{ grader_name: 'syntax', grader_type: 'code_syntax', score: 0, weight: 1, reasoning: '', details: { _status: 'skipped' } }] })])
  assert.equal(stats.pass_rate, 0)
  assert.equal(stats.avg_score, null)
  assert.deepEqual(stats.by_grader, {})
  assert.deepEqual(stats.by_category, {})
})
