"""Shared pytest fixtures.

Every test that touches the database points ``PROMPTLAB_DB`` at a fresh temp file via
the ``tmp_db`` fixture, so tests never touch a real ``promptlab.db`` and never leak
state between tests. Because :mod:`backend.app.config` resolves its cached
``Settings`` at import time, tests that need a specific DB path re-point
``backend.app.config.settings.promptlab_db`` directly (simpler and more explicit than
juggling env vars + reload order).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app import db as db_module
from backend.app.config import settings


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app's DB path at a fresh temp file and initialize the schema."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "promptlab_db", str(db_path))
    db_module.init_db()
    return db_path


@pytest.fixture(autouse=True)
def offline_providers(monkeypatch):
    """Keep discovery offline regardless of the developer's environment."""
    from backend.app import model_catalog, pricing
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(model_catalog, "_cache", None)
    monkeypatch.setattr(pricing, "DISCOVERED_CAPABILITIES", {})
