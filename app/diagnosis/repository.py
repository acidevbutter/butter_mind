import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.diagnosis.models import (
    DiagnosisMessage,
    DiagnosisRequest,
    DiagnosisSession,
    DiagnosisTurnMetrics,
)
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

    async def list_recent_messages(
        self, diagnosis_session_id: uuid.UUID, *, limit: int
    ) -> list[DiagnosisMessage]:
        """The last `limit` messages, oldest first -- the fixed-size window sent
        to the LLM each turn instead of the full transcript (see
        docs/mapa-chat-widget-metricas-tokens.md §2.3).
        """
        result = await self.session.execute(
            select(DiagnosisMessage)
            .where(DiagnosisMessage.diagnosis_session_id == diagnosis_session_id)
            .order_by(DiagnosisMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def count_user_messages(self, diagnosis_session_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(DiagnosisMessage)
            .where(
                DiagnosisMessage.diagnosis_session_id == diagnosis_session_id,
                DiagnosisMessage.role == "user",
            )
        )
        return result.scalar_one()

    async def add_message(
        self, *, diagnosis_session_id: uuid.UUID, role: str, content: str
    ) -> DiagnosisMessage:
        message = DiagnosisMessage(
            diagnosis_session_id=diagnosis_session_id, role=role, content=content
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def add_turn_metrics(self, **fields: object) -> DiagnosisTurnMetrics:
        metrics = DiagnosisTurnMetrics(**fields)
        self.session.add(metrics)
        await self.session.commit()
        await self.session.refresh(metrics)
        return metrics

    async def list_turn_metrics(
        self, diagnosis_session_id: uuid.UUID
    ) -> list[DiagnosisTurnMetrics]:
        result = await self.session.execute(
            select(DiagnosisTurnMetrics)
            .where(DiagnosisTurnMetrics.diagnosis_session_id == diagnosis_session_id)
            .order_by(DiagnosisTurnMetrics.created_at)
        )
        return list(result.scalars().all())

    async def mark_completed(self, diagnosis_session: DiagnosisSession) -> None:
        diagnosis_session.status = "completed"
        await self.session.commit()

    async def create_request(self, **fields: object) -> DiagnosisRequest:
        diagnosis_request = DiagnosisRequest(**fields)
        self.session.add(diagnosis_request)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            session_id = fields.get('diagnosis_session_id')
            raise ConflictError(
                f"A diagnosis request already exists for session {session_id!r}"
            ) from exc
        await self.session.refresh(diagnosis_request)
        return diagnosis_request

    async def list_requests(self) -> list[DiagnosisRequest]:
        result = await self.session.execute(
            select(DiagnosisRequest).order_by(DiagnosisRequest.created_at.desc())
        )
        return list(result.scalars().all())
