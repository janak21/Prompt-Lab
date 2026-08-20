"""FastAPI application entrypoint.

Phase 1 wires up only ``/api/health`` and ``/api/models`` (per the frozen API
contract's foundation scope) plus the static-file / SPA-fallback mounting that later
frontend integration depends on. Other routers (prompts, datasets, graders, runs) are
added by later phases via ``app.include_router`` in ``backend/app/routers/``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import settings
from .pricing import PRICES
from .routers import datasets, graders, prompts
from .schemas import HealthResponse, ModelInfo, ModelsResponse

try:
    from backend.app.routers import runs
except ImportError:  # pragma: no cover - owned by a parallel agent, may not exist yet at import time
    runs = None  # type: ignore[assignment]

APP_VERSION = "0.1.0"

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize the SQLite schema on process start."""
    db.init_db()
    yield


app = FastAPI(title="PromptLab API", version=APP_VERSION, lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(prompts.router)
app.include_router(graders.router)
app.include_router(datasets.router)
if runs is not None:
    app.include_router(runs.router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report process health, API-key presence (boolean only -- never the key itself), and DB path."""
    return HealthResponse(
        status="ok",
        api_key_present=bool(settings.anthropic_api_key),
        db_path=str(settings.db_path()),
        version=APP_VERSION,
    )


@app.get("/api/models", response_model=ModelsResponse)
def models() -> ModelsResponse:
    """List available models with pricing, capabilities, and the configured defaults."""
    # Enumerated rather than unpacked from `price._asdict()`: ModelPrice and ModelInfo
    # field names diverge (input_per_mtok/output_per_mtok vs. *_price_per_mtok, plus
    # `id` which only exists as the PRICES dict key) -- unpacking would silently drop
    # or misname fields rather than fail loudly. Every ModelPrice capability flag
    # (label, context_window, supports_prefill, supports_temperature, ...) still needs
    # to be listed here explicitly; add new ones as they land in pricing.py.
    model_infos = [
        ModelInfo(
            id=model_id,
            label=price.label,
            input_price_per_mtok=price.input_per_mtok,
            output_price_per_mtok=price.output_per_mtok,
            context_window=price.context_window,
            supports_prefill=price.supports_prefill,
            supports_temperature=price.supports_temperature,
        )
        for model_id, price in PRICES.items()
    ]
    return ModelsResponse(
        models=model_infos,
        default_model=settings.default_model,
        default_judge_model=settings.default_judge_model,
    )


# --------------------------------------------------------------------------
# Static files + SPA fallback
# --------------------------------------------------------------------------

ASSETS_DIR = STATIC_DIR / "assets"

if ASSETS_DIR.is_dir():
    # The Vite build emits hashed JS/CSS/font assets under static/assets/ and references
    # them from index.html as /assets/<file> -- mount the URL prefix onto that
    # subdirectory, NOT onto STATIC_DIR itself (which would 404 every asset request,
    # since e.g. /assets/index-XXXX.js would resolve to static/index-XXXX.js, which
    # doesn't exist). check_dir=False lets the app still boot before a build exists.
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR), check_dir=False), name="static-assets")


@app.get("/{full_path:path}", response_model=None)
def spa_fallback(full_path: str) -> FileResponse | JSONResponse:
    """Serve the built SPA's ``index.html`` for any non-API path (client-side routing),
    EXCEPT for a handful of top-level static assets (``favicon.svg``, ``icons.svg``,
    ``robots.txt``, etc.) that ship directly in ``STATIC_DIR`` rather than under
    ``STATIC_DIR/assets`` (which is served by the ``/assets`` mount above and never
    reaches this handler at all).

    Without this check, a request for e.g. ``/favicon.svg`` would fall through to the
    SPA-fallback branch below and get a 200 response containing ``index.html`` -- which
    is worse than a 404, since it looks superficially fine (the browser gets *a*
    document) but silently serves the wrong content instead of the actual icon.

    Before the frontend has been built, ``index.html`` doesn't exist yet -- return a
    friendly JSON message instead of a 500, so the backend is usable standalone during
    development.
    """
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # Serve a real top-level static file directly if one exists at this path (e.g.
    # favicon.svg, icons.svg) -- guard against path traversal by requiring the
    # resolved path to still live inside STATIC_DIR.
    if STATIC_DIR.is_dir() and full_path:
        candidate = (STATIC_DIR / full_path).resolve()
        if candidate.is_file() and STATIC_DIR.resolve() in candidate.parents:
            return FileResponse(str(candidate))

    if INDEX_HTML.is_file():
        return FileResponse(str(INDEX_HTML))
    return JSONResponse(
        {
            "detail": "Frontend not built yet. Run the frontend build, or use the API directly "
            "under /api/*.",
            "path": full_path,
        },
        status_code=200,
    )
