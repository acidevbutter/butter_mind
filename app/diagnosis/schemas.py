import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Fields the concierge can offer as tappable options in a qualification turn.
# "none" means "this turn has no structured options -- just the composer".
# ADR-0007: services_of_interest/budget_range/timeline replaced by the
# ScopingVector dimensions that actually drive cost (see _SCOPING_CATALOG in
# service.py). budget_range/timeline are never asked as pills anymore --
# budget_ceiling is an optional constraint, not a question.
NextStepField = Literal[
    "business_type",
    "problem_area",
    "solution_kinds",
    "integrations",
    "surfaces",
    "ai_shape",
    "design_load",
    "engagement",
    "rush",
    "none",
]

# The conversation walks these stages (ADR-0004). butter_mind computes the
# stage deterministically from state -- it is not something the LLM decides.
DiagnosisStage = Literal["qualifying", "choosing", "collecting", "ready"]

# Business-profile keys required before stage can become "ready". The three
# ScopingVector dimensions are the minimum needed for a price to make sense
# (ADR-0007) -- merged into the same effective-profile dict in service.py's
# _extraction_profile, even though they don't live on BusinessProfile.
REQUIRED_PROFILE_FIELDS = (
    "business_name",
    "segment",
    "contact_name",
    "solution_kinds",
    "ai_shape",
    "surfaces",
)


class ProductOptionDraft(BaseModel):
    """One path the concierge proposes once it understands the problem
    (ADR-0004 / prompt-fluxo-cotacao-ia.md §1). The LLM fills these; butter_mind
    assigns the stable `key` in _sanitize_options. price_range/timeline stay
    free text and are `null` when there is no catalog basis for a figure."""

    title: str
    summary: str
    price_range: str | None = None
    timeline: str | None = None
    recommended: bool = False


class ProductOption(ProductOptionDraft):
    """A ProductOptionDraft with the server-assigned stable key."""

    key: str


class BusinessMetric(BaseModel):
    """One short number the visitor stated about the business -- rendered as a
    "números do negócio" stat card in the live dossiê (Fluxo Cotação IA, canvas
    screen 2a). `value` is always free text, never a real number.
    `computed=true` only when the AI derived the figure (e.g. hours/day spent on
    repetitive replies), never for a value that was not mentioned."""

    label: str
    value: str
    computed: bool = False


class DiagnosisSessionCreate(BaseModel):
    session_id: str


class DiagnosisSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: str
    status: str
    created_at: datetime


class DiagnosisMessageCreate(BaseModel):
    content: str


class DiagnosisMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class ScopingVector(BaseModel):
    """The real cost drivers of a request (ADR-0007), replacing the weak
    services_of_interest/budget_range/timeline proxies. One field per
    dimension of `_SCOPING_CATALOG` (service.py) -- ids are catalog-stable
    snake_case, never free text. Every field is optional: the vector fills in
    incrementally as the conversation (or a next_step pill tap) reveals it.
    Not persisted yet (ADR-0007 slice 02) -- recomputed each turn from the
    extraction, like BusinessProfile.
    """

    solution_kinds: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)
    ai_shape: str | None = None
    data_mode: str | None = None
    auth_mode: str | None = None
    novelty: str | None = None
    design_load: str | None = None
    compliance: list[str] = Field(default_factory=list)
    engagement: str | None = None
    rush: str | None = None
    # Optional "teto que você tem em mente" constraint -- never a question the
    # concierge asks, unlike the old budget_range pill.
    budget_ceiling: str | None = None


