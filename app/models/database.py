import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship

from app.orchestrator.state_machine import SessionState

Base = declarative_base()


def utcnow():
    return datetime.now(UTC)


class Tenant(Base):
    """Изолированный профиль компании-клиента."""
    __tablename__ = "tenants"

    tenant_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    display_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    settings_revision = Column(String)


class Session(Base):
    """История вызовов и сессий."""
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    status = Column(SQLEnum(SessionState), default=SessionState.CREATED)
    channel = Column(String, nullable=False)
    language = Column(String, default="ru")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")


class Turn(Base):
    """Отдельные ходы диалога внутри сессии."""
    __tablename__ = "turns"

    turn_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.session_id"), nullable=False, index=True)
    sequence_no = Column(String, nullable=False)
    started_at = Column(DateTime(timezone=True), default=utcnow)

    # Храним маскированный текст по умолчанию для безопасности
    redacted_text = Column(String, nullable=True)
    intent = Column(String, nullable=True)
    confidence = Column(String, nullable=True)

    session = relationship("Session")


class AuditEvent(Base):
    """Журнал аудита для доступа к транскриптам и изменения настроек[cite: 1]."""
    __tablename__ = "audit_events"

    event_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, index=True)
    actor = Column(String, nullable=False)
    action = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow)
    details = Column(JSON, nullable=True)


class RetrievalEvent(Base):
    """Session-side retrieval audit row (SSOT §8.3). No raw query text."""
    __tablename__ = "retrieval_events"

    event_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    turn_id = Column(String, ForeignKey("turns.turn_id"), nullable=False, index=True)
    session_id = Column(String, nullable=False)
    tenant_id = Column(String, nullable=False, index=True)
    index_revision = Column(String, nullable=True)
    retrieval_mode = Column(String, nullable=True)
    config_version = Column(String, nullable=True)
    evidence_status = Column(String, nullable=True)
    outcome = Column(String, nullable=False)
    error_code = Column(String, nullable=True)
    query_sha256 = Column(String, nullable=False)
    query_chars = Column(Integer, nullable=False)
    applied_filters = Column(JSON, nullable=True)
    candidates = Column(JSON, nullable=True)
    selected_source_ids = Column(JSON, nullable=True)
    cited_source_ids = Column(JSON, nullable=True)
    conflict_chunk_ids = Column(JSON, nullable=True)
    excluded_counts = Column(JSON, nullable=True)
    degraded = Column(JSON, nullable=True)
    top_score = Column(Float, nullable=True)
    outdated_matches = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    turn = relationship("Turn")