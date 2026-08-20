// Headless-render smoke test. tsc and `vite build` are both blind to a page
// that mounts React but renders nothing (e.g. a missing Router provider) —
// they only prove the bundle compiles and the HTML shell is served. This
// script actually loads every route in a real browser and asserts content
// showed up.
//
// Usage:
//   npm run dev:mock            # in one terminal
//   npm run smoke                # in another (defaults to http://localhost:5173)
//   SMOKE_BASE_URL=http://localhost:5174 npm run smoke
//
// Exits non-zero if any route is blank, is missing its expected text, or
// logs a console error / uncaught page error.

import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.dirname(fileURLToPath(import.meta.url))
const shotsDir = path.join(rootDir, '.smoke-shots')
const BASE_URL = process.env.SMOKE_BASE_URL ?? 'http://localhost:5173'

// One entry per registered route (see src/App.tsx). `expect` is a string
// that must appear in the rendered body text — proof of real content, not
// just a non-empty #root.
const ROUTES = [
  { name: 'root-redirect', path: '/', expect: 'PromptLab' },
  { name: 'prompts', path: '/prompts', expect: 'Prompts' },
  { name: 'prompt-detail', path: '/prompts/1', expect: 'Prompts' },
  { name: 'datasets', path: '/datasets', expect: 'Datasets' },
  { name: 'dataset-detail', path: '/datasets/1', expect: 'Datasets' },
  { name: 'runs', path: '/runs', expect: 'Runs' },
  { name: 'run-detail', path: '/runs/1', expect: 'Runs' },
  { name: 'compare', path: '/compare', expect: 'Compare' },
  { name: 'settings', path: '/settings', expect: 'Settings' },
  { name: 'kitchen-sink', path: '/kitchen-sink', expect: 'Kitchen Sink' },
]

async function main() {
  await mkdir(shotsDir, { recursive: true })

  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } })

  let anyFailed = false
  const results = []

  for (const route of ROUTES) {
    const consoleErrors = []
    const pageErrors = []
    const onConsole = (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    }
    const onPageError = (err) => pageErrors.push(String(err))
    page.on('console', onConsole)
    page.on('pageerror', onPageError)

    let rootHtml = ''
    let bodyText = ''
    let navError = null
    try {
      await page.goto(`${BASE_URL}${route.path}`, { waitUntil: 'networkidle', timeout: 15000 })
      await page.waitForTimeout(400)
      rootHtml = await page.innerHTML('#root').catch(() => '')
      bodyText = (await page.innerText('body').catch(() => '')).replace(/\s+/g, ' ').trim()
    } catch (err) {
      navError = String(err)
    }

    page.off('console', onConsole)
    page.off('pageerror', onPageError)

    const isBlank = rootHtml.trim().length === 0
    const hasExpectedText = bodyText.includes(route.expect)
    const hasErrors = consoleErrors.length > 0 || pageErrors.length > 0 || navError != null
    const pass = !isBlank && hasExpectedText && !hasErrors

    if (!pass) anyFailed = true

    const shotFile = path.join(shotsDir, `${route.name}.png`)
    await page.screenshot({ path: shotFile }).catch(() => {})

    results.push({ route, pass, isBlank, hasExpectedText, consoleErrors, pageErrors, navError, bodyPreview: bodyText.slice(0, 90) })
  }

  await browser.close()

  console.log(`\nSmoke test against ${BASE_URL}\n`)
  for (const r of results) {
    const status = r.pass ? 'PASS' : 'FAIL'
    console.log(`[${status}] ${r.route.path.padEnd(18)} ${r.pass ? r.bodyPreview : ''}`)
    if (!r.pass) {
      if (r.navError) console.log(`         navigation error: ${r.navError}`)
      if (r.isBlank) console.log('         #root is empty — page rendered nothing')
      if (!r.hasExpectedText) console.log(`         expected text "${r.route.expect}" not found. body: "${r.bodyPreview}"`)
      for (const e of r.consoleErrors) console.log(`         console.error: ${e.slice(0, 200)}`)
      for (const e of r.pageErrors) console.log(`         pageerror: ${e.slice(0, 200)}`)
    }
  }

  console.log(`\nScreenshots saved to ${path.relative(rootDir, shotsDir)}/`)

  if (anyFailed) {
    console.error('\nsmoke test FAILED — one or more routes are blank, missing content, or logged an error.')
    process.exit(1)
  }
  console.log('\nsmoke test passed — all routes rendered real content with no console/page errors.')
}

main().catch((err) => {
  console.error('smoke test crashed:', err)
  process.exit(1)
})