class DiagnosisExtraction(BaseModel):
    """Structured extraction the LLM produces once enough of the conversation
    has been gathered — consumed by DiagnosisService, never exposed raw via the API.

    contact_name/contact_email/contact_phone/company_name/cnpj are gathered
    from the conversation itself (see DIAGNOSIS_SYSTEM_PROMPT), not supplied
    by the caller of POST /diagnosis/sessions/{id}/submit -- devbutter_backend
    consumes them from this extraction to create the visitor's account without
    a separate signup form (see devbutter_backend's
    docs/plano-onboarding-conversa-primeiro.md). EXTRACTION_SYSTEM_PROMPT
    requires contact_name and contact_email before ready_to_submit=true.
    """

    ready_to_submit: bool
    problem_summary: str
    # ScopingVector dimensions (ADR-0007), flat here like the rest of this
    # schema -- re-extracted from the full transcript every turn, same as a
    # pill answer used to fill services_of_interest before. DiagnosisService.
    # _preview assembles these into a ScopingVector for DiagnosisPreview.
    solution_kinds: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)
    ai_shape: str | None = None
    data_mode: str | None = None
    auth_mode: str | None = None
    novelty: str | None = None
    design_load: str | None = None
    compliance: list[str] = Field(default_factory=list)
    engagement: str | None = None
    rush: str | None = None
    budget_ceiling: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    company_name: str | None = None
    cnpj: str | None = None
    # Structured business profile the concierge fills opportunistically as the
    # conversation reveals it -- surfaced live as editable chips + the
    # "X de N perguntas" counter on the Fluxo Cotação IA chat (canvas screen
    # 1c). All optional: a null/empty field simply renders no chip. `is_legal_
    # entity` drives whether the 1e contact form shows an "empresa" field.
    is_legal_entity: bool | None = None
    business_segment: str | None = None
    daily_volume: str | None = None
    pain_points: list[str] = Field(default_factory=list)
    scope_modules: list[str] = Field(default_factory=list)
    # City/UF of the business when stated ("Curitiba PR") -- feeds the live
    # dossiê subtitle (canvas screen 2a).
    city: str | None = None
    # 0-4 short numbers the visitor stated about the business (volume, headcount,
    # ...) -- the "números do negócio" stat cards in the dossiê. Keep the list
    # empty when nothing quantitative was said; never invent a figure.
    business_metrics: list[BusinessMetric] = Field(default_factory=list)
    # Which field the concierge should collect next as tappable options, and a
    # short question to show above them. The option list itself is NOT taken
    # from the LLM -- DiagnosisService expands `next_step_field` against a fixed
    # catalog (see _SCOPING_CATALOG) so ids/labels stay stable and the extraction
    # schema stays small. "none" while the conversation still flows freely.
    next_step_field: NextStepField = "none"
    next_step_prompt: str | None = None
    # 0, 2 or 3 paths the concierge proposes once the problem + scale/channel
    # are understood (ADR-0004). Empty while still qualifying. butter_mind
    # sanitizes and keys these in _sanitize_options.
    proposed_options: list[ProductOptionDraft] = Field(default_factory=list)


class NextStepOption(BaseModel):
    """One tappable option in a qualification turn. `id` is stable
    (snake_case, from _SCOPING_CATALOG); `label` is the pt-BR text to render."""

    id: str
    label: str


class NextStep(BaseModel):
    """Structured "pick one/some of these" block attached to a turn's preview.
    Built server-side from _SCOPING_CATALOG -- the browser only renders it.
    `allow_free_text` stays true so the composer never disappears mid-chat."""

    prompt: str
    field: NextStepField
    selection_mode: Literal["single", "multi"]
    allow_free_text: bool = True
    options: list[NextStepOption]


class BusinessProfile(BaseModel):
    """The structured slice of the conversation the chat surfaces live as
    editable chips while qualifying (Fluxo Cotação IA, canvas screen 1c).
    Every field is optional -- the chip row only renders what is known."""

    company_name: str | None = None
    is_legal_entity: bool | None = None
    segment: str | None = None
    city: str | None = None
    volume: str | None = None
    metrics: list[BusinessMetric] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    scope_modules: list[str] = Field(default_factory=list)
    contact_ready: bool = False


class QualificationProgress(BaseModel):
    """"X de N perguntas" shown in the chat header while qualifying (canvas
    screen 1c). `answered` counts the qualification checkpoints already
    covered by the conversation; `total` is the fixed checkpoint count."""

    answered: int
    total: int


