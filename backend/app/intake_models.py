"""Release 0.3 heads and immutable academic/source snapshots."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class OnboardingConfig(Base):
    __tablename__ = "onboarding_configs"
    id: Mapped[UUID] = mapped_column(ForeignKey("org_units.id"), primary_key=True)
    version: Mapped[int] = mapped_column(default=0)
    active_schema_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("onboarding_schemas.id", use_alter=True, name="active_onboarding_schema")
    )


class OnboardingSchema(Base):
    __tablename__ = "onboarding_schemas"
    __table_args__ = (UniqueConstraint("org_unit_id", "version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    org_unit_id: Mapped[UUID] = mapped_column(ForeignKey("org_units.id"))
    version: Mapped[int]
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AcademicProfile(Base):
    __tablename__ = "academic_profiles"
    id: Mapped[UUID] = mapped_column(ForeignKey("student_memberships.id"), primary_key=True)
    version: Mapped[int] = mapped_column(default=0)


class ProfileVersion(Base):
    __tablename__ = "profile_versions"
    __table_args__ = (UniqueConstraint("student_membership_id", "version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    student_membership_id: Mapped[UUID] = mapped_column(ForeignKey("student_memberships.id"))
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    org_unit_id: Mapped[UUID] = mapped_column(ForeignKey("org_units.id"))
    version: Mapped[int]
    schema_id: Mapped[UUID] = mapped_column(ForeignKey("onboarding_schemas.id"))
    status: Mapped[str]
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reviews: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    org_unit_id: Mapped[UUID | None] = mapped_column(ForeignKey("org_units.id"))
    student_membership_id: Mapped[UUID | None] = mapped_column(ForeignKey("student_memberships.id"))
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    visibility: Mapped[str]
    version: Mapped[int] = mapped_column(default=0)
    archived: Mapped[bool] = mapped_column(default=False)


class SourceVersion(Base):
    __tablename__ = "source_versions"
    __table_args__ = (UniqueConstraint("source_id", "version"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    version: Mapped[int]
    filename: Mapped[str]
    media_type: Mapped[str]
    content_hash: Mapped[str]
    object_key: Mapped[str]
    metadata_fields: Mapped[dict[str, Any]] = mapped_column(JSONB)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (UniqueConstraint("source_version_id", "attempt"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_version_id: Mapped[UUID] = mapped_column(ForeignKey("source_versions.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    grant_epoch: Mapped[int]
    relationship_epoch: Mapped[int | None]
    purpose: Mapped[str]
    attempt: Mapped[int] = mapped_column(default=1)
    state: Mapped[str] = mapped_column(default="uploaded")
    error_code: Mapped[str | None]
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExtractionArtifact(Base):
    __tablename__ = "extraction_artifacts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_version_id: Mapped[UUID] = mapped_column(ForeignKey("source_versions.id"), unique=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_jobs.id"))
    object_key: Mapped[str]
    extractor_version: Mapped[str]
    ocr: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
