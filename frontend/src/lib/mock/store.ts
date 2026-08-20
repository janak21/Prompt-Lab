import {
  allCases,
  datasetsSeed,
  gradersSeed,
  nextIds,
  promptVersionsSeed,
  promptsSeed,
  runCasesSeed,
  runSummariesSeed,
} from './seed'
import type { Dataset, Grader, Prompt, PromptVersion, RunCase, RunSummary, TestCase } from '../types'

// A single mutable in-memory store, deep-cloned from seed data so repeated
// edits during a session don't mutate the frozen seed module.
function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v))
}

export const store: {
  prompts: Prompt[]
  versions: PromptVersion[]
  graders: Grader[]
  datasets: Dataset[]
  cases: TestCase[]
  runs: RunSummary[]
  runCases: RunCase[]
  ids: typeof nextIds
} = {
  prompts: clone(promptsSeed),
  versions: clone(promptVersionsSeed),
  graders: clone(gradersSeed),
  datasets: clone(datasetsSeed),
  cases: clone(allCases),
  runs: clone(runSummariesSeed),
  runCases: clone(runCasesSeed),
  ids: clone(nextIds),
}

export function delay<T>(value: T, ms = 220): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

export function nowIso(): string {
  return new Date().toISOString()
}
