// Deterministic PRNG so seed data (scores, timings) is stable across reloads
// within a session but still looks varied, rather than uniformly fake.
export function mulberry32(seed: number) {
  let a = seed
  return function rand() {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function renderTemplate(template: string, inputs: Record<string, string>): string {
  return template.replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, (_, key: string) =>
    key in inputs ? inputs[key] : `{{${key}}}`,
  )
}

export function extractVariableNames(template: string): string[] {
  const found = new Set<string>()
  const re = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g
  let m: RegExpExecArray | null
  while ((m = re.exec(template))) found.add(m[1])
  return [...found]
}
