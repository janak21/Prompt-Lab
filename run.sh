#!/usr/bin/env bash
# PromptLab -- one-command start.
#
# Usage:
#   ./run.sh              build (if stale) + start uvicorn + open browser
#   ./run.sh --dev         backend (uvicorn --reload) + frontend (vite dev server), both hot-reloading
#   ./run.sh --no-open     skip opening a browser
#   ./run.sh --seed        run the seed importer (idempotent) before starting
#
# Env overrides: PORT (default 8000)
set -euo pipefail

# --------------------------------------------------------------------------
# Resolve our own location, robust to being invoked from any directory and
# to spaces anywhere in the path (e.g. ".../Prompt Evaluation/promptlab").
# --------------------------------------------------------------------------
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
cd -- "$SCRIPT_DIR"

PORT="${PORT:-8000}"
DEV_MODE=0
OPEN_BROWSER=1
RUN_SEED=0

for arg in "$@"; do
    case "$arg" in
        --dev) DEV_MODE=1 ;;
        --no-open) OPEN_BROWSER=0 ;;
        --seed) RUN_SEED=1 ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: $0 [--dev] [--no-open] [--seed]" >&2
            exit 1
            ;;
    esac
done

# --------------------------------------------------------------------------
# Prerequisite checks -- fail with a clear, actionable message, never a
# raw stack trace.
# --------------------------------------------------------------------------
missing=0

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: 'uv' is not installed or not on PATH." >&2
    echo "  Install it: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    echo "  (or: brew install uv)" >&2
    missing=1
fi

if ! command -v node >/dev/null 2>&1; then
    echo "ERROR: 'node' is not installed or not on PATH." >&2
    echo "  Install it: https://nodejs.org/ (or: brew install node / nvm install --lts)" >&2
    missing=1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: 'npm' is not installed or not on PATH." >&2
    echo "  npm ships with Node.js: https://nodejs.org/" >&2
    missing=1
fi

if [ "$missing" -ne 0 ]; then
    echo "" >&2
    echo "Install the missing tool(s) above, then re-run ./run.sh." >&2
    exit 1
fi

# --------------------------------------------------------------------------
# Python deps
# --------------------------------------------------------------------------
echo "==> Syncing Python dependencies (uv sync)"
uv sync

# --------------------------------------------------------------------------
# API key status -- report BEFORE starting anything, but never block startup.
# Mirrors backend/app/config.py's resolution order: env var, else walk up
# looking for a .env defining ANTHROPIC_API_KEY.
# --------------------------------------------------------------------------
check_api_key() {
    # Mirrors backend/app/config.py's resolution exactly: if ANTHROPIC_API_KEY is
    # already set in the process environment -- even to an empty string -- that value
    # wins outright and python-dotenv will NOT fall back to a .env file (dotenv never
    # overrides an already-set env var). So an exported-but-blank key must NOT fall
    # through to the .env search below, or this check would report "found" while the
    # app itself resolves to no key.
    if [ "${ANTHROPIC_API_KEY+is_set}" = "is_set" ]; then
        [ -n "$ANTHROPIC_API_KEY" ]
        return $?
    fi
    local dir="$SCRIPT_DIR"
    while true; do
        if [ -f "$dir/.env" ] && grep -q '^ANTHROPIC_API_KEY=.\+' "$dir/.env" 2>/dev/null; then
            return 0
        fi
        local parent
        parent="$(dirname -- "$dir")"
        if [ "$parent" = "$dir" ]; then
            break
        fi
        dir="$parent"
    done
    return 1
}

if check_api_key; then
    echo "==> ANTHROPIC_API_KEY: found"
else
    echo ""
    echo "WARNING: No ANTHROPIC_API_KEY found in the environment or in any .env file"
    echo "         walking up from $SCRIPT_DIR."
    echo "         The UI will load, but any run/generation that calls the model WILL FAIL."
    echo "         Fix: copy .env.example to .env and set ANTHROPIC_API_KEY=sk-ant-..."
    echo "         (a .env in this directory or any parent directory is picked up automatically)."
    echo ""
fi

# --------------------------------------------------------------------------
# Frontend build -- only when stale. Compare newest mtime under
# frontend/src/** + frontend/package.json against backend/app/static/index.html.
# --------------------------------------------------------------------------
FRONTEND_DIR="$SCRIPT_DIR/frontend"
STATIC_INDEX="$SCRIPT_DIR/backend/app/static/index.html"

