"""Tests for /api/prompts/{id}/graders and /api/graders/{id}."""

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


async def _create_prompt(client: httpx.AsyncClient) -> int:
    resp = await client.post(
        "/api/prompts", json={"name": "P", "template": "Hi {{name}}"}
    )
    return resp.json()["prompt"]["id"]


class TestCreateGrader:
    async def test_create_llm_judge(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={
                "type": "llm_judge",
                "name": "quality",
                "config": {"rubric": "be helpful", "use_solution_criteria": True},
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["type"] == "llm_judge"
        assert body["config"]["rubric"] == "be helpful"
        assert body["weight"] == 1.0
        assert body["enabled"] is True

    async def test_create_code_syntax(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "code_syntax", "name": "syn", "config": {"format": "json"}},
        )
        assert resp.status_code == 201

    async def test_create_string_match(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={
                "type": "string_match",
                "name": "sm",
                "config": {"must_contain": ["hello"], "must_not_contain": []},
            },
        )
        assert resp.status_code == 201

    async def test_create_json_schema(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={
                "type": "json_schema",
                "name": "js",
                "config": {"schema": {"type": "object"}},
            },
        )
        assert resp.status_code == 201
        assert resp.json()["config"]["schema"] == {"type": "object"}

    async def test_create_budget(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "budget", "name": "b", "config": {"max_cost_usd": 0.01}},
        )
        assert resp.status_code == 201

    async def test_mismatched_config_is_422(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "code_syntax", "name": "bad", "config": {"rubric": "wrong shape"}},
        )
        assert resp.status_code == 422

    async def test_duplicate_name_is_409(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        cfg = {"type": "code_syntax", "name": "dup", "config": {"format": "json"}}
        resp1 = await client.post(f"/api/prompts/{prompt_id}/graders", json=cfg)
        assert resp1.status_code == 201
        resp2 = await client.post(f"/api/prompts/{prompt_id}/graders", json=cfg)
        assert resp2.status_code == 409

    async def test_missing_prompt_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            "/api/prompts/999999/graders",
            json={"type": "code_syntax", "name": "x", "config": {"format": "json"}},
        )
        assert resp.status_code == 404


class TestListGraders:
    async def test_list_ordered_by_position(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "code_syntax", "name": "second", "config": {"format": "json"}, "position": 2},
        )
        await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "code_syntax", "name": "first", "config": {"format": "json"}, "position": 1},
        )
        resp = await client.get(f"/api/prompts/{prompt_id}/graders")
        names = [g["name"] for g in resp.json()]
        assert names == ["first", "second"]

    async def test_list_missing_prompt_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/prompts/999999/graders")
        assert resp.status_code == 404


class TestPatchGrader:
    async def test_patch_weight_and_enabled(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        created = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "budget", "name": "b", "config": {"max_cost_usd": 0.01}},
        )
        grader_id = created.json()["id"]
        resp = await client.patch(f"/api/graders/{grader_id}", json={"weight": 2.5, "enabled": False})
        assert resp.status_code == 200
        body = resp.json()
        assert body["weight"] == 2.5
        assert body["enabled"] is False

    async def test_patch_revalidates_config_against_existing_type(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        created = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "code_syntax", "name": "syn", "config": {"format": "json"}},
        )
        grader_id = created.json()["id"]
        resp = await client.patch(
            f"/api/graders/{grader_id}", json={"config": {"rubric": "not a code_syntax config"}}
        )
        assert resp.status_code == 422

    async def test_patch_valid_config_update(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        created = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "code_syntax", "name": "syn", "config": {"format": "json"}},
        )
        grader_id = created.json()["id"]
        resp = await client.patch(f"/api/graders/{grader_id}", json={"config": {"format": "python"}})
        assert resp.status_code == 200
        assert resp.json()["config"]["format"] == "python"

    async def test_patch_name_collision_409(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "code_syntax", "name": "existing", "config": {"format": "json"}},
        )
        created2 = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "code_syntax", "name": "other", "config": {"format": "json"}},
        )
        grader_id = created2.json()["id"]
        resp = await client.patch(f"/api/graders/{grader_id}", json={"name": "existing"})
        assert resp.status_code == 409

    async def test_patch_missing_grader_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch("/api/graders/999999", json={"weight": 1.0})
        assert resp.status_code == 404


