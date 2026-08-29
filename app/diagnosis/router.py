import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.core.dependencies import (
    DbSession,
    EmbeddingsProviderDep,
    LLMProviderDep,
    RequireInternalApiKey,
    RequireServiceApiKey,
)
from app.diagnosis.repository import DiagnosisRepository
from app.diagnosis.schemas import (
    DiagnosisGovernanceRead,
    DiagnosisGovernanceUpdate,
    DiagnosisMessageCreate,
    DiagnosisMessageRead,
    DiagnosisPreview,
    DiagnosisRequestRead,
    DiagnosisSessionCreate,
    DiagnosisSessionRead,
    DiagnosisTurnMetricsRead,
    DiagnosisTurnResponse,
    MindDashboardOverviewRead,
)
from app.diagnosis.service import DiagnosisService
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeIngestionService
from app.llm_usage.repository import LLMUsageRepository
from app.llm_usage.service import LLMUsageService

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


def get_diagnosis_service(
    db: DbSession, llm_provider: LLMProviderDep, embeddings_provider: EmbeddingsProviderDep
) -> DiagnosisService:
    knowledge_service = KnowledgeIngestionService(KnowledgeRepository(db), embeddings_provider)
    return DiagnosisService(
        DiagnosisRepository(db), llm_provider, knowledge_service, LLMUsageService(LLMUsageRepository(db))
    )


DiagnosisServiceDep = Annotated[DiagnosisService, Depends(get_diagnosis_service)]


@router.post(
    "/sessions", response_model=DiagnosisSessionRead,
    status_code=status.HTTP_201_CREATED, summary="Start a guided diagnosis session",
    dependencies=[RequireServiceApiKey],
    description=(
        "Creates a new guided diagnosis session that walks a prospect through a structured "
        "set of questions. Use this to kick off a lead-qualification flow, e.g. a visitor "
        "starting a 'get a project diagnosis' form on the site."
    ),
)
async def create_session(
    payload: DiagnosisSessionCreate, service: DiagnosisServiceDep
) -> DiagnosisSessionRead:
    diagnosis_session = await service.create_session(payload)
    return DiagnosisSessionRead.model_validate(diagnosis_session)


@router.post(
    "/sessions/{session_id}/messages", response_model=DiagnosisTurnResponse,
    status_code=status.HTTP_201_CREATED, summary="Send a message in the guided diagnosis flow",
    dependencies=[RequireServiceApiKey],
    description=(
        "Sends the visitor's answer to the diagnosis session, advances the guided "
        "conversation via the LLM, and reports whether enough information has been "
        "gathered to submit. Use this for each turn of the diagnosis Q&A, e.g. the "
        "visitor answering 'what's your budget?' in the flow."
    ),
)
async def send_message(
    session_id: uuid.UUID, payload: DiagnosisMessageCreate, service: DiagnosisServiceDep
) -> DiagnosisTurnResponse:
    message, ready_to_submit, preview = await service.send_message(
        session_id=session_id, content=payload.content
    )
    return DiagnosisTurnResponse(
        message=DiagnosisMessageRead.model_validate(message),
        ready_to_submit=ready_to_submit,
        preview=DiagnosisPreview.model_validate(preview),
    )


@router.post(
    "/sessions/{session_id}/messages/stream",
    summary="Send a message in the guided diagnosis flow, streaming the reply (SSE)",
    dependencies=[RequireServiceApiKey],
    description=(
        "Requires the X-Service-Api-Key header (called only by devbutter_backend, never "
        "the browser directly). Sends the visitor's answer, then streams the assistant's "
        "reply as server-sent "
        "events: one `{\"type\": \"delta\", \"content\": ...}` line per text chunk as it "
        "comes off the LLM, followed by a final `{\"type\": \"done\", \"ready_to_submit\": "
        "..., \"message_id\": ...}` once the full reply has been persisted and extracted."
    ),
)
async def send_message_stream(
    session_id: uuid.UUID, payload: DiagnosisMessageCreate, service: DiagnosisServiceDep
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for event in service.stream_message(session_id=session_id, content=payload.content):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post(
    "/sessions/{session_id}/submit", response_model=DiagnosisRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Finalize the session into a diagnosis request (lead)",
    dependencies=[RequireServiceApiKey],
    description=(
        "Closes out a diagnosis session and converts it into a stored lead. Contact details "
        "(name, email, phone, company, cnpj) are pulled from the conversation's own "
        "extraction, not passed in here -- the guided flow asks for them naturally. Use this "
        "once the guided flow is complete and the visitor wants to submit their info, e.g. "
        "the final 'send me my diagnosis' step that hands the lead off to sales."
    ),
)
async def submit(session_id: uuid.UUID, service: DiagnosisServiceDep) -> DiagnosisRequestRead:
    diagnosis_request = await service.submit(session_id=session_id)
    return DiagnosisRequestRead.model_validate(diagnosis_request)


@router.get(
    "/sessions/{session_id}/turn-metrics", response_model=list[DiagnosisTurnMetricsRead],
    summary="List per-turn grounding/token metrics for a session (internal)",
    dependencies=[RequireInternalApiKey],
    description=(
        "Lists structured per-assistant-turn metrics for a diagnosis session: how many "
        "knowledge-base chunks were retrieved for grounding, and input/output token "
        "counts. Use this to power an admin view for spotting turns that answered with "
        "zero grounding (possibly hallucinated) before approving the quote it produced."
    ),
)
async def list_turn_metrics(
    session_id: uuid.UUID, service: DiagnosisServiceDep
) -> list[DiagnosisTurnMetricsRead]:
    metrics = await service.list_turn_metrics(session_id)
    return [DiagnosisTurnMetricsRead.model_validate(m) for m in metrics]


@router.get(
    "/requests", response_model=list[DiagnosisRequestRead],
    summary="List diagnosis requests (internal)", dependencies=[RequireInternalApiKey],
    description=(
        "Lists all submitted diagnosis requests (leads). Use this from an internal "
        "dashboard or CRM sync job to review and follow up on incoming leads. Requires "
        "the internal API key."
    ),
)
async def list_requests(service: DiagnosisServiceDep) -> list[DiagnosisRequestRead]:
    requests = await service.list_requests()
    return [DiagnosisRequestRead.model_validate(r) for r in requests]


@router.get(
    "/internal/dashboard/overview",
    response_model=MindDashboardOverviewRead,
    summary="Internal AI metrics dashboard overview",
    dependencies=[RequireInternalApiKey],
)
async def dashboard_overview(service: DiagnosisServiceDep) -> MindDashboardOverviewRead:
    return await service.dashboard_overview()


@router.get(
    "/internal/dashboard/settings",
    response_model=DiagnosisGovernanceRead,
    summary="Read effective diagnosis governance settings",
    dependencies=[RequireInternalApiKey],
)
async def get_dashboard_settings(service: DiagnosisServiceDep) -> DiagnosisGovernanceRead:
    return await service.get_governance()


@router.patch(
    "/internal/dashboard/settings",
    response_model=DiagnosisGovernanceRead,
    summary="Update safe diagnosis governance settings",
    dependencies=[RequireInternalApiKey],
)
async def update_dashboard_settings(
    payload: DiagnosisGovernanceUpdate, service: DiagnosisServiceDep
) -> DiagnosisGovernanceRead:
    return await service.update_governance(payload)