newest_source_mtime() {
    {
        [ -f "$FRONTEND_DIR/package.json" ] && stat -f '%m' "$FRONTEND_DIR/package.json" 2>/dev/null
        find "$FRONTEND_DIR/src" -type f -exec stat -f '%m' {} \; 2>/dev/null
    } | sort -rn | head -n1
}

build_frontend() {
    echo "==> Installing frontend dependencies (npm install)"
    (cd "$FRONTEND_DIR" && npm install --silent)
    echo "==> Building frontend (npm run build)"
    (cd "$FRONTEND_DIR" && npm run build)
}

if [ "$DEV_MODE" -eq 0 ]; then
    if [ ! -f "$STATIC_INDEX" ]; then
        echo "==> Frontend build branch: BUILD (no existing build found)"
        build_frontend
    else
        src_mtime="$(newest_source_mtime)"
        out_mtime="$(stat -f '%m' "$STATIC_INDEX" 2>/dev/null || echo 0)"
        if [ -n "$src_mtime" ] && [ "$src_mtime" -gt "$out_mtime" ]; then
            echo "==> Frontend build branch: BUILD (sources newer than static/index.html)"
            build_frontend
        else
            echo "==> Frontend build branch: SKIP (static/index.html is up to date)"
        fi
    fi
fi

# --------------------------------------------------------------------------
# Seed the worked example. Explicit --seed always runs it (it's idempotent,
# so this is always safe). Otherwise, auto-run it exactly when the DB has no
# prompts yet, so a first-time clone gets the example without needing a flag,
# but an existing DB with the user's own data is never touched automatically.
# --------------------------------------------------------------------------
db_is_empty() {
    uv run python -c "
from backend.app import db
db.init_db()
with db.connection() as conn:
    row = conn.execute('SELECT COUNT(*) AS n FROM prompt').fetchone()
    raise SystemExit(0 if row['n'] == 0 else 1)
" 2>/dev/null
}

if [ "$RUN_SEED" -eq 1 ]; then
    echo "==> Seeding example prompt/dataset/graders (idempotent)"
    uv run python -m backend.app.seed
elif db_is_empty; then
    echo "==> Database is empty -- seeding the worked example (idempotent)"
    uv run python -m backend.app.seed
fi

# --------------------------------------------------------------------------
# Start processes, with a trap that cleans up the whole process group on
# Ctrl-C / TERM so nothing is left orphaned.
# --------------------------------------------------------------------------
PIDS=()

cleanup() {
    echo ""
    echo "==> Shutting down..."
    for pid in "${PIDS[@]:-}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            # Kill the whole process group for this pid (negative pid), so
            # child processes (e.g. vite's esbuild worker) don't survive.
            kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

URL="http://localhost:${PORT}"

open_browser() {
    if [ "$OPEN_BROWSER" -eq 0 ]; then
        return
    fi
    if command -v open >/dev/null 2>&1; then
        open "$URL" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 || true
    fi
}

wait_for_health() {
    for _ in $(seq 1 60); do
        if curl -fsS "$URL/api/health" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

if [ "$DEV_MODE" -eq 1 ]; then
    echo "==> Starting backend (uvicorn --reload) on :$PORT"
    set -m
    uv run uvicorn backend.app.main:app --reload --port "$PORT" &
    PIDS+=("$!")
    set +m

    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        echo "==> Installing frontend dependencies (npm install)"
        (cd "$FRONTEND_DIR" && npm install --silent)
    fi

    echo "==> Starting frontend (vite dev server)"
    set -m
    (cd "$FRONTEND_DIR" && npm run dev) &
    PIDS+=("$!")
    set +m

    if wait_for_health; then
        echo "==> Backend healthy at $URL"
    else
        echo "WARNING: backend did not report healthy within 30s; continuing anyway." >&2
    fi
    # Vite dev server default port is 5173; open that in --dev mode.
    if [ "$OPEN_BROWSER" -eq 1 ]; then
        if command -v open >/dev/null 2>&1; then
            open "http://localhost:5173" >/dev/null 2>&1 || true
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "http://localhost:5173" >/dev/null 2>&1 || true
        fi
    fi
    echo "==> Backend: $URL   Frontend (dev, hot reload): http://localhost:5173"
    echo "==> Ctrl-C to stop both."
    wait
else
    echo "==> Starting PromptLab on $URL"
    set -m
    uv run uvicorn backend.app.main:app --port "$PORT" &
    PIDS+=("$!")
    set +m

    if wait_for_health; then
        echo "==> Healthy: $URL/api/health"
    else
        echo "WARNING: backend did not report healthy within 30s; continuing anyway." >&2
    fi

    open_browser
    echo "==> PromptLab running at $URL   (Ctrl-C to stop)"
    wait
fi
