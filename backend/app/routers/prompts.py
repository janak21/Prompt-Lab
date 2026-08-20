"""``/api/prompts`` and related routes: prompt CRUD, immutable version history.

Per ``docs/DATA_MODEL.md`` invariant 1, ``prompt_version`` rows are append-only --
there is no version UPDATE or DELETE endpoint here, only ``POST .../versions`` which
auto-increments ``version_no`` via :func:`models.create_prompt_version`.

``PromptVersion.variables`` is DERIVED at read time via :func:`templating.extract_variables`
-- it is never persisted, so every response-building helper here recomputes it from
``template``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from .. import models
from ..schemas import (
    ExtractVariablesRequest,
    ExtractVariablesResponse,
    Prompt,
    PromptCreate,
    PromptCreateResponse,
    PromptDetailResponse,
    PromptPatch,
    PromptVersion,
    PromptVersionCreate,
)
from ..templating import extract_variables

router = APIRouter(tags=["prompts"])


def _prompt_response(row: dict[str, Any]) -> Prompt:
    """Build a :class:`Prompt` response model, deriving ``version_count``/``latest_version_no``."""
    versions = models.list_prompt_versions(row["id"])
    return Prompt(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        version_count=len(versions),
        latest_version_no=versions[-1]["version_no"] if versions else None,
    )


def _version_response(row: dict[str, Any]) -> PromptVersion:
    """Build a :class:`PromptVersion` response model, deriving ``variables`` from ``template``."""
    return PromptVersion(
        id=row["id"],
        prompt_id=row["prompt_id"],
        version_no=row["version_no"],
        template=row["template"],
        system_prompt=row["system_prompt"],
        model=row["model"],
        temperature=row["temperature"],
        max_tokens=row["max_tokens"],
        notes=row["notes"],
        created_at=row["created_at"],
        variables=extract_variables(row["template"]),
    )


def _get_prompt_or_404(prompt_id: int) -> dict[str, Any]:
    row = models.get_prompt(prompt_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Prompt {prompt_id} not found")
    return row


@router.get("/api/prompts", response_model=list[Prompt])
def list_prompts() -> list[Prompt]:
    """List all prompts, newest first."""
    return [_prompt_response(row) for row in models.list_prompts()]


@router.post("/api/prompts", response_model=PromptCreateResponse, status_code=201)
def create_prompt(body: PromptCreate) -> PromptCreateResponse:
    """Create a prompt and its version 1, atomically."""
    prompt_row = models.create_prompt(body.name, description=body.description)
    try:
        version_row = models.create_prompt_version(
            prompt_row["id"],
            body.template,
            system_prompt=body.system_prompt,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
    except Exception:
        models.delete_prompt(prompt_row["id"])
        raise
    return PromptCreateResponse(
        prompt=_prompt_response(models.get_prompt(prompt_row["id"])),  # type: ignore[arg-type]
        version=_version_response(version_row),
    )


@router.get("/api/prompts/{prompt_id}", response_model=PromptDetailResponse)
def get_prompt(prompt_id: int) -> PromptDetailResponse:
    """Fetch a prompt with its full version history and graders."""
    prompt_row = _get_prompt_or_404(prompt_id)
    versions = [_version_response(v) for v in models.list_prompt_versions(prompt_id)]
    graders = [
        {
            "id": g["id"],
            "prompt_id": g["prompt_id"],
            "type": g["type"],
            "name": g["name"],
            "weight": g["weight"],
            "config": g["config"],
            "enabled": g["enabled"],
            "position": g["position"],
        }
        for g in models.list_graders(prompt_id)
    ]
    return PromptDetailResponse(prompt=_prompt_response(prompt_row), versions=versions, graders=graders)  # type: ignore[arg-type]


@router.patch("/api/prompts/{prompt_id}", response_model=Prompt)
def patch_prompt(prompt_id: int, body: PromptPatch) -> Prompt:
    """Patch a prompt's ``name``/``description``."""
    _get_prompt_or_404(prompt_id)
    row = models.update_prompt(prompt_id, name=body.name, description=body.description)
    return _prompt_response(row)  # type: ignore[arg-type]


@router.delete("/api/prompts/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: int) -> None:
    """Delete a prompt (cascades to its versions and graders)."""
    _get_prompt_or_404(prompt_id)
    models.delete_prompt(prompt_id)


@router.post("/api/prompts/{prompt_id}/versions", response_model=PromptVersion, status_code=201)
def create_version(prompt_id: int, body: PromptVersionCreate) -> PromptVersion:
    """Create the next version for a prompt (``version_no`` auto-increments)."""
    _get_prompt_or_404(prompt_id)
    row = models.create_prompt_version(
        prompt_id,
        body.template,
        system_prompt=body.system_prompt,
        model=body.model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        notes=body.notes,
    )
    return _version_response(row)


@router.get("/api/prompt-versions/{version_id}", response_model=PromptVersion)
def get_version(version_id: int) -> PromptVersion:
    """Fetch a single immutable prompt version."""
    row = models.get_prompt_version(version_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Prompt version {version_id} not found")
    return _version_response(row)


@router.post("/api/prompts/extract-variables", response_model=ExtractVariablesResponse)
def extract_variables_endpoint(body: ExtractVariablesRequest) -> ExtractVariablesResponse:
    """Pure function: extract ``{{variable}}`` names from a template. No persistence."""
    return ExtractVariablesResponse(variables=extract_variables(body.template))
