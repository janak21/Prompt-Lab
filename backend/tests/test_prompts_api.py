"""Tests for /api/prompts, /api/prompt-versions, and extract-variables."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from backend.app.main import app


@pytest.fixture
async def client(tmp_db: Path) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def _create_prompt(client: httpx.AsyncClient, **overrides: object) -> dict:
    body = {
        "name": "Ticket classifier",
        "template": "Classify this ticket: {{ticket_text}} for tier {{tier}}",
        "system_prompt": "You are a helpful classifier.",
    }
    body.update(overrides)
    resp = await client.post("/api/prompts", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreatePrompt:
    async def test_creates_prompt_and_version_1(self, client: httpx.AsyncClient) -> None:
        data = await _create_prompt(client)
        assert data["prompt"]["name"] == "Ticket classifier"
        assert data["prompt"]["version_count"] == 1
        assert data["prompt"]["latest_version_no"] == 1
        assert data["version"]["version_no"] == 1
        assert data["version"]["prompt_id"] == data["prompt"]["id"]

    async def test_variables_derived_from_template(self, client: httpx.AsyncClient) -> None:
        data = await _create_prompt(client)
        assert set(data["version"]["variables"]) == {"ticket_text", "tier"}

    async def test_missing_required_field_is_422(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/prompts", json={"name": "no template"})
        assert resp.status_code == 422


class TestListAndGetPrompt:
    async def test_list_prompts(self, client: httpx.AsyncClient) -> None:
        await _create_prompt(client, name="A")
        await _create_prompt(client, name="B")
        resp = await client.get("/api/prompts")
        assert resp.status_code == 200
        names = {p["name"] for p in resp.json()}
        assert {"A", "B"}.issubset(names)

    async def test_get_prompt_detail(self, client: httpx.AsyncClient) -> None:
        created = await _create_prompt(client)
        prompt_id = created["prompt"]["id"]
        resp = await client.get(f"/api/prompts/{prompt_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["prompt"]["id"] == prompt_id
        assert len(body["versions"]) == 1
        assert body["graders"] == []

    async def test_get_missing_prompt_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/prompts/999999")
        assert resp.status_code == 404


class TestPatchDeletePrompt:
    async def test_patch_name(self, client: httpx.AsyncClient) -> None:
        created = await _create_prompt(client)
        prompt_id = created["prompt"]["id"]
        resp = await client.patch(f"/api/prompts/{prompt_id}", json={"name": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    async def test_patch_missing_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch("/api/prompts/999999", json={"name": "x"})
        assert resp.status_code == 404

    async def test_delete_prompt(self, client: httpx.AsyncClient) -> None:
        created = await _create_prompt(client)
        prompt_id = created["prompt"]["id"]
        resp = await client.delete(f"/api/prompts/{prompt_id}")
        assert resp.status_code == 204
        resp2 = await client.get(f"/api/prompts/{prompt_id}")
        assert resp2.status_code == 404

    async def test_delete_missing_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete("/api/prompts/999999")
        assert resp.status_code == 404


class TestVersions:
    async def test_creating_version_auto_increments(self, client: httpx.AsyncClient) -> None:
        created = await _create_prompt(client)
        prompt_id = created["prompt"]["id"]
        resp = await client.post(
            f"/api/prompts/{prompt_id}/versions",
            json={"template": "New template {{x}}", "notes": "rewrote it"},
        )
        assert resp.status_code == 201
        v2 = resp.json()
        assert v2["version_no"] == 2
        assert v2["variables"] == ["x"]

        resp3 = await client.post(
            f"/api/prompts/{prompt_id}/versions", json={"template": "Third {{y}} {{z}}"}
        )
        assert resp3.json()["version_no"] == 3

    async def test_versions_are_immutable_no_update_endpoint(self, client: httpx.AsyncClient) -> None:
        created = await _create_prompt(client)
        prompt_id = created["prompt"]["id"]
        version_id = created["version"]["id"]
        # No PUT/PATCH route exists for a version -- confirm the method is rejected.
        resp = await client.put(f"/api/prompt-versions/{version_id}", json={"template": "hacked"})
        assert resp.status_code in (404, 405)

    async def test_get_version(self, client: httpx.AsyncClient) -> None:
        created = await _create_prompt(client)
        version_id = created["version"]["id"]
        resp = await client.get(f"/api/prompt-versions/{version_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == version_id

    async def test_get_missing_version_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/prompt-versions/999999")
        assert resp.status_code == 404

    async def test_versions_on_missing_prompt_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/prompts/999999/versions", json={"template": "x {{a}}"}
        )
        assert resp.status_code == 404


class TestExtractVariables:
    async def test_pure_function_no_persistence(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/prompts/extract-variables", json={"template": "Hello {{name}}, tier {{tier}}"}
        )
        assert resp.status_code == 200
        assert resp.json()["variables"] == ["name", "tier"]

    async def test_no_variables(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/prompts/extract-variables", json={"template": "static text"})
        assert resp.json()["variables"] == []
