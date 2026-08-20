"""Tests for /api/datasets: CRUD, cases, generation (via FakeLLM), and import."""

from __future__ import annotations

import io
import json
from pathlib import Path

import httpx
import pytest

from backend.app import models
from backend.app.llm import FakeLLM
from backend.app.main import app
from backend.app.routers import datasets as datasets_router


@pytest.fixture
async def client(tmp_db: Path) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    """Swap the datasets router's LLM client for a FakeLLM -- no real network call."""
    fake = FakeLLM()
    monkeypatch.setattr(datasets_router, "get_llm_client", lambda: fake)
    return fake


def _generated_batch_json(cases: list[dict]) -> str:
    return json.dumps({"cases": cases})


class TestDatasetCrud:
    async def test_create_dataset(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/datasets", json={"name": "D1", "description": "desc"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "D1"
        assert body["source"] == "manual"
        assert body["case_count"] == 0
        assert body["variables"] == []

    async def test_list_datasets(self, client: httpx.AsyncClient) -> None:
        await client.post("/api/datasets", json={"name": "A"})
        await client.post("/api/datasets", json={"name": "B"})
        resp = await client.get("/api/datasets")
        names = {d["name"] for d in resp.json()}
        assert {"A", "B"}.issubset(names)

    async def test_get_dataset_detail_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/datasets/999999")
        assert resp.status_code == 404

    async def test_patch_dataset(self, client: httpx.AsyncClient) -> None:
        created = await client.post("/api/datasets", json={"name": "orig"})
        ds_id = created.json()["id"]
        resp = await client.patch(f"/api/datasets/{ds_id}", json={"name": "renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed"

    async def test_patch_missing_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch("/api/datasets/999999", json={"name": "x"})
        assert resp.status_code == 404

    async def test_delete_dataset_does_not_break_runs(self, client: httpx.AsyncClient, tmp_db: Path) -> None:
        created = await client.post("/api/datasets", json={"name": "to-delete"})
        ds_id = created.json()["id"]
        # Simulate a historical run referencing this dataset (DATA_MODEL invariant 5:
        # runs are orphan-tolerant, not cascade-deleted with their dataset).
        prompt = models.create_prompt("P")
        version = models.create_prompt_version(prompt["id"], "hi {{x}}")
        run = models.create_run(
            version["id"],
            ds_id,
            model="claude-haiku-4-5",
            temperature=1.0,
            max_tokens=100,
            judge_model="claude-sonnet-5",
            concurrency=5,
            grader_snapshot=[],
        )
        resp = await client.delete(f"/api/datasets/{ds_id}")
        assert resp.status_code == 204
        # The run row must still exist untouched.
        assert models.get_run(run["id"]) is not None

    async def test_delete_missing_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete("/api/datasets/999999")
        assert resp.status_code == 404


class TestCaseCrud:
    async def test_create_case_and_derived_fields(self, client: httpx.AsyncClient) -> None:
        created = await client.post("/api/datasets", json={"name": "D"})
        ds_id = created.json()["id"]
        resp = await client.post(
            f"/api/datasets/{ds_id}/cases",
            json={"inputs": {"a": "1", "b": "2"}, "solution_criteria": "must be correct", "category": "standard"},
        )
        assert resp.status_code == 201
        case = resp.json()
        assert case["inputs"] == {"a": "1", "b": "2"}

        detail = await client.get(f"/api/datasets/{ds_id}")
        body = detail.json()
        assert body["dataset"]["case_count"] == 1
        assert set(body["dataset"]["variables"]) == {"a", "b"}

    async def test_variables_is_union_across_cases(self, client: httpx.AsyncClient) -> None:
        created = await client.post("/api/datasets", json={"name": "D"})
        ds_id = created.json()["id"]
        await client.post(f"/api/datasets/{ds_id}/cases", json={"inputs": {"a": "1"}})
        await client.post(f"/api/datasets/{ds_id}/cases", json={"inputs": {"b": "2"}})
        resp = await client.get(f"/api/datasets/{ds_id}")
        assert set(resp.json()["dataset"]["variables"]) == {"a", "b"}

    async def test_create_case_missing_dataset_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/datasets/999999/cases", json={"inputs": {"a": "1"}})
        assert resp.status_code == 404

    async def test_patch_case(self, client: httpx.AsyncClient) -> None:
        created = await client.post("/api/datasets", json={"name": "D"})
        ds_id = created.json()["id"]
        case = (await client.post(f"/api/datasets/{ds_id}/cases", json={"inputs": {"a": "1"}})).json()
        resp = await client.patch(f"/api/cases/{case['id']}", json={"category": "edge"})
        assert resp.status_code == 200
        assert resp.json()["category"] == "edge"

    async def test_patch_missing_case_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch("/api/cases/999999", json={"category": "x"})
        assert resp.status_code == 404

    async def test_delete_case(self, client: httpx.AsyncClient) -> None:
        created = await client.post("/api/datasets", json={"name": "D"})
        ds_id = created.json()["id"]
        case = (await client.post(f"/api/datasets/{ds_id}/cases", json={"inputs": {"a": "1"}})).json()
        resp = await client.delete(f"/api/cases/{case['id']}")
        assert resp.status_code == 204
        resp2 = await client.get(f"/api/datasets/{ds_id}")
        assert resp2.json()["dataset"]["case_count"] == 0

    async def test_delete_missing_case_404(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete("/api/cases/999999")
        assert resp.status_code == 404


class TestGenerateDataset:
    async def test_generate_creates_new_dataset(self, client: httpx.AsyncClient, fake_llm: FakeLLM) -> None:
        fake_llm.queue_response(
            _generated_batch_json(
                [
                    {
                        "inputs": {"ticket_text": "my card was charged twice"},
                        "solution_criteria": "must offer refund",
                        "category": "standard",
                    }
                ]
            )
        )
        resp = await client.post(
            "/api/datasets/generate",
            json={
                "name": "Generated",
                "domain_description": "classifies support tickets",
                "variables": ["ticket_text"],
                "count": 1,
                "mode": "standard",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dataset"]["source"] == "generated"
        assert len(body["cases"]) == 1
        assert body["cases"][0]["inputs"] == {"ticket_text": "my card was charged twice"}

        # Verify the structured-outputs path was used, never prefill.
        call = fake_llm.calls[0]
        assert call.output_schema is not None
        assert call.prefill is None

    async def test_generate_requires_name_when_no_dataset_id(
        self, client: httpx.AsyncClient, fake_llm: FakeLLM
    ) -> None:
        resp = await client.post(
            "/api/datasets/generate",
            json={
                "domain_description": "x",
                "variables": ["a"],
                "count": 1,
                "mode": "standard",
            },
        )
        assert resp.status_code == 422

    async def test_generate_appends_to_existing_dataset(
        self, client: httpx.AsyncClient, fake_llm: FakeLLM
    ) -> None:
        created = await client.post("/api/datasets", json={"name": "Existing"})
        ds_id = created.json()["id"]
        fake_llm.queue_response(
            _generated_batch_json(
                [{"inputs": {"a": "v"}, "solution_criteria": "sc", "category": "standard"}]
            )
        )
        resp = await client.post(
            "/api/datasets/generate",
            json={
                "dataset_id": ds_id,
                "domain_description": "x",
                "variables": ["a"],
                "count": 1,
                "mode": "standard",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["dataset"]["id"] == ds_id

    async def test_generate_missing_dataset_id_404(
        self, client: httpx.AsyncClient, fake_llm: FakeLLM
    ) -> None:
        resp = await client.post(
            "/api/datasets/generate",
            json={
                "dataset_id": 999999,
                "domain_description": "x",
                "variables": ["a"],
                "count": 1,
                "mode": "standard",
            },
        )
        assert resp.status_code == 404

    async def test_generate_drops_malformed_cases(self, client: httpx.AsyncClient, fake_llm: FakeLLM) -> None:
        # One well-formed case, one missing the required variable entirely.
        fake_llm.queue_response(
            _generated_batch_json(
                [
                    {"inputs": {"a": "ok"}, "solution_criteria": "sc", "category": "standard"},
                    {"inputs": {"wrong_key": "oops"}, "solution_criteria": "sc", "category": "standard"},
                ]
            )
        )
        resp = await client.post(
            "/api/datasets/generate",
            json={
                "name": "WithDrops",
                "domain_description": "x",
                "variables": ["a"],
                "count": 2,
                "mode": "standard",
            },
        )
        assert resp.status_code == 200
        # Only the well-formed case should have been persisted.
        assert len(resp.json()["cases"]) == 1
        assert resp.json()["cases"][0]["inputs"] == {"a": "ok"}


class TestImport:
    async def test_preview_csv(self, client: httpx.AsyncClient) -> None:
        content = b"question,answer\nWhat is 2+2?,4\nWhat is the capital of France?,Paris\n"
        files = {"file": ("cases.csv", io.BytesIO(content), "text/csv")}
        resp = await client.post("/api/datasets/import/preview", files=files)
        assert resp.status_code == 200
        body = resp.json()
        assert body["format"] == "csv"
        assert body["columns"] == ["question", "answer"]
        assert body["total_rows"] == 2
        assert len(body["rows"]) == 2

    async def test_preview_json(self, client: httpx.AsyncClient) -> None:
        content = json.dumps([{"q": "a"}, {"q": "b"}]).encode()
        files = {"file": ("cases.json", io.BytesIO(content), "application/json")}
        resp = await client.post("/api/datasets/import/preview", files=files)
        assert resp.status_code == 200
        assert resp.json()["format"] == "json"
        assert resp.json()["total_rows"] == 2

    async def test_preview_non_array_json_422(self, client: httpx.AsyncClient) -> None:
        content = json.dumps({"not": "an array"}).encode()
        files = {"file": ("cases.json", io.BytesIO(content), "application/json")}
        resp = await client.post("/api/datasets/import/preview", files=files)
        assert resp.status_code == 422

    async def test_preview_non_utf8_422(self, client: httpx.AsyncClient) -> None:
        content = b"\xff\xfe\x00bad bytes not utf8 \x80\x81"
        files = {"file": ("cases.csv", io.BytesIO(content), "text/csv")}
        resp = await client.post("/api/datasets/import/preview", files=files)
        assert resp.status_code == 422

    async def test_preview_too_large_413(self, client: httpx.AsyncClient) -> None:
        big = b"a,b\n" + b"1,2\n" * (6 * 1024 * 1024 // 4)
        files = {"file": ("big.csv", io.BytesIO(big), "text/csv")}
        resp = await client.post("/api/datasets/import/preview", files=files)
        assert resp.status_code == 413

    async def test_commit_csv_with_mapping(self, client: httpx.AsyncClient) -> None:
        content = b"question,answer,notes\nWhat is 2+2?,4,easy\n"
        files = {"file": ("cases.csv", io.BytesIO(content), "text/csv")}
        payload = {
            "name": "Imported",
            "mapping": {"question": "q", "answer": "a"},
            "solution_criteria_column": "notes",
        }
        resp = await client.post(
            "/api/datasets/import", files=files, data={"payload": json.dumps(payload)}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dataset"]["source"] == "imported"
        assert len(body["cases"]) == 1
        assert body["cases"][0]["inputs"] == {"q": "What is 2+2?", "a": "4"}
        assert body["cases"][0]["solution_criteria"] == "easy"

    async def test_commit_appends_to_existing_dataset(self, client: httpx.AsyncClient) -> None:
        created = await client.post("/api/datasets", json={"name": "Existing"})
        ds_id = created.json()["id"]
        await client.post(f"/api/datasets/{ds_id}/cases", json={"inputs": {"q": "already here"}})

        content = b"question,answer\nWhat is 2+2?,4\n"
        files = {"file": ("cases.csv", io.BytesIO(content), "text/csv")}
        payload = {"dataset_id": ds_id, "mapping": {"question": "q", "answer": "a"}}
        resp = await client.post(
            "/api/datasets/import", files=files, data={"payload": json.dumps(payload)}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["dataset"]["id"] == ds_id
        assert body["dataset"]["case_count"] == 2
        assert len(body["cases"]) == 1
        assert body["cases"][0]["inputs"] == {"q": "What is 2+2?", "a": "4"}

    async def test_commit_appends_even_with_mismatched_variable_keys(
        self, client: httpx.AsyncClient
    ) -> None:
        """Gap 2 decision: appending is allowed even when the imported cases' variable
        keys differ from the dataset's existing cases. Dataset.variables is already a
        union across cases (existing behavior), and a genuine mismatch against a
        prompt's template is caught with a clear error by the run pre-flight check
        (routers/runs.py), not by import."""
        created = await client.post("/api/datasets", json={"name": "Existing"})
        ds_id = created.json()["id"]
        await client.post(f"/api/datasets/{ds_id}/cases", json={"inputs": {"x": "1"}})

        content = b"other_col\nsome value\n"
        files = {"file": ("cases.csv", io.BytesIO(content), "text/csv")}
        payload = {"dataset_id": ds_id, "mapping": {"other_col": "y"}}
        resp = await client.post(
            "/api/datasets/import", files=files, data={"payload": json.dumps(payload)}
        )
        assert resp.status_code == 200, resp.text
        variables = set(resp.json()["dataset"]["variables"])
        assert variables == {"x", "y"}

    async def test_commit_requires_name_when_no_dataset_id(self, client: httpx.AsyncClient) -> None:
        content = b"question,answer\nWhat is 2+2?,4\n"
        files = {"file": ("cases.csv", io.BytesIO(content), "text/csv")}
        payload = {"mapping": {"question": "q", "answer": "a"}}
        resp = await client.post(
            "/api/datasets/import", files=files, data={"payload": json.dumps(payload)}
        )
        assert resp.status_code == 422

    async def test_commit_missing_dataset_id_404(self, client: httpx.AsyncClient) -> None:
        content = b"question,answer\nWhat is 2+2?,4\n"
        files = {"file": ("cases.csv", io.BytesIO(content), "text/csv")}
        payload = {"dataset_id": 999999, "mapping": {"question": "q", "answer": "a"}}
        resp = await client.post(
            "/api/datasets/import", files=files, data={"payload": json.dumps(payload)}
        )
        assert resp.status_code == 404

    async def test_commit_bad_payload_json_422(self, client: httpx.AsyncClient) -> None:
        content = b"a,b\n1,2\n"
        files = {"file": ("cases.csv", io.BytesIO(content), "text/csv")}
        resp = await client.post(
            "/api/datasets/import", files=files, data={"payload": "not json"}
        )
        assert resp.status_code == 422

    async def test_commit_payload_failing_pydantic_validation_is_422_with_readable_body(
        self, client: httpx.AsyncClient
    ) -> None:
        # Regression test: a pydantic ValidationError converted to HTTPException must
        # never crash the response (see routers/graders.py's http_422_from_validation_error
        # helper, reused here) -- `mapping` missing (required field) triggers a real
        # ValidationError through ImportPayload.model_validate().
        content = b"a,b\n1,2\n"
        files = {"file": ("cases.csv", io.BytesIO(content), "text/csv")}
        payload = {"name": "Imported"}  # missing required `mapping`
        resp = await client.post(
            "/api/datasets/import", files=files, data={"payload": json.dumps(payload)}
        )
        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], list)
        assert any("mapping" in e["loc"] for e in body["detail"])
