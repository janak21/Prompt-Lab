"""``/api/prompts/{id}/graders`` and ``/api/graders/{id}`` routes.

``config`` is validated against the per-type shape (``schemas.GRADER_CONFIG_MODELS`` /
:func:`schemas.validate_grader_config`) -- a mismatched config is a 422, never a 500.
``name`` must be unique per prompt (409 on collision). ``PATCH`` re-validates ``config``
against the grader's existing (unchanged) ``type`` since ``type`` itself is immutable.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from .. import models
from ..schemas import Grader, GraderCreate, GraderCreateAdapter, GraderPatch, validate_grader_config

router = APIRouter(tags=["graders"])


def validation_error_detail(exc: ValidationError) -> list[dict[str, Any]]:
    """Convert a pydantic :class:`ValidationError` into a JSON-safe list of
    ``{loc, msg, type}`` dicts, suitable for an HTTP 422 ``detail``.

    Pydantic v2's raw ``exc.errors()`` includes a ``ctx`` dict for errors raised from a
    custom ``field_validator``/``model_validator`` (e.g. \"regex does not compile\",
    \"budget grader has no ceiling configured\") -- and that ``ctx`` carries the
    *original* ``ValueError`` object, which ``JSONResponse`` cannot serialize, crashing
    the response with a 500 instead of returning the intended 422. This drops ``ctx``
    (and the doc-link ``url``) and keeps only the JSON-safe, UI-usable fields: ``loc``
    (so the frontend can attach the error to the right field/input) and ``msg`` (the
    human-readable message -- for our custom validators this already names the
    offending constraint, e.g. which grader-config field is invalid).
    """
    return [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors(include_url=False, include_context=False)
    ]


def http_422_from_validation_error(exc: ValidationError) -> HTTPException:
    """Build a 422 :class:`HTTPException` from a pydantic :class:`ValidationError`,
    using :func:`validation_error_detail` so the response body is always JSON-safe.
    Every ``ValidationError`` -> ``HTTPException`` conversion in this package's routers
    should go through this helper rather than calling ``exc.errors()`` directly.
    """
    return HTTPException(status_code=422, detail=validation_error_detail(exc))


def _grader_response(row: dict[str, Any]) -> Grader:
    return Grader(
        id=row["id"],
        prompt_id=row["prompt_id"],
        type=row["type"],
        name=row["name"],
        weight=row["weight"],
        config=row["config"],
        enabled=row["enabled"],
        position=row["position"],
    )


def _get_prompt_or_404(prompt_id: int) -> dict[str, Any]:
    row = models.get_prompt(prompt_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Prompt {prompt_id} not found")
    return row


def _get_grader_or_404(grader_id: int) -> dict[str, Any]:
    row = models.get_grader(grader_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Grader {grader_id} not found")
    return row


@router.get("/api/prompts/{prompt_id}/graders", response_model=list[Grader])
def list_graders(prompt_id: int) -> list[Grader]:
    """List all graders for a prompt, ordered by ``position``."""
    _get_prompt_or_404(prompt_id)
    return [_grader_response(g) for g in models.list_graders(prompt_id)]


@router.post("/api/prompts/{prompt_id}/graders", response_model=Grader, status_code=201)
def create_grader(prompt_id: int, body: dict[str, Any]) -> Grader:
    """Create a grader for a prompt.

    Validates the body against the discriminated union (``GraderCreateAdapter``) so a
    ``type``/``config`` mismatch is a 422, not a 500. Enforces ``name`` uniqueness per
    prompt (409 on collision).
    """
    _get_prompt_or_404(prompt_id)
    try:
        validated: GraderCreate = GraderCreateAdapter.validate_python(body)
    except ValidationError as exc:
        raise http_422_from_validation_error(exc) from exc

    existing = models.list_graders(prompt_id)
    if any(g["name"] == validated.name for g in existing):
        raise HTTPException(
            status_code=409, detail=f"Grader name {validated.name!r} already exists for this prompt"
        )

    config_dict = validated.config.model_dump(mode="json", by_alias=True)
    row = models.create_grader(
        prompt_id,
        validated.type,
        validated.name,
        config_dict,
        weight=validated.weight,
        enabled=validated.enabled,
        position=validated.position,
    )
    return _grader_response(row)


@router.patch("/api/graders/{grader_id}", response_model=Grader)
def patch_grader(grader_id: int, body: GraderPatch) -> Grader:
    """Patch a grader's mutable fields. ``config`` is re-validated against the grader's
    existing ``type`` (which cannot itself be changed here)."""
    existing = _get_grader_or_404(grader_id)

    if body.name is not None and body.name != existing["name"]:
        siblings = models.list_graders(existing["prompt_id"])
        if any(g["id"] != grader_id and g["name"] == body.name for g in siblings):
            raise HTTPException(
                status_code=409, detail=f"Grader name {body.name!r} already exists for this prompt"
            )

    validated_config: dict[str, Any] | None = None
    if body.config is not None:
        try:
            validated_config = validate_grader_config(existing["type"], body.config)
        except ValidationError as exc:
            raise http_422_from_validation_error(exc) from exc

    row = models.update_grader(
        grader_id,
        name=body.name,
        weight=body.weight,
        config=validated_config,
        enabled=body.enabled,
        position=body.position,
    )
    return _grader_response(row)  # type: ignore[arg-type]


@router.delete("/api/graders/{grader_id}", status_code=204)
def delete_grader(grader_id: int) -> None:
    """Delete a single grader."""
    _get_grader_or_404(grader_id)
    models.delete_grader(grader_id)
