"""Shared verified activation path for invitations, approvals, and staff appointments."""

from uuid import UUID

from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.assignments import assign, eligible_advisor
from app.models import RoleGrant, StudentMembership, User
from app.outbox import emit
from app.security import ApiError
from app.staff_security import audit


def activate(
    db: Session,
    request: Request,
    target: User,
    role: str,
    scope: UUID,
    institution: UUID,
    reason: str,
    advisor_id: UUID | None = None,
    caps: list[str] | None = None,
    *,
    invitation_id: UUID | None = None,
    ceiling: str = "advisor",
    capacity: int | None = None,
) -> RoleGrant:
    if not db.scalar(text("SELECT org_active(:id)"), {"id": scope}):
        raise ApiError(
            409, "ORGANIZATION_INACTIVE", "This department is unavailable for activation."
        )
    if not target.verified or target.status != "active":
        raise ApiError(409, "IDENTITY_UNAVAILABLE", "A verified active identity is required.")
    if target.id == request.state.actor_id and invitation_id is None:
        raise ApiError(403, "SELF_APPROVAL", "You cannot grant your own membership or privileges.")
    if role == "student":
        eligible_advisor(db, advisor_id, scope, institution)
    if invitation_id:
        gid = db.scalar(text("SELECT accept_invited_grant(:id)"), {"id": invitation_id})
        db.expire_all()
        grant = db.get(RoleGrant, gid)
        assert grant
    else:
        grant = db.scalar(
            select(RoleGrant).where(
                RoleGrant.user_id == target.id,
                RoleGrant.org_unit_id == scope,
                RoleGrant.role == role,
                RoleGrant.status.in_(["active", "pending", "invited", "suspended"]),
            )
        )
        if grant:
            if grant.status != "pending":
                raise ApiError(
                    409, "MEMBERSHIP_EXISTS", "An existing membership requires lifecycle review."
                )
            grant.status = "active"
            grant.version += 1
        else:
            grant = RoleGrant(
                user_id=target.id,
                institution_id=institution,
                org_unit_id=scope,
                role=role,
                status="active",
                capabilities=caps or [],
                ceiling=ceiling,
                capacity=capacity,
            )
            db.add(grant)
        db.flush()
    if role == "student":
        member = db.scalar(select(StudentMembership).where(StudentMembership.grant_id == grant.id))
        if member is None:
            member = StudentMembership(
                grant_id=grant.id, user_id=target.id, institution_id=institution, org_unit_id=scope
            )
            db.add(member)
            db.flush()
        assign(db, request, member, advisor_id, reason)
    audit(db, request, "membership.activated", "grant", grant.id, scope, institution)
    emit(db, request, "membership.activated", grant)
    return grant
