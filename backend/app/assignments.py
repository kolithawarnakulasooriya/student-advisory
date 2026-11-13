"""Primary-advisor eligibility, capacity, immutable history, and transactional reassignment."""

from uuid import UUID

from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AdvisorAssignment, RoleGrant, StudentMembership
from app.outbox import emit
from app.security import ApiError, now
from app.staff_security import audit


def current_assignment(db: Session, mid: UUID) -> AdvisorAssignment | None:
    return db.scalar(
        select(AdvisorAssignment).where(
            AdvisorAssignment.student_membership_id == mid, AdvisorAssignment.ended_at.is_(None)
        )
    )


def eligible_advisor(
    db: Session,
    advisor_id: UUID | None,
    scope: UUID,
    institution: UUID,
    *,
    exclude_member: UUID | None = None,
) -> RoleGrant:
    if advisor_id is None:
        raise ApiError(
            409, "ADVISOR_REQUIRED", "Choose an eligible primary advisor before activation."
        )
    grant = db.get(RoleGrant, advisor_id)
    if (
        grant is None
        or grant.role != "advisor"
        or grant.org_unit_id != scope
        or grant.institution_id != institution
        or not db.scalar(text("SELECT effective_grant(:id)"), {"id": advisor_id})
    ):
        raise ApiError(409, "ADVISOR_UNAVAILABLE", "Choose an active advisor in this department.")
    count = int(db.scalar(text("SELECT advisor_load(:id)"), {"id": advisor_id}) or 0)
    current = current_assignment(db, exclude_member) if exclude_member else None
    if current and current.advisor_grant_id == advisor_id:
        count -= 1
    if grant.capacity is not None and count >= grant.capacity:
        raise ApiError(409, "ADVISOR_CAPACITY", "This advisor has no available capacity.")
    return grant


def assign(
    db: Session, request: Request, member: StudentMembership, advisor_id: UUID | None, reason: str
) -> None:
    advisor = eligible_advisor(
        db, advisor_id, member.org_unit_id, member.institution_id, exclude_member=member.id
    )
    old = current_assignment(db, member.id)
    if old:
        old.ended_at = now()
        db.flush()
    db.add(
        AdvisorAssignment(
            student_membership_id=member.id,
            advisor_grant_id=advisor.id,
            actor_id=request.state.actor_id,
            reason=reason,
        )
    )
    db.flush()
    db.refresh(member)
    audit(
        db,
        request,
        "assignment.changed",
        "student_membership",
        member.id,
        member.org_unit_id,
        member.institution_id,
    )
    emit(db, request, "assignment.changed", member)
