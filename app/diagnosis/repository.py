import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.diagnosis.models import (
    DiagnosisMessage,
    DiagnosisRequest,
    DiagnosisRuntimeSettings,
    DiagnosisSession,
    DiagnosisTurnMetrics,
)
from app.diagnosis.schemas import DiagnosisSessionCreate
from app.knowledge.models import KnowledgeChunk, KnowledgeSource


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

    async def get_runtime_settings(self) -> DiagnosisRuntimeSettings | None:
        return await self.session.get(DiagnosisRuntimeSettings, 1)

    async def save_runtime_settings(
        self,
        *,
        diagnosis_max_output_tokens: int,
        diagnosis_max_history_messages: int,
        diagnosis_max_turns: int,
        diagnosis_grounding_top_k: int,
        diagnosis_grounding_min_score: float,
    ) -> DiagnosisRuntimeSettings:
        runtime_settings = await self.get_runtime_settings()
        values = {
            "diagnosis_max_output_tokens": diagnosis_max_output_tokens,
            "diagnosis_max_history_messages": diagnosis_max_history_messages,
            "diagnosis_max_turns": diagnosis_max_turns,
            "diagnosis_grounding_top_k": diagnosis_grounding_top_k,
            "diagnosis_grounding_min_score": diagnosis_grounding_min_score,
        }
        if runtime_settings is None:
            runtime_settings = DiagnosisRuntimeSettings(id=1, **values)
            self.session.add(runtime_settings)
        else:
            for key, value in values.items():
                setattr(runtime_settings, key, value)
        await self.session.commit()
        await self.session.refresh(runtime_settings)
        return runtime_settings

    async def dashboard_data(self) -> dict[str, object]:
        session_count = await self.session.scalar(
            select(func.count()).select_from(DiagnosisSession)
        )
        in_progress_count = await self.session.scalar(
            select(func.count())
            .select_from(DiagnosisSession)
            .where(DiagnosisSession.status == "in_progress")
        )
        request_count = await self.session.scalar(
            select(func.count()).select_from(DiagnosisRequest)
        )
        ungrounded_request_count = await self.session.scalar(
            select(func.count())
            .select_from(DiagnosisRequest)
            .where(DiagnosisRequest.possibly_ungrounded.is_(True))
        )
        source_count = await self.session.scalar(
            select(func.count()).select_from(KnowledgeSource)
        )
        chunk_count = await self.session.scalar(select(func.count()).select_from(KnowledgeChunk))
        last_knowledge_update_at = await self.session.scalar(
            select(func.max(KnowledgeChunk.created_at))
        )
        metrics_result = await self.session.execute(select(DiagnosisTurnMetrics))
        return {
            "diagnosis_sessions": session_count or 0,
            "sessions_in_progress": in_progress_count or 0,
            "submitted_requests": request_count or 0,
            "possibly_ungrounded_requests": ungrounded_request_count or 0,
            "knowledge_sources": source_count or 0,
            "knowledge_chunks": chunk_count or 0,
            "last_knowledge_update_at": last_knowledge_update_at,
            "turn_metrics": list(metrics_result.scalars().all()),
        }

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
