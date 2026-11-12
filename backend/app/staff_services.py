import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.assignments import current_assignment
from app.config import Settings
from app.models import (
    AuditEvent,
    IdempotencyRecord,
    Invitation,
    MembershipRequest,
    RoleGrant,
    StudentMembership,
    User,
)
from app.security import ApiError, AuthContext, digest, now
from app.staff_schemas import InviteOut, MemberOut, RequestOut, StudentOut
from app.staff_security import not_found


def invitation_token(inv: Invitation, cfg: Settings) -> str:
    signature = hmac.new(
        cfg.identity_signing_key.get_secret_value().encode(),
        f"invitation:{inv.id}:{inv.nonce}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{inv.id}.{signature}"


def idempotent(
    db: Session,
    request: Request,
    actor: AuthContext,
    payload: dict[str, Any],
    operation: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    key = request.headers.get("idempotency-key", "")
    if not 8 <= len(key) <= 100:
        raise ApiError(422, "IDEMPOTENCY_REQUIRED", "Supply a fresh idempotency key.")
    route = request.method + " " + request.url.path
    hashed = digest(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == actor.user.id,
            IdempotencyRecord.route == route,
            IdempotencyRecord.key == key,
        )
    )
    if existing:
        db.refresh(actor.user)
        if existing.payload_hash != hashed or existing.grant_epoch != actor.user.grant_epoch:
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Refresh before retrying this operation.")
        return existing.result
    request.state.operation_reason = payload.get("reason", "")
    result = operation()
    db.flush()
    db.refresh(actor.user)
    db.add(
        IdempotencyRecord(
            actor_id=actor.user.id,
            route=route,
            key=key,
            payload_hash=hashed,
            grant_epoch=actor.user.grant_epoch,
            result=result,
        )
    )
    return result


def paginate(
    db: Session,
    stmt: Any,
    request: Request,
    scope: UUID | None,
    limit: int,
    cursor: str | None,
    transform: Callable[[Any], Any],
    *,
    descending: bool = False,
) -> dict[str, Any]:
    cfg = request.app.state.settings
    model = stmt.column_descriptions[0]["entity"]
    actor = db.get(User, request.state.actor_id)
    assert actor
    binding = (
        f"{request.url.path}:{scope}:{actor.id}:{actor.grant_epoch}:{limit}:"
        + str(request.query_params.get("email", ""))
        + ":"
        + str(request.query_params.get("purpose", ""))
    )
    binding += ":" + json.dumps(
        sorted((k, v) for k, v in request.query_params.multi_items() if k != "cursor")
    )
    if (
        request.url.path.startswith("/api/v1/admin/")
        or request.url.path == "/api/v1/membership-options"
    ):
        binding += ":" + str(db.scalar(text("SELECT organization_catalog_epoch()")))
    last: str | None = None
    if cursor:
        try:
            data, signature = cursor.split(".")
            expected = hmac.new(
                cfg.identity_signing_key.get_secret_value().encode(),
                ("cursor:" + data).encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            decoded = json.loads(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))
            if decoded["binding"] != binding:
                raise ValueError
            last = decoded["last"]
        except (ValueError, KeyError, TypeError):
            raise ApiError(409, "INVALID_CURSOR", "Refresh this list before continuing.") from None
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if last:
        identifier = int(last) if model is AuditEvent else UUID(last)
        stmt = stmt.where(model.id < identifier if descending else model.id > identifier)
    rows = list(
        db.scalars(stmt.order_by(model.id.desc() if descending else model.id).limit(limit + 1))
    )
    items = [transform(row).model_dump(mode="json") for row in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        data = (
            base64.urlsafe_b64encode(
                json.dumps({"binding": binding, "last": str(rows[limit - 1].id)}).encode()
            )
            .decode()
            .rstrip("=")
        )
        signature = hmac.new(
            cfg.identity_signing_key.get_secret_value().encode(),
            ("cursor:" + data).encode(),
            hashlib.sha256,
        ).hexdigest()
        next_cursor = data + "." + signature
    return {"items": items, "next_cursor": next_cursor, "total": total}


def member_out(db: Session, g: RoleGrant) -> MemberOut:
    user = db.get(User, g.user_id)
    if user is None:
        raise not_found()
    member = db.scalar(select(StudentMembership).where(StudentMembership.grant_id == g.id))
    assignment = current_assignment(db, member.id) if member else None
    advisor = db.get(RoleGrant, assignment.advisor_grant_id) if assignment else None
    advisor_user = db.get(User, advisor.user_id) if advisor else None
    return MemberOut(
        account_state=user.status,
        id=g.id,
        student_membership_id=member.id if member else None,
        user_id=g.user_id,
        institution_id=g.institution_id,
        org_unit_id=g.org_unit_id,
        name=user.name,
        email=user.email,
        role=g.role,
        status=g.status,
        version=g.version,
        capabilities=g.capabilities,
        ceiling=g.ceiling,
        capacity=g.capacity,
        advisor_grant_id=advisor.id if advisor else None,
        advisor_name=advisor_user.name if advisor_user else None,
        relationship_epoch=member.relationship_epoch if member else 0,
    )


def student_out(db: Session, member: StudentMembership) -> StudentOut:
    if not db.scalar(text("SELECT can_student(:id)"), {"id": member.id}):
        raise not_found()
    grant = db.get(RoleGrant, member.grant_id)
    assert grant
    row = member_out(db, grant)
    return StudentOut(
        id=member.id,
        user_id=member.user_id,
        institution_id=member.institution_id,
        org_unit_id=member.org_unit_id,
        name=row.name,
        email=row.email,
        status=row.status,
        advisor_grant_id=row.advisor_grant_id,
        advisor_name=row.advisor_name,
        relationship_epoch=member.relationship_epoch,
        version=member.version,
    )


def request_out(db: Session, row: MembershipRequest) -> RequestOut:
    user = db.get(User, row.user_id)
    if user is None:
        raise not_found()
    return RequestOut(
        id=row.id,
        user_id=row.user_id,
        org_unit_id=row.org_unit_id,
        requested_role=row.requested_role,
        justification=row.justification,
        status=row.status,
        decision_reason=row.decision_reason,
        version=row.version,
        name=user.name,
        email=user.email,
    )


def invite_out(inv: Invitation) -> InviteOut:
    return InviteOut(
        id=inv.id,
        org_unit_id=inv.org_unit_id,
        email=inv.email,
        role=inv.role,
        status="expired" if inv.status == "pending" and inv.expires_at <= now() else inv.status,
        version=inv.version,
        expires_at=inv.expires_at,
        advisor_grant_id=inv.advisor_grant_id,
        capabilities=inv.capabilities,
    )