class DiagnosisPreview(BaseModel):
    """Safe, client-facing preview of the current diagnosis."""

    problem_summary: str
    # ADR-0007: renamed from services_of_interest -- a light label taxonomy,
    # kept for display; the real cost drivers live in `scoping_vector`.
    solution_kinds: list[str]
    # budget_range/timeline stay named this way for the client (draft-quote
    # overrides, dossiê stat cards) but now mirror the chosen option's
    # figures, or the ScopingVector's budget_ceiling/rush labels -- never a
    # question answered directly (ADR-0007).
    budget_range: str | None = None
    timeline: str | None = None
    missing_information: list[str]
    grounding_status: str
    # Present only during qualification (not once ready_to_submit). Null =
    # render just the composer, same as before this field existed.
    next_step: NextStep | None = None
    # Live qualification state for the chat's chip row + progress counter
    # (canvas screen 1c). Always present; older clients simply ignore them.
    business_profile: BusinessProfile = Field(default_factory=BusinessProfile)
    progress: QualificationProgress
    # ADR-0004: which stage the conversation is in, the 2-3 proposed paths
    # (or the single chosen one once selected), the chosen key, and which
    # required business-profile fields are still blank.
    stage: DiagnosisStage = "qualifying"
    options: list[ProductOption] = Field(default_factory=list)
    selected_option_key: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    # ADR-0007: the full structured scope, recomputed from the extraction
    # every turn (not persisted until slice 02). solution_kinds/budget_range/
    # timeline above are the display-friendly slices of this same vector.
    scoping_vector: ScopingVector = Field(default_factory=ScopingVector)
    # The fixed option catalog for every _SCOPING_CATALOG dimension (plus the
    # business_type/problem_area warm-up questions). Sent so the browser
    # renders from one source instead of a hardcoded copy that drifts from
    # _SCOPING_CATALOG. Keys match ScopingVector's field names (solution_kinds,
    # integrations, surfaces, ai_shape, data_mode, auth_mode, novelty,
    # design_load, compliance, engagement, rush, budget_ceiling) plus
    # business_type/problem_area. Always present.
    field_options: dict[str, list[NextStepOption]] = Field(default_factory=dict)


class DiagnosisTurnResponse(BaseModel):
    message: DiagnosisMessageRead
    ready_to_submit: bool
    preview: DiagnosisPreview | None = None


class SelectOptionRequest(BaseModel):
    """POST /diagnosis/sessions/{id}/select-option -- the visitor picked one of
    the proposed paths (ADR-0004)."""

    option_key: str


class BusinessProfilePatch(BaseModel):
    """PATCH /diagnosis/sessions/{id}/business-profile -- partial merge of the
    business-profile fields the collecting step asks for (ADR-0004). Any field
    omitted is left untouched; an explicit null clears it."""

    model_config = ConfigDict(extra="forbid")

    business_name: str | None = None
    segment: str | None = None
    city: str | None = None
    volume: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class DiagnosisSubmitRequest(BaseModel):
    """Optional body for POST /diagnosis/sessions/{id}/submit -- last-chance
    overrides for the chosen path and the business profile (ADR-0004)."""

    selected_option_key: str | None = None
    business_profile: BusinessProfilePatch | None = None


class DiagnosisRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    diagnosis_session_id: uuid.UUID
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    company_name: str | None
    cnpj: str | None
    problem_summary: str
    services_of_interest: list[str]
    budget_range: str | None
    timeline: str | None
    status: str
    possibly_ungrounded: bool
    selected_option_key: str | None = None
    business_profile: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class DiagnosisTurnMetricsRead(BaseModel):
    """One assistant turn's grounding/token metrics -- see
    docs/mapa-chat-widget-metricas-tokens.md §2.2b. Meant to back an admin
    view of a session before approving the quote it produced.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assistant_message_id: uuid.UUID
    chunks_retrieved: list[dict[str, str | float]]
    chunks_used_count: int
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    model: str | None
    created_at: datetime


class DiagnosisGovernanceRead(BaseModel):
    diagnosis_max_output_tokens: int
    diagnosis_max_history_messages: int
    diagnosis_max_turns: int
    diagnosis_grounding_top_k: int
    diagnosis_grounding_min_score: float
    uses_runtime_override: bool
    maritaca_model: str
    embeddings_model_name: str


class DiagnosisGovernanceUpdate(BaseModel):
    diagnosis_max_output_tokens: int = Field(ge=128, le=4096)
    diagnosis_max_history_messages: int = Field(ge=2, le=50)
    diagnosis_max_turns: int = Field(ge=1, le=100)
    diagnosis_grounding_top_k: int = Field(ge=1, le=10)
    diagnosis_grounding_min_score: float = Field(ge=0, le=1)


class DiagnosisModelUsageRead(BaseModel):
    model: str | None
    turns: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    turns_without_token_usage: int


class MindDashboardOverviewRead(BaseModel):
    diagnosis_sessions: int
    sessions_in_progress: int
    submitted_requests: int
    possibly_ungrounded_requests: int
    assistant_turns: int
    grounded_turns: int
    turns_without_token_usage: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    knowledge_sources: int
    knowledge_chunks: int
    last_knowledge_update_at: datetime | None
    model_usage: list[DiagnosisModelUsageRead]
