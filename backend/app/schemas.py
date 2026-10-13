"""Pydantic v2 schemas for every shape in ``docs/API_CONTRACT.md``.

Later agents (routers, runner, generation, frontend type generation) should import from
here rather than redefining these shapes. Field names are ``snake_case`` throughout,
matching the contract exactly.

Grader ``config`` validation is discriminated on the grader's ``type``: see
``GraderConfigCreate`` (a discriminated union, used directly as the POST body for
creating a grader -- FastAPI raises 422 automatically on a type/config mismatch) and
:func:`validate_grader_config` (for validating a config dict against a known type at
runtime, e.g. on PATCH, where the type isn't re-supplied in the body).
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

import jsonschema
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

# --------------------------------------------------------------------------
# Enums (as literal aliases -- kept as plain strings for easy DB round-tripping)
# --------------------------------------------------------------------------

DatasetSource = Literal["generated", "manual", "imported"]
GraderType = Literal["llm_judge", "code_syntax", "string_match", "json_schema", "budget", "tool_calls"]
RunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
RunCaseStatus = Literal["pending", "running", "completed", "failed"]
CodeSyntaxFormat = Literal["json", "python", "regex", "auto"]
ExpectedFormat = Literal["json", "python", "regex"]
GenerationMode = Literal["standard", "adversarial", "mixed"]
ImportFormat = Literal["csv", "json", "jsonl"]


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


class MockTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    description: str = ""
    input_schema: dict[str, Any]
    response: Any = None

    @field_validator("input_schema")
    @classmethod
    def _valid_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            jsonschema.validators.validator_for(value).check_schema(value)
        except jsonschema.SchemaError as exc:
            raise ValueError(f"Invalid tool input_schema: {exc.message}") from exc
        if value.get("type") != "object":
            raise ValueError("Tool input_schema must have type object.")
        return value


def validate_tool_names(tools: list[MockTool]) -> list[MockTool]:
    if len({tool.name for tool in tools}) != len(tools):
        raise ValueError("Mock tool names must be unique.")
    return tools


Conversation = Annotated[list[str], Field(max_length=20)]


class Prompt(BaseModel):
    """A named prompt with derived version-count metadata."""

    id: int
    name: str
    description: str | None = None
    created_at: str
    updated_at: str
    version_count: int
    latest_version_no: int | None = None


class PromptVersion(BaseModel):
    """One immutable version of a prompt's template + generation settings."""

    id: int
    prompt_id: int
    version_no: int
    template: str
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    notes: str | None = None
    created_at: str
    variables: list[str] = Field(default_factory=list)


class Grader(BaseModel):
    """A configured grader attached to a prompt."""

    id: int
    prompt_id: int
    type: GraderType
    name: str
    weight: float
    config: dict[str, Any]
    enabled: bool
    position: int
    gating: bool = False
    pass_threshold: float = 8.0


class Dataset(BaseModel):
    """A named collection of test cases."""

    tools: list[MockTool] = Field(default_factory=list)

    id: int
    name: str
    description: str | None = None
    source: DatasetSource
    created_at: str
    case_count: int
    variables: list[str] = Field(default_factory=list)


class TestCase(BaseModel):
    """A single input example within a dataset."""

    conversation: Conversation = Field(default_factory=list)

    id: int
    dataset_id: int
    inputs: dict[str, str]
    solution_criteria: str | None = None
    category: str | None = None
    expected_format: ExpectedFormat | None = None
    created_at: str


class Grade(BaseModel):
    """One grader's verdict on one run_case."""

    grader_name: str
    grader_type: GraderType
    score: float
    weight: float
    reasoning: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RunCase(BaseModel):
    """One test case's execution + grading result within a run."""

    transcript: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)

    id: int
    run_id: int
    test_case_id: int
    idx: int
    rendered_prompt: str | None = None
    output: str | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None
    passed: bool | None = None
    final_score: float | None = None
    status: RunCaseStatus
    error: str | None = None
    grades: list[Grade] = Field(default_factory=list)
    test_case: TestCase


class RunSummary(BaseModel):
    """A run's headline info, without full per-case detail."""

    id: int
    prompt_id: int
    prompt_name: str
    prompt_version_id: int
    version_no: int
    dataset_id: int
    dataset_name: str
    model: str
    judge_model: str
    temperature: float
    status: RunStatus
    pass_rate: float | None = None
    avg_score: float | None = None
    total_cost: float | None = None
    total: int
    completed: int
    failed: int
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str
    error: str | None = None


