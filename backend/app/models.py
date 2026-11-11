from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str]


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
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"))
    parent_id: Mapped[UUID | None]
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str]
    kind: Mapped[str]
    timezone: Mapped[str] = mapped_column(default="America/Chicago")


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
        UniqueConstraint("user_id", "org_unit_id", "role"),
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
