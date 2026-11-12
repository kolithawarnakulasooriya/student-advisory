"""Current-DB authorization, short identity transactions, and scoped workflow transactions."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import Table, insert, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import context, safe_runtime_role, transaction
from app.models import AuditEvent, OperationalReason, PlatformGrant, RoleGrant
from app.security import (
    COOKIE,
    ApiError,
    AuthContext,
    check_csrf,
    digest,
    load_actor,
    require_recent,
    session_for,
)

SECRETARY_CAPS = {"student.invite", "student.approve", "student.manage", "assignment.manage"}
PLATFORM_CAPS = SECRETARY_CAPS | {
    "org.read",
    "profile.configure",
    "source.manage",
    "source.read",
    "advisor.invite",
    "advisor.approve",
    "advisor.manage",
    "manager.invite",
    "manager.approve",
    "manager.manage",
    "secretary.manage",
    "membership.read",
    "student.read",
    "staff.read",
    "audit.read",
    "history.read",
}
WORKFLOW_LOCK = 2026111102


def platform(db: Session) -> bool:
    return bool(db.scalar(text("SELECT platform_admin()")))


def can(db: Session, action: str, scope: UUID | None) -> bool:
    return bool(
        db.scalar(text("SELECT can_action(:action,:scope)"), {"action": action, "scope": scope})
    )


def require(db: Session, action: str, scope: UUID | None) -> None:
    if not can(db, action, scope):
        raise ApiError(403, "FORBIDDEN", "This action is not permitted in the selected scope.")


def not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", "Resource not found.")


def audit(
    db: Session,
    request: Request,
    action: str,
    obj_type: str,
    obj_id: object = None,
    scope: UUID | None = None,
    institution: UUID | None = None,
    result: str = "allow",
    reason: str = "AUTHORIZED",
) -> None:
    reason_id = None
    explanation = getattr(request.state, "operation_reason", "")
    if explanation and result == "allow":
        reason_id = uuid4()
        db.add(
            OperationalReason(
                id=reason_id, actor_id=request.state.actor_id, org_unit_id=scope, text=explanation
            )
        )
        db.flush()
    if getattr(request.state, "actor_id", None) is None:
        # Anonymous denial logging needs INSERT only: RETURNING would require permission
        # to read the anonymous row, which must remain inaccessible to ordinary callers.
        db.execute(
            insert(cast(Table, AuditEvent.__table__))
            .inline()
            .values(
                actor_id=None,
                action=action,
                reason_id=None,
                object_type=obj_type,
                object_id=str(obj_id) if obj_id is not None else None,
                org_unit_id=scope,
                institution_id=institution,
                result=result,
                reason_code=reason,
                correlation_id=request.state.correlation_id,
            )
        )
        return
    db.add(
        AuditEvent(
            actor_id=getattr(request.state, "actor_id", None),
            action=action,
            reason_id=reason_id,
            object_type=obj_type,
            object_id=str(obj_id) if obj_id is not None else None,
            org_unit_id=scope,
            institution_id=institution,
            result=result,
            reason_code=reason,
            correlation_id=request.state.correlation_id,
        )
    )


@contextmanager
def workflow(
    request: Request, action: str, purpose: str | None = None
) -> Iterator[tuple[Session, AuthContext]]:
    app = request.app
    cfg = app.state.settings
    actor_id: UUID | None = None
    try:
        # Commit identity bookkeeping before acquiring business locks. In particular, never
        # retain an auth-session row lock while another connection revokes sessions.
        with transaction(app.state.auth_engine) as auth:
            if not safe_runtime_role(auth, "advisory_auth"):
                raise ApiError(
                    503, "UNSAFE_DATABASE_ROLE", "Database role configuration is invalid."
                )
            identity_session = session_for(auth, request.cookies.get(COOKIE), cfg)
            if identity_session.user_id is None:
                raise ApiError(401, "SESSION_REQUIRED", "Sign in to continue.")
            actor_id = identity_session.user_id
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                check_csrf(request, identity_session, cfg)
                require_recent(identity_session, cfg)
            mfa = identity_session.mfa
        request.state.actor_id = actor_id
        with transaction(app.state.engine) as db:
            if not safe_runtime_role(db, "advisory_app"):
                raise ApiError(
                    503, "UNSAFE_DATABASE_ROLE", "Database role configuration is invalid."
                )
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                # A deliberately coarse local write lock serializes approvals, capacity,
                # authority changes and last-admin checks. No throughput claim is made.
                db.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": WORKFLOW_LOCK})
            context(
                db,
                user_id=str(actor_id),
                mfa="true" if mfa else "false",
                session_hash=digest(request.cookies.get(COOKIE, "")),
                purpose=purpose or "",
            )
            if not db.scalar(text("SELECT current_session_live()")):
                raise ApiError(401, "SESSION_REQUIRED", "Sign in to continue.")
            actor = load_actor(db, actor_id, mfa)
            if not actor.user.verified:
                raise ApiError(403, "VERIFICATION_REQUIRED", "Verify your synthetic email first.")
            is_platform = bool(
                db.scalar(
                    select(PlatformGrant.id).where(
                        PlatformGrant.user_id == actor_id, PlatformGrant.status == "active"
                    )
                )
            )
            if (actor.mfa_required or is_platform) and not mfa:
                raise ApiError(403, "MFA_REQUIRED", "Complete simulated staff MFA to continue.")
            yield db, actor
            if request.method in {"GET", "HEAD"}:
                selected = request.query_params.get("scope_id")
                audit(db, request, action, "query", scope=UUID(selected) if selected else None)
    except (ApiError, SQLAlchemyError) as exc:
        # This is a separate, append-only transaction after business rollback. Do not
        # serialize bodies, token strings, email addresses or free-text justifications.
        with transaction(app.state.engine) as denied:
            context(denied, user_id=str(actor_id) if actor_id else "")
            request.state.actor_id = actor_id
            audit(
                denied,
                request,
                action,
                "attempt",
                result="deny",
                reason=exc.code if isinstance(exc, ApiError) else "DATABASE_CONFLICT",
            )
        raise


def parameters(role: str, caps: list[str], ceiling: str, *, global_admin: bool) -> None:
    allowed = (
        SECRETARY_CAPS
        if role == "secretary"
        else PLATFORM_CAPS
        if role == "platform_admin"
        else set()
    )
    if not set(caps) <= allowed or len(caps) != len(set(caps)):
        raise ApiError(
            422, "INVALID_CAPABILITIES", "Select only permitted delegation capabilities."
        )
    if role == "platform_admin" and not global_admin:
        raise ApiError(403, "FORBIDDEN", "Only a platform super admin can delegate administrators.")
    if role == "platform_admin":
        if "manager.approve" in caps:
            raise ApiError(
                422, "INVALID_CAPABILITIES", "Manager requests require a platform super admin."
            )
        prohibited = (
            ("advisor.", "manager.", "secretary.")
            if ceiling == "student"
            else ("manager.",)
            if ceiling == "advisor"
            else ()
        )
        if prohibited and any(cap.startswith(prohibited) for cap in caps):
            raise ApiError(
                422, "INVALID_CEILING", "Delegation exceeds the selected appointment ceiling."
            )
    if role != "platform_admin" and ceiling != "advisor":
        raise ApiError(422, "INVALID_CEILING", "This role cannot receive an administrator ceiling.")


def version_check(request: Request, version: int) -> None:
    if request.headers.get("if-match") != f'"{version}"':
        raise ApiError(409, "STALE_REVISION", "This item changed. Refresh and review it again.")


def own_scope_capabilities(db: Session, scope: UUID | None) -> list[str]:
    actions = sorted(PLATFORM_CAPS | {"platform.manage", "account.manage"})
    result = [action for action in actions if can(db, action, scope)]
    actor_id = db.scalar(text("SELECT actor_id()"))
    own = list(
        db.scalars(
            select(RoleGrant).where(
                RoleGrant.user_id == actor_id,
                RoleGrant.org_unit_id == scope,
                text("effective_grant(role_grants.id)"),
            )
        )
    )
    for action in ("profile.configure", "source.manage", "source.read"):
        if db.scalar(text("SELECT intake_cap(:action,:scope)"), {"action": action, "scope": scope}):
            result.append(action)
    if any(g.role in {"student", "advisor"} for g in own):
        result.append("roster.read")
    if any(g.role != "student" for g in own) or platform(db):
        result.append("audit.own")
    return result


def lock_and_check_last_admin(db: Session, uid: UUID) -> None:
    target = db.scalar(
        select(PlatformGrant).where(PlatformGrant.user_id == uid, PlatformGrant.status == "active")
    )
    if target:
        count = db.scalar(
            text(
                "SELECT count(*) FROM platform_grants p JOIN users u ON u.id=p.user_id "
                "WHERE p.status='active' AND u.status='active' AND u.verified"
            )
        )
        if count is None or count <= 1:
            raise ApiError(
                409, "LAST_SUPER_ADMIN", "Keep at least one active platform super admin."
            )
