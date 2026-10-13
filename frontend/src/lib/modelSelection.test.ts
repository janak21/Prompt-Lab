import assert from 'node:assert/strict'
import test from 'node:test'
import { effectiveRunModel } from './modelSelection.ts'

const models = [{ id: 'claude-current' }, { id: 'openai:gpt-current' }]

test('an explicit provider selection overrides a saved model', () => {
  assert.equal(effectiveRunModel('openai:gpt-current', 'claude-current', 'claude-current', models), 'openai:gpt-current')
})

test('an available saved model remains the effective selection', () => {
  assert.equal(effectiveRunModel('', 'openai:gpt-current', 'claude-current', models), 'openai:gpt-current')
})

test('retired or unset saved ids fall back to the discovered default', () => {
  assert.equal(effectiveRunModel('', 'claude-retired', 'claude-current', models), 'claude-current')
  assert.equal(effectiveRunModel('', null, 'openai:gpt-current', models), 'openai:gpt-current')
})
