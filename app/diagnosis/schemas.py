import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    services_of_interest: list[str]
    budget_range: str | None = None
    timeline: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    company_name: str | None = None
    cnpj: str | None = None


class DiagnosisPreview(BaseModel):
    """Safe, client-facing preview of the current diagnosis."""

    problem_summary: str
    services_of_interest: list[str]
    budget_range: str | None = None
    timeline: str | None = None
    missing_information: list[str]
    grounding_status: str


class DiagnosisTurnResponse(BaseModel):
    message: DiagnosisMessageRead
    ready_to_submit: bool
    preview: DiagnosisPreview | None = None


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
    output_tokens: int | None
    model: str | None
    created_at: datetime
