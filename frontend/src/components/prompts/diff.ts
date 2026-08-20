// Small line-level diff util (LCS-based) for the version history rail.
// Deliberately simple — prompt templates are short enough that an O(n*m)
// LCS table is instant, and we don't want a dependency for this.

export type DiffLineType = 'unchanged' | 'added' | 'removed'

export interface DiffLine {
  type: DiffLineType
  text: string
}

export function diffLines(a: string, b: string): DiffLine[] {
  const aLines = a.split('\n')
  const bLines = b.split('\n')
  const n = aLines.length
  const m = bLines.length

  // dp[i][j] = length of LCS of aLines[i..] and bLines[j..]
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = aLines[i] === bLines[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }

  const result: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (aLines[i] === bLines[j]) {
      result.push({ type: 'unchanged', text: aLines[i] })
      i++
      j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      result.push({ type: 'removed', text: aLines[i] })
      i++
    } else {
      result.push({ type: 'added', text: bLines[j] })
      j++
    }
  }
  while (i < n) {
    result.push({ type: 'removed', text: aLines[i] })
    i++
  }
  while (j < m) {
    result.push({ type: 'added', text: bLines[j] })
    j++
  }
  return result
}

/** True if the diff contains any change (used to grey out a no-op diff view). */
export function hasChanges(lines: DiffLine[]): boolean {
  return lines.some((l) => l.type !== 'unchanged')
}
