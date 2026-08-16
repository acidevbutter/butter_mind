import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import DbSession, LLMProviderDep, RequireInternalApiKey
from app.diagnosis.repository import DiagnosisRepository
from app.diagnosis.schemas import (
    DiagnosisMessageCreate,
    DiagnosisMessageRead,
    DiagnosisRequestRead,
    DiagnosisSessionCreate,
    DiagnosisSessionRead,
    DiagnosisTurnResponse,
)
from app.diagnosis.service import DiagnosisService

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


def get_diagnosis_service(db: DbSession, llm_provider: LLMProviderDep) -> DiagnosisService:
    return DiagnosisService(DiagnosisRepository(db), llm_provider)


DiagnosisServiceDep = Annotated[DiagnosisService, Depends(get_diagnosis_service)]


@router.post(
    "/sessions", response_model=DiagnosisSessionRead,
    status_code=status.HTTP_201_CREATED, summary="Start a guided diagnosis session",
)
async def create_session(payload: DiagnosisSessionCreate, service: DiagnosisServiceDep) -> DiagnosisSessionRead:
    diagnosis_session = await service.create_session(payload)
    return DiagnosisSessionRead.model_validate(diagnosis_session)


@router.post(
    "/sessions/{session_id}/messages", response_model=DiagnosisTurnResponse,
    status_code=status.HTTP_201_CREATED, summary="Send a message in the guided diagnosis flow",
)
async def send_message(
    session_id: uuid.UUID, payload: DiagnosisMessageCreate, service: DiagnosisServiceDep
) -> DiagnosisTurnResponse:
    message, ready_to_submit = await service.send_message(session_id=session_id, content=payload.content)
    return DiagnosisTurnResponse(
        message=DiagnosisMessageRead.model_validate(message), ready_to_submit=ready_to_submit
    )


@router.post(
    "/sessions/{session_id}/submit", response_model=DiagnosisRequestRead,
    status_code=status.HTTP_201_CREATED, summary="Finalize the session into a diagnosis request (lead)",
)
async def submit(
    session_id: uuid.UUID,
    service: DiagnosisServiceDep,
    contact_name: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    company_name: str | None = None,
) -> DiagnosisRequestRead:
    diagnosis_request = await service.submit(
        session_id=session_id,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        company_name=company_name,
    )
    return DiagnosisRequestRead.model_validate(diagnosis_request)


@router.get(
    "/requests", response_model=list[DiagnosisRequestRead],
    summary="List diagnosis requests (internal)", dependencies=[RequireInternalApiKey],
)
async def list_requests(service: DiagnosisServiceDep) -> list[DiagnosisRequestRead]:
    requests = await service.list_requests()
    return [DiagnosisRequestRead.model_validate(r) for r in requests]