class TestDeleteGrader:
    async def test_delete(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        created = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "code_syntax", "name": "syn", "config": {"format": "json"}},
        )
        grader_id = created.json()["id"]
        resp = await client.delete(f"/api/graders/{grader_id}")
        assert resp.status_code == 204
        resp2 = await client.patch(f"/api/graders/{grader_id}", json={"weight": 1.0})
        assert resp2.status_code == 404

    async def test_delete_missing_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete("/api/graders/999999")
        assert resp.status_code == 404


class TestValidationErrorsAreJsonSafe422s:
    """The bug: pydantic v2's ValidationError.errors() carries a ctx dict for errors
    raised from a custom field_validator/model_validator, and that ctx holds the
    original ValueError object -- not JSON-serializable. Passing exc.errors() straight
    into HTTPException(detail=...) crashes the response instead of returning a 422.
    These tests hit the real HTTP boundary (not just the schema layer) and assert on
    the actual response body, for every new schemas.py guardrail, through both the
    create (POST) and patch (PATCH) call sites."""

    async def test_create_unknown_config_key_422_with_readable_body(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "budget", "name": "b", "config": {"nope": 1, "max_cost_usd": 0.1}},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], list)
        assert any("config" in e["loc"] for e in body["detail"])

    async def test_create_budget_always_skip_422_with_readable_body(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "budget", "name": "b", "config": {}},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], list)
        assert any("ceiling" in e["msg"] for e in body["detail"])

    async def test_create_string_match_always_skip_422_with_readable_body(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "string_match", "name": "sm", "config": {}},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], list)
        assert any("constraint" in e["msg"] for e in body["detail"])

    async def test_create_string_match_bad_regex_422_with_readable_body(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "string_match", "name": "sm", "config": {"regex": "([un"}},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], list)
        assert any("regex" in e["msg"].lower() or "regex" in e["loc"] for e in body["detail"])

    async def test_create_json_schema_invalid_schema_422_with_readable_body(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        resp = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={
                "type": "json_schema",
                "name": "js",
                "config": {"schema": {"type": "not-a-real-type"}},
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], list)
        assert len(body["detail"]) > 0

    async def test_patch_unknown_config_key_422_with_readable_body(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        created = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "budget", "name": "b", "config": {"max_cost_usd": 0.1}},
        )
        grader_id = created.json()["id"]
        resp = await client.patch(f"/api/graders/{grader_id}", json={"config": {"nope": 1}})
        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], list)

    async def test_patch_budget_always_skip_422_with_readable_body(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        created = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "budget", "name": "b", "config": {"max_cost_usd": 0.1}},
        )
        grader_id = created.json()["id"]
        resp = await client.patch(f"/api/graders/{grader_id}", json={"config": {}})
        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], list)
        assert any("ceiling" in e["msg"] for e in body["detail"])

    async def test_patch_string_match_bad_regex_422_with_readable_body(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        created = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "string_match", "name": "sm", "config": {"must_contain": ["x"]}},
        )
        grader_id = created.json()["id"]
        resp = await client.patch(f"/api/graders/{grader_id}", json={"config": {"regex": "([un"}})
        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], list)

    async def test_patch_json_schema_invalid_422_with_readable_body(self, client: httpx.AsyncClient) -> None:
        prompt_id = await _create_prompt(client)
        created = await client.post(
            f"/api/prompts/{prompt_id}/graders",
            json={"type": "json_schema", "name": "js", "config": {"schema": {"type": "object"}}},
        )
        grader_id = created.json()["id"]
        resp = await client.patch(
            f"/api/graders/{grader_id}", json={"config": {"schema": {"type": "bogus-type"}}}
        )
        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], list)
