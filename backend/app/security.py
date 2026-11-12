import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import context
from app.models import LoginSession, OrganizationAdminGrant, OrgUnit, PlatformGrant, RoleGrant, User

COOKIE = "advisory_session"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token: str, settings: Settings) -> str:
    return hmac.new(
        settings.identity_signing_key.get_secret_value().encode(),
        ("csrf:" + token).encode(),
        hashlib.sha256,
    ).hexdigest()


def now() -> datetime:
    return datetime.now(UTC)


def session_for(db: Session, token: str | None, settings: Settings) -> LoginSession:
    if not token or len(token) > 200:
        raise ApiError(401, "SESSION_REQUIRED", "Sign in to continue.")
    context(db, session_hash=digest(token))
    row = db.scalar(
        select(LoginSession).where(LoginSession.token_hash == digest(token)).with_for_update()
    )
    if row is None or row.revoked:
        raise ApiError(401, "SESSION_REQUIRED", "Sign in to continue.")
    if (
        row.expires_at <= now()
        or row.last_seen + timedelta(seconds=settings.session_idle_seconds) <= now()
    ):
        raise ApiError(401, "SESSION_EXPIRED", "Your session expired. Sign in again.")
    row.last_seen = now()
    if row.user_id:
        context(db, user_id=str(row.user_id))
    return row


def new_session(
    db: Session,
    response: Response,
    settings: Settings,
    user_id: UUID | None = None,
    mfa: bool = False,
) -> str:
    token = secrets.token_urlsafe(32)
    context(db, session_hash=digest(token))
    if user_id:
        context(db, user_id=str(user_id))
    row = LoginSession(
        user_id=user_id,
        token_hash=digest(token),
        csrf_hash=digest(csrf_token(token, settings)),
        expires_at=now() + timedelta(seconds=settings.session_absolute_seconds),
        auth_time=now() if user_id else None,
        mfa=mfa,
    )
    db.add(row)
    db.flush()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_absolute_seconds,
        path="/",
    )
    return token


def check_csrf(request: Request, session: LoginSession, settings: Settings) -> None:
    origin = request.headers.get("origin")
    token = request.headers.get("x-csrf-token", "")
    if origin != settings.web_origin or not hmac.compare_digest(session.csrf_hash, digest(token)):
        raise ApiError(403, "CSRF_FAILED", "Refresh this page and try again.")


@dataclass
class AuthContext:
    user: User
    grants: list[RoleGrant]
    mfa: bool
    platform_grants: list[PlatformGrant] = field(default_factory=list)
    platform_scopes: set[UUID] = field(default_factory=set)
    organization_grants: list[OrganizationAdminGrant] = field(default_factory=list)

    @property
    def active(self) -> list[RoleGrant]:
        if not self.user.verified or self.user.status != "active":
            return []
        return [
            g
            for g in self.grants
            if g.status == "active" and (g.valid_until is None or g.valid_until > now())
        ]

    @property
    def mfa_required(self) -> bool:
        return not self.mfa and (
            bool(self.platform_grants)
            or bool(self.organization_grants)
            or any(g.role != "student" for g in self.active)
        )

    @property
    def allowed_scopes(self) -> set[UUID]:
        if self.mfa_required:
            return set()
        return {g.org_unit_id for g in self.active} | self.platform_scopes


def load_actor(db: Session, user_id: UUID | None, mfa: bool) -> AuthContext:
    if user_id is None:
        raise ApiError(401, "SESSION_REQUIRED", "Sign in to continue.")
    context(db, user_id=str(user_id), mfa="true" if mfa else "false")
    user = db.get(User, user_id)
    if user is None or user.status != "active":
        raise ApiError(401, "ACCOUNT_UNAVAILABLE", "This account is unavailable.")
    grants = list(db.scalars(select(RoleGrant).where(RoleGrant.user_id == user_id)))
    pgs = list(
        db.scalars(
            select(PlatformGrant).where(
                PlatformGrant.user_id == user_id, PlatformGrant.status == "active"
            )
        )
    )
    extra = set(db.scalars(select(OrgUnit.id))) if pgs and mfa else set()
    ogs = (
        list(
            db.scalars(
                select(OrganizationAdminGrant).where(
                    OrganizationAdminGrant.user_id == user_id,
                    OrganizationAdminGrant.status == "active",
                    (OrganizationAdminGrant.valid_until.is_(None))
                    | (OrganizationAdminGrant.valid_until > now()),
                )
            )
        )
        if user.verified
        else []
    )
    return AuthContext(user, grants, mfa, pgs, extra, ogs)


def authorize(actor: AuthContext, action: str, resource: OrgUnit | None) -> None:
    if (
        action != "org.read"
        or resource is None
        or resource.id not in actor.allowed_scopes
        or (
            not actor.platform_grants
            and not any(
                g.org_unit_id == resource.id and g.institution_id == resource.institution_id
                for g in actor.active
            )
        )
    ):
        raise ApiError(404, "NOT_FOUND", "Resource not found.")


def scoped_orgs(db: Session, actor: AuthContext, selected: UUID | None = None) -> list[OrgUnit]:
    ids = (
        actor.allowed_scopes if selected is None else actor.allowed_scopes.intersection({selected})
    )
    return list(db.scalars(select(OrgUnit).where(OrgUnit.id.in_(ids)).order_by(OrgUnit.name)))


def require_recent(session: LoginSession, settings: Settings) -> None:
    if (
        session.auth_time is None
        or session.auth_time + timedelta(seconds=settings.recent_auth_seconds) <= now()
    ):
        raise ApiError(403, "RECENT_AUTH_REQUIRED", "Sign in again to continue.")