class GraderStat(BaseModel):
    """Aggregate stats for one grader within a run."""

    avg_score: float
    weight: float


class CategoryStat(BaseModel):
    """Aggregate stats for one test-case category within a run."""

    avg_score: float
    count: int


class RunStats(BaseModel):
    """Aggregate statistics computed over a run's cases."""

    pass_rate: float | None = None
    avg_score: float | None = None
    total_cost: float = 0.0
    total_latency_ms: int = 0
    total: int = 0
    completed: int = 0
    failed: int = 0
    by_grader: dict[str, GraderStat] = Field(default_factory=dict)
    by_category: dict[str, CategoryStat] = Field(default_factory=dict)
    distribution: list[int] = Field(default_factory=lambda: [0] * 10)


# --------------------------------------------------------------------------
# Meta
# --------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"]
    api_key_present: bool
    db_path: str
    version: str


class ModelInfo(BaseModel):
    id: str
    label: str
    input_price_per_mtok: float
    output_price_per_mtok: float
    context_window: int
    supports_prefill: bool
    supports_temperature: bool


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    default_model: str
    default_judge_model: str


# --------------------------------------------------------------------------
# Prompts — request bodies
# --------------------------------------------------------------------------


class PromptCreate(BaseModel):
    name: str
    description: str | None = None
    template: str
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class PromptCreateResponse(BaseModel):
    prompt: Prompt
    version: PromptVersion


class PromptPatch(BaseModel):
    name: str | None = None
    description: str | None = None


class PromptDetailResponse(BaseModel):
    prompt: Prompt
    versions: list[PromptVersion]
    graders: list[Grader]


class PromptVersionCreate(BaseModel):
    template: str
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    notes: str | None = None


class ExtractVariablesRequest(BaseModel):
    template: str


class ExtractVariablesResponse(BaseModel):
    variables: list[str]


# --------------------------------------------------------------------------
# Graders — config shapes (discriminated on the grader's `type`)
# --------------------------------------------------------------------------


class LLMJudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rubric: str
    use_solution_criteria: bool
    judge_model: str | None = None
    scale_max: Literal[10] = 10


class CodeSyntaxConfig(BaseModel):
    """``format: "auto"`` legitimately skips per-case when a test case has no
    ``expected_format`` -- that is a dynamic, per-case decision (not knowable at
    config-save time) and must stay allowed; it is NOT an always-skip configuration."""

    model_config = ConfigDict(extra="forbid")

    format: CodeSyntaxFormat


class StringMatchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    regex: str | None = None
    case_sensitive: bool = False

    @field_validator("regex")
    @classmethod
    def _regex_must_compile(cls, v: str | None) -> str | None:
        """Reject an uncompilable regex at config-save time rather than failing on
        every single case of a run."""
        if v is None:
            return v
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"regex does not compile: {exc}") from exc
        return v

    @model_validator(mode="after")
    def _reject_always_skip(self) -> "StringMatchConfig":
        """A string_match grader with no constraints at all can never contribute a
        score -- that's a configuration error, not a valid (if lenient) grader."""
        if not self.must_contain and not self.must_not_contain and not self.regex:
            raise ValueError(
                "string_match grader has no constraints configured -- must_contain, "
                "must_not_contain, and regex are all empty, so it would never score "
                "anything. Add at least one of: must_contain, must_not_contain, regex."
            )
        return self


class JsonSchemaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: dict[str, Any] = Field(alias="schema")

    @field_validator("schema_")
    @classmethod
    def _schema_must_be_valid_json_schema(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Reject a malformed JSON Schema at config-save time rather than failing on
        every single case of a run."""
        try:
            validator_cls = jsonschema.validators.validator_for(v)
            validator_cls.check_schema(v)
        except jsonschema.exceptions.SchemaError as exc:
            raise ValueError(f"schema is not a valid JSON Schema: {exc.message}") from exc
        except Exception as exc:  # defensive: malformed shape jsonschema itself chokes on
            raise ValueError(f"schema is not a valid JSON Schema: {exc}") from exc
        return v


class BudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_latency_ms: float | None = None
    max_cost_usd: float | None = None
    max_output_tokens: float | None = None

    @model_validator(mode="after")
    def _reject_always_skip(self) -> "BudgetConfig":
        """A budget grader with no ceiling set can never contribute a score -- that's
        a configuration error (a silent no-op guardrail), not a valid empty state."""
        if self.max_latency_ms is None and self.max_cost_usd is None and self.max_output_tokens is None:
            raise ValueError(
                "budget grader has no ceiling configured -- max_latency_ms, "
                "max_cost_usd, and max_output_tokens are all unset, so it would never "
                "score anything. Set at least one of: max_latency_ms, max_cost_usd, "
                "max_output_tokens."
            )
        return self


class ToolCallsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1)
    mode: Literal["never_called", "called_with_arguments"]
    arguments: dict[str, Any] = Field(default_factory=dict)


GRADER_CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "llm_judge": LLMJudgeConfig,
    "code_syntax": CodeSyntaxConfig,
    "string_match": StringMatchConfig,
    "json_schema": JsonSchemaConfig,
    "budget": BudgetConfig,
    "tool_calls": ToolCallsConfig,
}


def validate_grader_config(grader_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Validate ``config`` against the Pydantic model for ``grader_type``.

    Returns the validated config as a plain dict (JSON-mode, so ``schema_`` round-trips
    back to the wire key ``schema``). Raises :class:`pydantic.ValidationError` if
    ``grader_type`` is unknown or ``config`` doesn't match its shape -- callers (routers)
    should catch this and re-raise as an HTTP 422.
    """
    model_cls = GRADER_CONFIG_MODELS.get(grader_type)
    if model_cls is None:
        raise ValueError(f"Unknown grader type: {grader_type!r}")
    instance = model_cls.model_validate(config)
    return instance.model_dump(mode="json", by_alias=True)


class _GraderCreateBase(BaseModel):
    gating: bool = False
    pass_threshold: float = Field(default=8.0, ge=0, le=10, allow_inf_nan=False)


class _LLMJudgeGraderCreate(_GraderCreateBase):
    type: Literal["llm_judge"]
    name: str
    weight: float = 1.0
    config: LLMJudgeConfig
    enabled: bool = True
    position: int = 0


class _CodeSyntaxGraderCreate(_GraderCreateBase):
    type: Literal["code_syntax"]
    name: str
    weight: float = 1.0
    config: CodeSyntaxConfig
    enabled: bool = True
    position: int = 0


class _StringMatchGraderCreate(_GraderCreateBase):
    type: Literal["string_match"]
    name: str
    weight: float = 1.0
    config: StringMatchConfig
    enabled: bool = True
    position: int = 0


class _JsonSchemaGraderCreate(_GraderCreateBase):
    type: Literal["json_schema"]
    name: str
    weight: float = 1.0
    config: JsonSchemaConfig
    enabled: bool = True
    position: int = 0


class _BudgetGraderCreate(_GraderCreateBase):
    type: Literal["budget"]
    name: str
    weight: float = 1.0
    config: BudgetConfig
    enabled: bool = True
    position: int = 0


class _ToolCallsGraderCreate(_GraderCreateBase):
    type: Literal["tool_calls"]
    name: str
    weight: float = 1.0
    config: ToolCallsConfig
    enabled: bool = True
    position: int = 0


GraderCreate = Annotated[
    _LLMJudgeGraderCreate
    | _CodeSyntaxGraderCreate
    | _StringMatchGraderCreate
    | _JsonSchemaGraderCreate
    | _BudgetGraderCreate
    | _ToolCallsGraderCreate,
    Field(discriminator="type"),
]
"""Discriminated union for POST /api/prompts/{id}/graders. FastAPI validates the request
body against exactly the config shape matching ``type`` and raises 422 automatically on
a mismatch (e.g. ``type: "budget"`` with a ``config`` missing all budget fields, or a
``config`` shaped for a different grader type)."""

GraderCreateAdapter: TypeAdapter[Any] = TypeAdapter(GraderCreate)


class GraderPatch(BaseModel):
    """PATCH body for an existing grader. ``config``'s shape is validated against the
    grader's existing (unchanged) ``type`` via :func:`validate_grader_config`, since the
    type itself is not re-specified on PATCH."""

    name: str | None = None
    weight: float | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    position: int | None = None
    gating: bool | None = None
    pass_threshold: float | None = Field(default=None, ge=0, le=10, allow_inf_nan=False)


# --------------------------------------------------------------------------
# Datasets — request bodies
# --------------------------------------------------------------------------


class DatasetCreate(BaseModel):
    tools: list[MockTool] = Field(default_factory=list, max_length=20)
    _unique_tools = field_validator("tools")(validate_tool_names)

    name: str
    description: str | None = None


class DatasetPatch(BaseModel):
    tools: list[MockTool] | None = Field(default=None, max_length=20)

    @field_validator("tools")
    @classmethod
    def _unique_tools(cls, tools: list[MockTool] | None) -> list[MockTool] | None:
        return validate_tool_names(tools) if tools is not None else None

    name: str | None = None
    description: str | None = None


class DatasetDetailResponse(BaseModel):
    dataset: Dataset
    cases: list[TestCase]


class TestCaseCreate(BaseModel):
    conversation: Conversation = Field(default_factory=list)
    inputs: dict[str, str]
    solution_criteria: str | None = None
    category: str | None = None
    expected_format: ExpectedFormat | None = None


class TestCasePatch(BaseModel):
    conversation: Conversation | None = None
    inputs: dict[str, str] | None = None
    solution_criteria: str | None = None
    category: str | None = None
    expected_format: ExpectedFormat | None = None


class GenerateDatasetRequest(BaseModel):
    dataset_id: int | None = None
    name: str | None = None
    domain_description: str
    variables: list[str]
    count: int = Field(ge=1, le=50)
    mode: GenerationMode
    model: str | None = None
    prompt_template: str | None = None


class GenerateDatasetResponse(BaseModel):
    dataset: Dataset
    cases: list[TestCase]


class ImportPreviewResponse(BaseModel):
    format: ImportFormat
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int


class ImportPayload(BaseModel):
    dataset_id: int | None = None
    name: str | None = None
    mapping: dict[str, str]
    solution_criteria_column: str | None = None
    category_column: str | None = None
    expected_format_column: str | None = None


class ImportResponse(BaseModel):
    dataset: Dataset
    cases: list[TestCase]


# --------------------------------------------------------------------------
# Runs — request bodies
# --------------------------------------------------------------------------


class RunCreate(BaseModel):
    prompt_version_id: int
    dataset_id: int
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    judge_model: str | None = None
    concurrency: int | None = None


class RunCreateResponse(BaseModel):
    run_id: int
    status: Literal["pending"]


class RunDetailResponse(BaseModel):
    run: RunSummary
    stats: RunStats
    cases: list[RunCase]


class RunCancelResponse(BaseModel):
    status: Literal["cancelled"]


class CompareSideResponse(BaseModel):
    run: RunSummary
    stats: RunStats


class CompareDeltas(BaseModel):
    avg_score: float
    pass_rate: float | None = None
    total_cost: float
    by_grader: dict[str, float] = Field(default_factory=dict)
    by_category: dict[str, float] = Field(default_factory=dict)


class CompareCase(BaseModel):
    test_case: TestCase
    a: RunCase | None = None
    b: RunCase | None = None
    winner: Literal["a", "b", "tie"]
    delta: float


class CompareWins(BaseModel):
    a: int
    b: int
    tie: int


class RunCompareResponse(BaseModel):
    a: CompareSideResponse
    b: CompareSideResponse
    deltas: CompareDeltas
    cases: list[CompareCase]
    wins: CompareWins


# --------------------------------------------------------------------------
# SSE event payloads
# --------------------------------------------------------------------------


class RunStartedEvent(BaseModel):
    run_id: int
    total: int


class CaseStartedEvent(BaseModel):
    run_case_id: int
    test_case_id: int
    idx: int


class CaseCompletedEvent(BaseModel):
    passed: bool | None = None
    error: str | None = None
    run_case_id: int
    test_case_id: int
    idx: int
    final_score: float | None
    latency_ms: int | None
    cost: float | None
    status: RunCaseStatus
    output_preview: str | None
    grades: list[Grade]


class CaseFailedEvent(BaseModel):
    run_case_id: int
    idx: int
    error: str


class ProgressEvent(BaseModel):
    completed: int
    failed: int
    total: int
    avg_score_so_far: float | None


class RunCompletedEvent(BaseModel):
    pass_rate: float | None = None
    run_id: int
    avg_score: float | None
    total_cost: float
    completed: int
    failed: int


class RunFailedEvent(BaseModel):
    run_id: int
    error: str


class CancelledEvent(BaseModel):
    run_id: int
