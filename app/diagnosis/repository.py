import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.diagnosis.models import DiagnosisMessage, DiagnosisRequest, DiagnosisSession
from app.diagnosis.schemas import DiagnosisSessionCreate


class DiagnosisRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(self, payload: DiagnosisSessionCreate) -> DiagnosisSession:
        diagnosis_session = DiagnosisSession(**payload.model_dump())
        self.session.add(diagnosis_session)
        await self.session.commit()
        await self.session.refresh(diagnosis_session)
        return diagnosis_session

    async def get_session(self, session_id: uuid.UUID) -> DiagnosisSession:
        diagnosis_session = await self.session.get(DiagnosisSession, session_id)
        if diagnosis_session is None:
            raise NotFoundError(f"Diagnosis session {session_id} not found")
        return diagnosis_session

    async def list_messages(self, diagnosis_session_id: uuid.UUID) -> list[DiagnosisMessage]:
        result = await self.session.execute(
            select(DiagnosisMessage)
            .where(DiagnosisMessage.diagnosis_session_id == diagnosis_session_id)
            .order_by(DiagnosisMessage.created_at)
        )
        return list(result.scalars().all())

    async def add_message(
        self, *, diagnosis_session_id: uuid.UUID, role: str, content: str
    ) -> DiagnosisMessage:
        message = DiagnosisMessage(diagnosis_session_id=diagnosis_session_id, role=role, content=content)
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def mark_completed(self, diagnosis_session: DiagnosisSession) -> None:
        diagnosis_session.status = "completed"
        await self.session.commit()

    async def create_request(self, **fields) -> DiagnosisRequest:
        diagnosis_request = DiagnosisRequest(**fields)
        self.session.add(diagnosis_request)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(
                f"A diagnosis request already exists for session {fields.get('diagnosis_session_id')!r}"
            ) from exc
        await self.session.refresh(diagnosis_request)
        return diagnosis_request

    async def list_requests(self) -> list[DiagnosisRequest]:
        result = await self.session.execute(
            select(DiagnosisRequest).order_by(DiagnosisRequest.created_at.desc())
        )
        return list(result.scalars().all())
