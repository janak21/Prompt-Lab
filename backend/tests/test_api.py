"""Tests for the FastAPI app's /api/health and /api/models endpoints, driven via
httpx's ASGI transport (no real network, no real server process)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from backend.app import main
from backend.app.main import app


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


class TestHealth:
    async def test_status_ok(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert isinstance(body["api_key_present"], bool)
        assert "db_path" in body
        assert "version" in body

    async def test_never_exposes_the_key(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/health")
        body = resp.json()
        assert "anthropic_api_key" not in body
        assert "api_key" not in body


class TestModels:
    @pytest.fixture(autouse=True)
    def provider_models(self, monkeypatch):
        from backend.app import model_catalog
        from backend.app.config import settings
        from backend.app.pricing import PRICES

        async def listed(provider, key):
            return [{"id": id, "display_name": price.label, "created_at": "2026-01-01T00:00:00Z"} for id, price in PRICES.items()]

        monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(model_catalog, "_list_models", listed)

    async def test_lists_required_models(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/models")
        assert resp.status_code == 200
        body = resp.json()
        ids = {m["id"] for m in body["models"]}
        assert {"claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"}.issubset(ids)

    async def test_defaults(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/models")
        body = resp.json()
        assert body["default_model"] == "claude-haiku-4-5"
        assert body["default_judge_model"] == "claude-sonnet-5"

    async def test_model_entries_have_pricing(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/models")
        body = resp.json()
        for m in body["models"]:
            assert m["input_price_per_mtok"] > 0
            assert m["output_price_per_mtok"] > 0

    async def test_model_entries_have_capability_flags(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/models")
        body = resp.json()
        by_id = {m["id"]: m for m in body["models"]}
        assert by_id["claude-opus-5"]["supports_prefill"] is False
        assert by_id["claude-sonnet-5"]["supports_prefill"] is False
        assert by_id["claude-haiku-4-5"]["supports_prefill"] is True
        # Sampling params (temperature) were also removed on Claude 5 -- opus-5 and
        # sonnet-5 return HTTP 400 for a non-default temperature; haiku-4-5 still accepts it.
        assert by_id["claude-opus-5"]["supports_temperature"] is False
        assert by_id["claude-sonnet-5"]["supports_temperature"] is False
        assert by_id["claude-haiku-4-5"]["supports_temperature"] is True
        for m in body["models"]:
            assert m["context_window"] > 0


class TestSpaFallback:
    async def test_unbuilt_frontend_returns_friendly_json_not_500(
        self, client: httpx.AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Hermetic: point the app at an empty temp static dir (no index.html), regardless
        # of whether the real frontend has been built into backend/app/static/.
        empty_dir = tmp_path / "empty_static"
        empty_dir.mkdir()
        monkeypatch.setattr(main, "INDEX_HTML", empty_dir / "index.html")

        resp = await client.get("/some/random/path")
        assert resp.status_code == 200
        assert "detail" in resp.json()

    async def test_built_frontend_serves_index_html(
        self, client: httpx.AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Hermetic companion test: point the app at a temp dir containing a fake
        # index.html, so the "built" branch is exercised deterministically.
        built_dir = tmp_path / "built_static"
        built_dir.mkdir()
        fake_index = built_dir / "index.html"
        fake_index.write_text("<!doctype html><html><body>fake spa</body></html>")
        monkeypatch.setattr(main, "INDEX_HTML", fake_index)

        resp = await client.get("/some/random/path")
        assert resp.status_code == 200
        assert "fake spa" in resp.text

    async def test_unknown_api_path_is_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/does-not-exist")
        assert resp.status_code == 404


class TestStaticAssets:
    """Regression tests for the /assets mount pointing at the wrong directory.

    The bug: ``app.mount("/assets", StaticFiles(directory=str(STATIC_DIR), ...))``
    mounted the URL prefix onto STATIC_DIR itself, but the Vite build's hashed JS/CSS/
    font files live in ``STATIC_DIR/assets`` -- so every asset the built index.html
    references 404'd, and the app rendered as a blank white page (200 on the HTML
    shell, 0 children in #root) even though every existing test passed, because a 200
    on the *document* says nothing about whether its *assets* loaded.
    """

    def _patch_assets_mount(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Point the live app's /assets StaticFiles mount at a fresh temp directory
        containing one real file, and return that directory."""
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        (assets_dir / "app.js").write_bytes(b"console.log('hello from a real built asset');")

        mount_app = None
        for route in app.routes:
            if getattr(route, "path", None) == "/assets":
                mount_app = route.app
                break
        if mount_app is None:
            # main.py only registers the /assets mount when backend/app/static/assets/
            # exists at import time (see main.py's `if ASSETS_DIR.is_dir():` guard) --
            # on a fresh clone before `cd frontend && npm run build`, this test's own
            # premise (a mount to repoint) doesn't hold yet. Skip rather than fail, same
            # as test_real_build_serves_js_css_and_font_with_correct_types below.
            pytest.skip("frontend not built -- no /assets mount registered to patch")
        monkeypatch.setattr(mount_app, "directory", str(assets_dir))
        monkeypatch.setattr(mount_app, "all_directories", [str(assets_dir)])
        return assets_dir

    async def test_assets_mount_serves_files_from_the_assets_subdirectory(
        self, client: httpx.AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assets_dir = self._patch_assets_mount(tmp_path, monkeypatch)

        resp = await client.get("/assets/app.js")
        assert resp.status_code == 200
        # Assert on the actual bytes, not just that *some* 200 came back -- a 200 with
        # the wrong content (e.g. index.html) would previously have masked this bug.
        assert resp.content == (assets_dir / "app.js").read_bytes()

    async def test_real_build_serves_js_css_and_font_with_correct_types(self) -> None:
        # Exercise the actual, currently-built frontend (not a temp fixture) end to
        # end, so this test would have caught the real production bug directly.
        static_dir = Path(main.STATIC_DIR)
        assets_dir = static_dir / "assets"
        if not assets_dir.is_dir():
            pytest.skip("frontend not built -- no backend/app/static/assets to verify against")

        js_files = list(assets_dir.glob("*.js"))
        css_files = list(assets_dir.glob("*.css"))
        font_files = list(assets_dir.glob("*.woff2"))
        if not (js_files and css_files and font_files):
            pytest.skip("built assets directory is missing an expected file type")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            js_resp = await c.get(f"/assets/{js_files[0].name}")
            css_resp = await c.get(f"/assets/{css_files[0].name}")
            font_resp = await c.get(f"/assets/{font_files[0].name}")

        assert js_resp.status_code == 200
        assert js_resp.content == js_files[0].read_bytes()
        assert css_resp.status_code == 200
        assert css_resp.content == css_files[0].read_bytes()
        assert font_resp.status_code == 200
        assert font_resp.content == font_files[0].read_bytes()

    async def test_top_level_favicon_and_icons_are_not_swallowed_by_spa_fallback(
        self, client: httpx.AsyncClient
    ) -> None:
        # favicon.ico and the logo PNGs live at STATIC_DIR's top level (not under
        # assets/). Before the fix, these fell through to the SPA catch-all and got a
        # 200 containing index.html -- superficially fine, but silently wrong content.
        static_dir = Path(main.STATIC_DIR)
        if not (static_dir / "favicon.ico").is_file():
            pytest.skip("frontend not built -- no favicon.ico to verify against")

        favicon_resp = await client.get("/favicon.ico")
        assert favicon_resp.status_code == 200
        assert favicon_resp.content == (static_dir / "favicon.ico").read_bytes()
        assert "html" not in favicon_resp.headers.get("content-type", "")

        for name in ("logo-32.png", "logo-180.png"):
            if (static_dir / name).is_file():
                resp = await client.get(f"/{name}")
                assert resp.status_code == 200
                assert resp.content == (static_dir / name).read_bytes()
                assert "html" not in resp.headers.get("content-type", "")
