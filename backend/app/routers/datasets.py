"""``/api/datasets`` routes: dataset CRUD, case CRUD, AI generation, and import.

``Dataset.variables`` is DERIVED (the union of keys across its cases' ``inputs``) and
``case_count`` is derived -- neither is stored, both are recomputed on every read.
Deleting a dataset cascades to its ``test_case`` rows only; per DATA_MODEL invariant 5,
existing runs are untouched (they keep denormalized/snapshotted data and tolerate a
missing parent dataset).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from .. import models
from ..config import settings
from ..eval import importers
from ..eval.generation import generate_cases
from ..llm import LLMClient
from ..providers import ProviderLLM
from ..model_catalog import discover_models
from .graders import http_422_from_validation_error
from ..schemas import (
    Dataset,
    DatasetCreate,
    DatasetDetailResponse,
    DatasetPatch,
    GenerateDatasetRequest,
    GenerateDatasetResponse,
    ImportPayload,
    ImportPreviewResponse,
    ImportResponse,
    TestCase,
    TestCaseCreate,
    TestCasePatch,
)

router = APIRouter(tags=["datasets"])

_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return the process-wide :class:`LLMClient` used for dataset generation.

    Lazily constructed so importing this module never requires an API key (e.g. in
    tests, which override this via FastAPI dependency overrides or by monkeypatching
    this function to return a :class:`llm.FakeLLM`).
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = ProviderLLM()
    return _llm_client


def _dataset_response(row: dict[str, Any]) -> Dataset:
    cases = models.list_test_cases(row["id"])
    variables: list[str] = []
    seen: set[str] = set()
    for case in cases:
        for key in case["inputs"]:
            if key not in seen:
                seen.add(key)
                variables.append(key)
    return Dataset(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        source=row["source"],
        created_at=row["created_at"],
        case_count=len(cases),
        variables=variables,
        tools=row["tools"],
    )


def _case_response(row: dict[str, Any]) -> TestCase:
    return TestCase(
        id=row["id"],
        dataset_id=row["dataset_id"],
        inputs=row["inputs"],
        conversation=row["conversation"],
        solution_criteria=row["solution_criteria"],
        category=row["category"],
        expected_format=row["expected_format"],
        created_at=row["created_at"],
    )


def _get_dataset_or_404(dataset_id: int) -> dict[str, Any]:
    row = models.get_dataset(dataset_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    return row


def _get_case_or_404(case_id: int) -> dict[str, Any]:
    row = models.get_test_case(case_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Test case {case_id} not found")
    return row


# --------------------------------------------------------------------------
# Dataset CRUD
# --------------------------------------------------------------------------


@router.get("/api/datasets", response_model=list[Dataset])
def list_datasets() -> list[Dataset]:
    """List all datasets, newest first."""
    return [_dataset_response(row) for row in models.list_datasets()]


@router.post("/api/datasets", response_model=Dataset, status_code=201)
def create_dataset(body: DatasetCreate) -> Dataset:
    """Create an empty, manually-authored dataset."""
    row = models.create_dataset(body.name, description=body.description, source="manual", tools=[t.model_dump(mode="json") for t in body.tools])
    return _dataset_response(row)


@router.get("/api/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(dataset_id: int) -> DatasetDetailResponse:
    """Fetch a dataset with all of its cases."""
    row = _get_dataset_or_404(dataset_id)
    cases = [_case_response(c) for c in models.list_test_cases(dataset_id)]
    return DatasetDetailResponse(dataset=_dataset_response(row), cases=cases)


@router.patch("/api/datasets/{dataset_id}", response_model=Dataset)
def patch_dataset(dataset_id: int, body: DatasetPatch) -> Dataset:
    """Patch a dataset's ``name``/``description``."""
    _get_dataset_or_404(dataset_id)
    row = models.update_dataset(dataset_id, name=body.name, description=body.description, tools=[t.model_dump(mode="json") for t in body.tools] if body.tools is not None else None)
    return _dataset_response(row)  # type: ignore[arg-type]


