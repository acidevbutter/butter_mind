import uuid
from datetime import datetime

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DiagnosisRequest(Base):
    __tablename__ = "diagnosis_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    diagnosis_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diagnosis_sessions.id"))
    contact_name: Mapped[str | None]
    contact_email: Mapped[str | None]
    contact_phone: Mapped[str | None]
    company_name: Mapped[str | None]
    problem_summary: Mapped[str] = mapped_column(Text)
    services_of_interest: Mapped[list] = mapped_column(JSON, default=list)
    budget_range: Mapped[str | None]
    timeline: Mapped[str | None]
    raw_transcript_snapshot: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("diagnosis_session_id"),)
