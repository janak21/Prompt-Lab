// Simulates the server-driven event stream from docs/API_CONTRACT.md
// (`GET /api/runs/{id}/events`) entirely in-memory, on timers, so pages built
// against mock mode exercise the exact same live-progress code path they'll
// use against the real backend.

import type {
  Grade,
  RunCase,
  RunCaseStatus,
  RunStatus,
  SseEventMap,
  SseEventName,
  TestCase,
} from '../types'
import { renderTemplate } from './rng'
import { store } from './store'
import type { Grader } from '../types'

type BufferedEvent = { name: SseEventName; data: SseEventMap[SseEventName] }

interface LiveRun {
  buffer: BufferedEvent[]
  listeners: Set<(evt: BufferedEvent) => void>
  cancelled: boolean
  timer: ReturnType<typeof setTimeout> | null
}

const liveRuns = new Map<number, LiveRun>()

function emit<K extends SseEventName>(runId: number, name: K, data: SseEventMap[K]) {
  const live = liveRuns.get(runId)
  if (!live) return
  const evt = { name, data } as BufferedEvent
  live.buffer.push(evt)
  for (const l of live.listeners) l(evt)
}

function outputForMock(cs: TestCase, ok: boolean): string {
  if (!ok) return ''
  if ('transcript' in cs.inputs) return '- [Alice] Follow up on the item discussed (due: unspecified)'
  return '{"category":"general_inquiry","priority":"medium","suggested_reply":"Thanks for reaching out — looking into this now."}'
}

function scoreGrades(graders: Grader[]): Grade[] {
  return graders
    .filter((g) => g.enabled)
    .map((g) => {
      const s = Math.round((5 + Math.random() * 5) * 10) / 10
      return {
        grader_name: g.name,
        grader_type: g.type,
        score: g.type === 'code_syntax' ? (Math.random() > 0.1 ? 10 : 0) : s,
        weight: g.weight,
        reasoning: 'Simulated grading result for mock mode.',
        details: {},
      }
    })
}

export function isLiveRun(runId: number): boolean {
  return liveRuns.has(runId)
}