@router.delete("/api/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: int) -> None:
    """Delete a dataset and its cases. Existing runs are untouched (DATA_MODEL invariant 5)."""
    _get_dataset_or_404(dataset_id)
    models.delete_dataset(dataset_id)


# --------------------------------------------------------------------------
# Case CRUD
# --------------------------------------------------------------------------


@router.post("/api/datasets/{dataset_id}/cases", response_model=TestCase, status_code=201)
def create_case(dataset_id: int, body: TestCaseCreate) -> TestCase:
    """Add a test case to a dataset."""
    _get_dataset_or_404(dataset_id)
    row = models.create_test_case(
        dataset_id,
        body.inputs,
        solution_criteria=body.solution_criteria,
        category=body.category,
        expected_format=body.expected_format,
        conversation=body.conversation,
    )
    return _case_response(row)


@router.patch("/api/cases/{case_id}", response_model=TestCase)
def patch_case(case_id: int, body: TestCasePatch) -> TestCase:
    """Patch any subset of a test case's fields."""
    _get_case_or_404(case_id)
    row = models.update_test_case(
        case_id,
        inputs=body.inputs,
        solution_criteria=body.solution_criteria,
        category=body.category,
        expected_format=body.expected_format,
        conversation=body.conversation,
    )
    return _case_response(row)  # type: ignore[arg-type]


@router.delete("/api/cases/{case_id}", status_code=204)
def delete_case(case_id: int) -> None:
    """Delete a single test case."""
    _get_case_or_404(case_id)
    models.delete_test_case(case_id)


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


@router.post("/api/datasets/generate", response_model=GenerateDatasetResponse)
async def generate_dataset(body: GenerateDatasetRequest) -> GenerateDatasetResponse:
    """Generate test cases via structured-output LLM calls and persist them.

    Creates a new dataset (``name`` required) or appends to an existing one
    (``dataset_id``). Generated cases' ``inputs`` keys are guaranteed to be exactly
    ``body.variables`` -- see ``eval.generation`` for the enforcement + drop reporting.
    """
    if body.dataset_id is not None:
        dataset_row = _get_dataset_or_404(body.dataset_id)
    else:
        if not body.name:
            raise HTTPException(status_code=422, detail="`name` is required when `dataset_id` is omitted")
        dataset_row = models.create_dataset(body.name, source="generated")

    model = body.model or settings.default_model
    if body.model is None and isinstance(get_llm_client(), ProviderLLM):
        model = (await discover_models()).default_model
        if not model:
            raise HTTPException(status_code=422, detail="No models available. Configure a provider key and refresh Settings.")
    result = await generate_cases(
        get_llm_client(),
        domain_description=body.domain_description,
        variables=body.variables,
        count=body.count,
        mode=body.mode,
        model=model,
        prompt_template=body.prompt_template,
    )

    case_rows = [
        models.create_test_case(
            dataset_row["id"],
            case["inputs"],
            solution_criteria=case["solution_criteria"],
            category=case["category"],
        )
        for case in result.cases
    ]

    return GenerateDatasetResponse(
        dataset=_dataset_response(models.get_dataset(dataset_row["id"])),  # type: ignore[arg-type]
        cases=[_case_response(r) for r in case_rows],
    )


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------


@router.post("/api/datasets/import/preview", response_model=ImportPreviewResponse)
async def import_preview(file: UploadFile = File(...)) -> ImportPreviewResponse:
    """Preview an upload: detected format, columns, first 10 rows, total row count."""
    try:
        content = await importers.read_capped(file)
    except importers.UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    try:
        result = importers.preview(file.filename or "upload", content)
    except importers.ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ImportPreviewResponse(**result)


@router.post("/api/datasets/import", response_model=ImportResponse)
async def import_dataset(file: UploadFile = File(...), payload: str = Form(...)) -> ImportResponse:
    """Commit an import: apply the column -> variable mapping and persist the dataset.

    Creates a new dataset (``name`` required) or appends to an existing one
    (``dataset_id``) -- mirrors ``POST /api/datasets/generate``. Appending does not
    require the imported cases' variable keys to match the existing cases' keys:
    ``Dataset.variables`` is already the union of keys across all of a dataset's cases
    (see module docstring), and a real mismatch is caught with a clear error at run
    time by the pre-flight template-variable check in ``routers/runs.py`` -- rejecting
    at import time would block the exact "collect one production failure at a time"
    workflow this endpoint exists for, since a single odd case would otherwise fail the
    whole append.
    """
    import json as _json

    try:
        payload_dict = _json.loads(payload)
    except _json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"`payload` is not valid JSON: {exc}") from exc
    try:
        parsed_payload = ImportPayload.model_validate(payload_dict)
    except ValidationError as exc:
        raise http_422_from_validation_error(exc) from exc

    if parsed_payload.dataset_id is not None:
        dataset_row = _get_dataset_or_404(parsed_payload.dataset_id)
    else:
        if not parsed_payload.name:
            raise HTTPException(status_code=422, detail="`name` is required when `dataset_id` is omitted")
        dataset_row = models.create_dataset(parsed_payload.name, source="imported")

    try:
        content = await importers.read_capped(file)
    except importers.UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    try:
        _fmt, parsed = importers.parse_rows(file.filename or "upload", content)
    except importers.ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cases = importers.apply_mapping(
        parsed,
        parsed_payload.mapping,
        solution_criteria_column=parsed_payload.solution_criteria_column,
        category_column=parsed_payload.category_column,
        expected_format_column=parsed_payload.expected_format_column,
    )

    case_rows = [
        models.create_test_case(
            dataset_row["id"],
            case["inputs"],
            solution_criteria=case["solution_criteria"],
            category=case["category"],
            expected_format=case["expected_format"],
        )
        for case in cases
    ]

    return ImportResponse(
        dataset=_dataset_response(models.get_dataset(dataset_row["id"])),  # type: ignore[arg-type]
        cases=[_case_response(r) for r in case_rows],
    )
