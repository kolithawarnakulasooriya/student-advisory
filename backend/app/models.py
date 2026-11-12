from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str]
    organization_epoch: Mapped[int] = mapped_column(default=1, server_default="1")


class OrgUnit(Base):
    __tablename__ = "org_units"
    __table_args__ = (
        UniqueConstraint("institution_id", "code"),
        UniqueConstraint("institution_id", "id"),
        ForeignKeyConstraint(
            ["institution_id", "parent_id"], ["org_units.institution_id", "org_units.id"]
        ),
        CheckConstraint("kind IN ('college', 'department')"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id"),
        CheckConstraint("status IN ('active','archived')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    parent_id: Mapped[UUID | None]
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str]
    kind: Mapped[str]
    timezone: Mapped[str] = mapped_column(default="America/Chicago")
    status: Mapped[str] = mapped_column(default="active", server_default="active")
    version: Mapped[int] = mapped_column(default=1, server_default="1")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("issuer", "subject"),
        CheckConstraint("status IN ('active','suspended','revoked')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    issuer: Mapped[str]
    subject: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(default="active")
    grant_epoch: Mapped[int] = mapped_column(Integer, default=1)


class RoleGrant(Base):
    __tablename__ = "role_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["institution_id", "org_unit_id"], ["org_units.institution_id", "org_units.id"]
        ),
        Index(
            "one_current_role",
            "user_id",
            "org_unit_id",
            "role",
            unique=True,
            postgresql_where=text("status IN ('active','pending','invited','suspended')"),
        ),
        UniqueConstraint(
            "id", "user_id", "institution_id", "org_unit_id", name="grant_membership_identity"
        ),
        CheckConstraint("capacity IS NULL OR capacity > 0"),
        CheckConstraint(
            "role IN ('student','advisor','secretary','manager','platform_admin','super_admin')"
        ),
        CheckConstraint(
            "status IN ('invited','pending','active','suspended','rejected','revoked')"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    institution_id: Mapped[UUID]
    org_unit_id: Mapped[UUID]
    role: Mapped[str]
    status: Mapped[str] = mapped_column(default="active")
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capabilities: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}"
    )
    ceiling: Mapped[str] = mapped_column(default="advisor", server_default="advisor")
    capacity: Mapped[int | None]
    version: Mapped[int] = mapped_column(default=1, server_default="1")


class LoginSession(Base):
    __tablename__ = "sessions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    auth_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa: Mapped[bool] = mapped_column(default=False)
    revoked: Mapped[bool] = mapped_column(default=False)


class Verification(Base):
    __tablename__ = "verifications"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(default=False)


class PlatformGrant(Base):
    __tablename__ = "platform_grants"
    __table_args__ = (
        Index(
            "one_platform_admin",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('active','suspended')"),
        ),
        CheckConstraint("status IN ('active','suspended','revoked')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(default="active")
    version: Mapped[int] = mapped_column(default=1)


class PlatformControl(Base):
    __tablename__ = "platform_control"
    id: Mapped[int] = mapped_column(primary_key=True)
    bootstrap_completed: Mapped[bool] = mapped_column(default=False)


class EnrollmentOption(Base):
    __tablename__ = "enrollment_options"
    id: Mapped[UUID] = mapped_column(ForeignKey("org_units.id"), primary_key=True)
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    label: Mapped[str]
    enabled: Mapped[bool] = mapped_column(default=False)


class StudentMembership(Base):
    __tablename__ = "student_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["grant_id", "user_id", "institution_id", "org_unit_id"],
            [
                "role_grants.id",
                "role_grants.user_id",
                "role_grants.institution_id",
                "role_grants.org_unit_id",
            ],
            name="student_grant_identity",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    grant_id: Mapped[UUID] = mapped_column(ForeignKey("role_grants.id"), unique=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    institution_id: Mapped[UUID]
    org_unit_id: Mapped[UUID]
    relationship_epoch: Mapped[int] = mapped_column(default=1)
    version: Mapped[int] = mapped_column(default=1)


class AdvisorAssignment(Base):
    __tablename__ = "advisor_assignments"
    __table_args__ = (
        Index(
            "one_primary_advisor",
            "student_membership_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    student_membership_id: Mapped[UUID] = mapped_column(ForeignKey("student_memberships.id"))
    advisor_grant_id: Mapped[UUID] = mapped_column(ForeignKey("role_grants.id"))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MembershipRequest(Base):
    __tablename__ = "membership_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["institution_id", "org_unit_id"], ["org_units.institution_id", "org_units.id"]
        ),
        Index(
            "one_pending_request",
            "user_id",
            "org_unit_id",
            "requested_role",
            unique=True,
            postgresql_where=text("status='pending'"),
        ),
        CheckConstraint("requested_role IN ('student','advisor','manager')"),
        CheckConstraint("status IN ('pending','approved','rejected')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    institution_id: Mapped[UUID]
    org_unit_id: Mapped[UUID] = mapped_column(ForeignKey("org_units.id"))
    requested_role: Mapped[str]
    justification: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")
    decision_reason: Mapped[str | None]
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["institution_id", "org_unit_id"], ["org_units.institution_id", "org_units.id"]
        ),
        Index(
            "one_pending_invite",
            "email",
            "org_unit_id",
            "role",
            unique=True,
            postgresql_where=text("status='pending'"),
        ),
        CheckConstraint("role IN ('student','advisor','secretary','manager')"),
        CheckConstraint("status IN ('pending','accepted','revoked','expired')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    institution_id: Mapped[UUID]
    org_unit_id: Mapped[UUID] = mapped_column(ForeignKey("org_units.id"))
    email: Mapped[str]
    role: Mapped[str]
    inviter_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    advisor_grant_id: Mapped[UUID | None] = mapped_column(ForeignKey("role_grants.id"))
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    nonce: Mapped[str]
    token_hash: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="pending")
    accepted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(default=1)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    actor_id: Mapped[UUID | None]
    action: Mapped[str]
    object_type: Mapped[str]
    object_id: Mapped[str | None]
    institution_id: Mapped[UUID | None]
    org_unit_id: Mapped[UUID | None]
    result: Mapped[str]
    reason_code: Mapped[str]
    correlation_id: Mapped[str]
    reason_id: Mapped[UUID | None] = mapped_column(ForeignKey("operational_reasons.id"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("actor_id", "route", "key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID]
    route: Mapped[str]
    key: Mapped[str]
    payload_hash: Mapped[str]
    grant_epoch: Mapped[int]
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_type: Mapped[str]
    aggregate_id: Mapped[UUID]
    aggregate_version: Mapped[int]
    schema_version: Mapped[int] = mapped_column(default=1)
    institution_id: Mapped[UUID]
    org_unit_id: Mapped[UUID | None]
    actor_id: Mapped[UUID]
    state: Mapped[str] = mapped_column(default="recorded")
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_error: Mapped[str | None]


class OperationalReason(Base):
    __tablename__ = "operational_reasons"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID]
    org_unit_id: Mapped[UUID | None]
    text: Mapped[str] = mapped_column(String(500))


class OrganizationAdminGrant(Base):
    __tablename__ = "organization_admin_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["institution_id", "root_org_unit_id"], ["org_units.institution_id", "org_units.id"]
        ),
        CheckConstraint("status IN ('active','suspended','revoked')"),
        CheckConstraint(
            "(scope_kind='institution' AND root_org_unit_id IS NULL) OR "
            "(scope_kind='college' AND root_org_unit_id IS NOT NULL)"
        ),
        Index(
            "one_organization_delegation",
            "user_id",
            "institution_id",
            "scope_kind",
            "root_org_unit_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("status IN ('active','suspended')"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    scope_kind: Mapped[str]
    root_org_unit_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(default="active", server_default="active")
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(default=1, server_default="1")