/** Kicks off a simulated run: template rendering, per-case timers, SSE-shaped events. */
export function startSimulatedRun(runId: number, template: string, testCases: TestCase[], graders: Grader[]) {
  const live: LiveRun = { buffer: [], listeners: new Set(), cancelled: false, timer: null }
  liveRuns.set(runId, live)

  const runSummary = store.runs.find((r) => r.id === runId)!
  runSummary.status = 'running'
  runSummary.started_at = new Date().toISOString()

  emit(runId, 'run_started', { run_id: runId, total: testCases.length })

  let completed = 0
  let failed = 0
  let scoreSum = 0
  let scoreN = 0
  let idx = 0
  let runCaseSeq = Math.max(0, ...store.runCases.map((c) => c.id)) + 1

  const step = () => {
    if (live.cancelled) return
    if (idx >= testCases.length) {
      const status: RunStatus = 'completed'
      runSummary.status = status
      runSummary.finished_at = new Date().toISOString()
      runSummary.completed = completed
      runSummary.failed = failed
      runSummary.avg_score = scoreN ? Math.round((scoreSum / scoreN) * 100) / 100 : null
      runSummary.total_cost = store.runCases
        .filter((c) => c.run_id === runId)
        .reduce((a, c) => a + (c.cost ?? 0), 0)
      emit(runId, 'run_completed', {
        run_id: runId,
        avg_score: runSummary.avg_score,
        total_cost: runSummary.total_cost ?? 0,
        completed,
        failed,
      })
      liveRuns.delete(runId)
      return
    }

    const tc = testCases[idx]
    const runCaseId = runCaseSeq++
    emit(runId, 'case_started', { run_case_id: runCaseId, test_case_id: tc.id, idx })

    live.timer = setTimeout(() => {
      if (live.cancelled) return
      const isFail = Math.random() < 0.05
      const latency = Math.round(500 + Math.random() * 2000)
      const inTok = Math.round(120 + Math.random() * 200)
      const outTok = Math.round(60 + Math.random() * 160)
      const cost = Math.round(((inTok / 1e6) * 0.8 + (outTok / 1e6) * 4) * 1e6) / 1e6
      const grades = isFail ? [] : scoreGrades(graders)
      const totalW = grades.reduce((a, g) => a + g.weight, 0)
      const finalScore = isFail || totalW === 0 ? null : Math.round((grades.reduce((a, g) => a + g.score * g.weight, 0) / totalW) * 10) / 10

      const status: RunCaseStatus = isFail ? 'failed' : 'completed'
      const runCase: RunCase = {
        id: runCaseId,
        run_id: runId,
        test_case_id: tc.id,
        idx,
        rendered_prompt: renderTemplate(template, tc.inputs),
        output: isFail ? null : outputForMock(tc, true),
        latency_ms: isFail ? null : latency,
        input_tokens: isFail ? null : inTok,
        output_tokens: isFail ? null : outTok,
        cost: isFail ? null : cost,
        final_score: finalScore,
        status,
        error: isFail ? 'Simulated transient failure (overloaded_error) after retries.' : null,
        grades,
        test_case: tc,
      }
      store.runCases.push(runCase)

      if (isFail) {
        failed += 1
        emit(runId, 'case_failed', { run_case_id: runCaseId, idx, error: runCase.error! })
      } else {
        completed += 1
        if (finalScore != null) {
          scoreSum += finalScore
          scoreN += 1
        }
        emit(runId, 'case_completed', {
          run_case_id: runCaseId,
          test_case_id: tc.id,
          idx,
          final_score: finalScore,
          latency_ms: latency,
          cost,
          status,
          output_preview: (runCase.output ?? '').slice(0, 240),
          grades,
        })
      }

      emit(runId, 'progress', {
        completed,
        failed,
        total: testCases.length,
        avg_score_so_far: scoreN ? Math.round((scoreSum / scoreN) * 100) / 100 : null,
      })

      idx += 1
      live.timer = setTimeout(step, 260 + Math.random() * 340)
    }, 420 + Math.random() * 480)
  }

  step()
}

export function cancelSimulatedRun(runId: number) {
  const live = liveRuns.get(runId)
  if (!live) return
  live.cancelled = true
  if (live.timer) clearTimeout(live.timer)
  const runSummary = store.runs.find((r) => r.id === runId)
  if (runSummary) {
    runSummary.status = 'cancelled'
    runSummary.finished_at = new Date().toISOString()
  }
  emit(runId, 'cancelled', { run_id: runId })
  liveRuns.delete(runId)
}

interface Handlers extends Partial<{ [K in SseEventName]: (data: SseEventMap[K]) => void }> {
  onOpen?: () => void
  onError?: (err: Event) => void
  onDone?: () => void
}

const TERMINAL: SseEventName[] = ['run_completed', 'run_failed', 'cancelled']

export function mockSubscribeToRunEvents(runId: number, handlers: Handlers) {
  const dispatch = (evt: BufferedEvent) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(handlers[evt.name] as any)?.(evt.data)
    if (TERMINAL.includes(evt.name)) handlers.onDone?.()
  }

  handlers.onOpen?.()

  const live = liveRuns.get(runId)
  if (!live) {
    // Run already finished (or never existed as a live run) — replay terminal state once.
    const run = store.runs.find((r) => r.id === runId)
    if (run) {
      if (run.status === 'completed') {
        dispatch({
          name: 'run_completed',
          data: { run_id: runId, avg_score: run.avg_score, total_cost: run.total_cost ?? 0, completed: run.completed, failed: run.failed },
        })
      } else if (run.status === 'failed') {
        dispatch({ name: 'run_failed', data: { run_id: runId, error: run.error ?? 'Run failed.' } })
      } else if (run.status === 'cancelled') {
        dispatch({ name: 'cancelled', data: { run_id: runId } })
      }
    }
    return { close: () => {} }
  }

  for (const evt of live.buffer) dispatch(evt)
  const listener = (evt: BufferedEvent) => dispatch(evt)
  live.listeners.add(listener)

  return {
    close: () => {
      live.listeners.delete(listener)
    },
  }
}
