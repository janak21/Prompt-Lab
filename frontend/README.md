# PromptLab frontend

Vite + React 19 + TypeScript (strict) + Tailwind v4 + React Router 7. Builds to
`../backend/app/static/`, served by the FastAPI backend. See `../docs/DESIGN.md`,
`../docs/API_CONTRACT.md`, and `../docs/PLAN.md` for the frozen specs this app implements.

## Development

```bash
npm install
npm run dev          # real backend on :8000 (proxied via /api)
npm run dev:mock      # VITE_MOCK=1 — everything served from src/lib/mock, no backend needed
```

`/kitchen-sink` (dev-only route) is the component gallery for everything in `src/components/ui`.

## Build

```bash
npm run build          # tsc -b && vite build -> ../backend/app/static/
```

## Mock mode

Set `VITE_MOCK=1` (or use `npm run dev:mock`) to run entirely against the in-memory fake API in
`src/lib/mock/`. It implements the same `ApiClient` interface as the real fetch client
(`src/lib/api.ts`) and the same SSE event shapes (`src/lib/sse.ts`), including a simulated
streaming run, so pages built against mock mode need no changes to work against the real backend.

## Smoke test

`npx tsc -b` and `vite build` only prove the bundle compiles — they are blind to a page that
mounts React but renders nothing (for example, a missing Router provider: React mounts
successfully, `#root` stays empty, and zero errors are logged anywhere). `npm run smoke` catches
that class of bug by actually loading every registered route in a headless browser and asserting
real content appeared.

```bash
npm run dev:mock                                  # terminal 1
npm run smoke                                       # terminal 2 — defaults to http://localhost:5173
SMOKE_BASE_URL=http://localhost:5174 npm run smoke   # or point at a different port
```

For each route in `smoke.mjs`'s `ROUTES` list it asserts:
- `#root` is non-empty,
- the body text contains that route's expected substring (real content, not just a non-empty div),
- no `console.error` or uncaught `pageerror` fired during the visit.

It prints a `[PASS]`/`[FAIL]` line per route, saves a screenshot per route to `.smoke-shots/`
(gitignored), and exits non-zero if anything failed. Run it after any change that touches routing,
the app shell, or `src/main.tsx`.

It also works against a production build (`npm run build` then serve `../backend/app/static/`
with the backend, e.g. `SMOKE_BASE_URL=http://localhost:8000 npm run smoke`). `/kitchen-sink` is
registered only in dev (see `src/App.tsx`), so the script probes for a Vite dev server
(`/@vite/client`) and expects that route to redirect to `/prompts` instead when it doesn't find
one — it stays correct in both modes rather than reporting a false failure on a healthy prod build.

## Directory map

- `src/lib/types.ts` — hand-written types mirroring `docs/API_CONTRACT.md`.
- `src/lib/api.ts` — typed fetch client, one function per endpoint; dispatches to mock mode when
  `VITE_MOCK=1`.
- `src/lib/apiError.ts` — the `ApiError` class and `getFieldError` helper. Kept out of `api.ts`
  deliberately — see the comment at the top of `src/lib/mock/index.ts` for why.
- `src/lib/sse.ts` — typed `EventSource` wrapper for `GET /api/runs/{id}/events`, with reconnect
  and a mock-mode simulator swap-in.
- `src/lib/mock/` — the in-memory fake backend + seed data (2 prompts, 3 datasets incl. a full
  adversarial set, several completed runs with real per-case grades, one simulated live run).
- `src/components/ui/` — the design system (Button, Table, Dialog, Drawer, Toast, ScoreBadge,
  Chart, etc.), built to the `emil-design-eng` standard. Demoed at `/kitchen-sink`.
- `src/pages/` — one file per route.
