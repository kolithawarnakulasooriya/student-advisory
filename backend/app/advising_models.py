"""Publication, grounded chat, human guidance, and local job records."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class EmbeddingConfig(Base):
    __tablename__ = "embedding_configs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    fingerprint: Mapped[str] = mapped_column(unique=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dimension: Mapped[int] = mapped_column(default=768)


class KnowledgeState(Base):
    __tablename__ = "knowledge_states"
    id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), primary_key=True)
    version: Mapped[int] = mapped_column(default=0)
    config_id: Mapped[UUID | None] = mapped_column(ForeignKey("embedding_configs.id"))


class IndexBuild(Base):
    __tablename__ = "index_builds"
    __table_args__ = (UniqueConstraint("source_version_id", "config_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_version_id: Mapped[UUID] = mapped_column(ForeignKey("source_versions.id"))
    config_id: Mapped[UUID] = mapped_column(ForeignKey("embedding_configs.id"))
    state: Mapped[str] = mapped_column(default="queued")
    error_code: Mapped[str | None]
    reviewed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    review_reason: Mapped[str]
    chunk_count: Mapped[int] = mapped_column(default=0)


class EvidenceChunk(Base):
    __tablename__ = "evidence_chunks"
    __table_args__ = (
        UniqueConstraint("build_id", "ordinal"),
        Index(
            "chunks_text_search",
            text("to_tsvector('english'::regconfig,text)"),
            postgresql_using="gin",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    build_id: Mapped[UUID] = mapped_column(ForeignKey("index_builds.id"))
    ordinal: Mapped[int]
    source_version_id: Mapped[UUID] = mapped_column(ForeignKey("source_versions.id"))
    text: Mapped[str]
    locator: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str]
    token_count: Mapped[int]
    embedding: Mapped[list[float]] = mapped_column(Vector(768))


class SourcePublication(Base):
    __tablename__ = "source_publications"
    id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    build_id: Mapped[UUID] = mapped_column(ForeignKey("index_builds.id"))
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(default="published")
    publisher_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str]
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PublicationEvent(Base):
    __tablename__ = "publication_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    build_id: Mapped[UUID] = mapped_column(ForeignKey("index_builds.id"))
    version: Mapped[int]
    action: Mapped[str]
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndexRelease(Base):
    __tablename__ = "index_releases"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    config_id: Mapped[UUID] = mapped_column(ForeignKey("embedding_configs.id"))
    version: Mapped[int]
    manifest: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GovernanceVersion(Base):
    __tablename__ = "governance_versions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    org_unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("org_units.id"))
    kind: Mapped[str]
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GovernanceActivation(Base):
    __tablename__ = "governance_activations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    governance_id: Mapped[UUID] = mapped_column(ForeignKey("governance_versions.id"))
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    org_unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("org_units.id"))
    kind: Mapped[str]
    version: Mapped[int]
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GovernanceEvaluation(Base):
    __tablename__ = "governance_evaluations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    governance_id: Mapped[UUID] = mapped_column(ForeignKey("governance_versions.id"))
    fingerprint: Mapped[str]
    dataset_hash: Mapped[str]
    passed: Mapped[bool]
    results: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    student_membership_id: Mapped[UUID] = mapped_column(ForeignKey("student_memberships.id"))
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    org_unit_id: Mapped[UUID] = mapped_column(ForeignKey("org_units.id"))
    version: Mapped[int] = mapped_column(default=1)
    guidance_epoch: Mapped[int] = mapped_column(default=0)
    title: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StudentMessage(Base):
    __tablename__ = "student_messages"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdvisorGuidance(Base):
    __tablename__ = "advisor_guidance"
    __table_args__ = (
        Index(
            "one_guidance_successor",
            "supersedes_id",
            unique=True,
            postgresql_where=text("supersedes_id IS NOT NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str]
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("advisor_guidance.id"))
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StaffNote(Base):
    __tablename__ = "staff_notes"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdvisingJob(Base):
    __tablename__ = "advising_jobs"
    __table_args__ = (UniqueConstraint("message_id", "attempt", "kind"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[str]
    target_id: Mapped[UUID]
    student_membership_id: Mapped[UUID | None] = mapped_column(ForeignKey("student_memberships.id"))
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("conversations.id"))
    message_id: Mapped[UUID | None] = mapped_column(ForeignKey("student_messages.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    grant_epoch: Mapped[int]
    purpose: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    attempt: Mapped[int] = mapped_column(default=1)
    state: Mapped[str] = mapped_column(default="queued")
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_code: Mapped[str | None]
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ValidatedAnswer(Base):
    __tablename__ = "validated_answers"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("advising_jobs.id"), unique=True)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"))
    message_id: Mapped[UUID] = mapped_column(ForeignKey("student_messages.id"))
    disposition: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdvisorDraft(Base):
    __tablename__ = "advisor_drafts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("advising_jobs.id"), unique=True)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RetrievalTrace(Base):
    __tablename__ = "retrieval_traces"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("advising_jobs.id"), unique=True)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdvisingCase(Base):
    __tablename__ = "advising_cases"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    student_membership_id: Mapped[UUID] = mapped_column(ForeignKey("student_memberships.id"))
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("conversations.id"))
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    org_unit_id: Mapped[UUID] = mapped_column(ForeignKey("org_units.id"))
    status: Mapped[str] = mapped_column(default="open")
    version: Mapped[int] = mapped_column(default=1)
    reason: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseEvent(Base):
    __tablename__ = "case_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("advising_cases.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str]
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
