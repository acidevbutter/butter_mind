import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DiagnosisSession(Base):
    __tablename__ = "diagnosis_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(default="in_progress")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DiagnosisMessage(Base):
    __tablename__ = "diagnosis_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    diagnosis_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagnosis_sessions.id"), index=True
    )
    role: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    # `list_recent_messages` orders by this column with a LIMIT to build the
    # fixed-size history window (see docs/mapa-chat-widget-metricas-tokens.md
    # §2.3) -- a server-side default (func.now()) is only second-precision
    # under SQLite, so several messages added within the same wall-clock
    # second (routine in tests, and possible in production under fast
    # successive turns) tie and sort arbitrarily, which can make the "recent"
    # window return the OLDEST messages instead. A Python-side default has
    # microsecond precision, so sequential inserts never tie.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )


class DiagnosisRequest(Base):
    __tablename__ = "diagnosis_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    diagnosis_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagnosis_sessions.id"))
    contact_name: Mapped[str | None]
    contact_email: Mapped[str | None]
    contact_phone: Mapped[str | None]
    company_name: Mapped[str | None]
    cnpj: Mapped[str | None]
    problem_summary: Mapped[str] = mapped_column(Text)
    services_of_interest: Mapped[list[str]] = mapped_column(JSON, default=list)
    budget_range: Mapped[str | None]
    timeline: Mapped[str | None]
    raw_transcript_snapshot: Mapped[list[dict[str, str]] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default="new")
    # Simplified anti-hallucination signal (see docs/mapa-chat-widget-metricas-tokens.md
    # §2.2b): true only when NO turn in the whole session ever retrieved a
    # knowledge-base chunk -- a session-level "this ran with zero grounding"
    # flag, not per-field fact-checking against the transcript. Meant to tell
    # Marcos "review this one more carefully" in the approval queue, not to
    # block anything automatically.
    possibly_ungrounded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("diagnosis_session_id"),)


class DiagnosisTurnMetrics(Base):
    """One row per assistant reply in a diagnosis session -- structured,
    queryable metrics (not just log text) so grounding/token usage can be
    reviewed per turn instead of trusted blindly. See
    docs/mapa-chat-widget-metricas-tokens.md §2.2b.
    """

    __tablename__ = "diagnosis_turn_metrics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    diagnosis_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagnosis_sessions.id"), index=True
    )
    assistant_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagnosis_messages.id"))
    # [{"chunk_id": "...", "score": 0.83}, ...] -- the chunks retrieved and
    # injected into the prompt for this turn, in score order.
    chunks_retrieved: Mapped[list[dict[str, str | float]]] = mapped_column(JSON, default=list)
    chunks_used_count: Mapped[int] = mapped_column(default=0)
    input_tokens: Mapped[int | None]
    cached_input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    model: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DiagnosisRuntimeSettings(Base):
    """Safe diagnosis limits overridden from the private admin."""

    __tablename__ = "diagnosis_runtime_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    diagnosis_max_output_tokens: Mapped[int]
    diagnosis_max_history_messages: Mapped[int]
    diagnosis_max_turns: Mapped[int]
    diagnosis_grounding_top_k: Mapped[int]
    diagnosis_grounding_min_score: Mapped[float]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
