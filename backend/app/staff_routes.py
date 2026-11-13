from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from sqlalchemy import select, text

from app.assignments import assign, eligible_advisor
from app.db import context
from app.memberships import activate
from app.models import (
    AuditEvent,
    EnrollmentOption,
    Invitation,
    MembershipRequest,
    OperationalReason,
    OrganizationAdminGrant,
    OrgUnit,
    PlatformGrant,
    RoleGrant,
    StudentMembership,
    User,
)
from app.outbox import emit
from app.security import ApiError, digest, now
from app.staff_schemas import (
    AcceptInput,
    AccountInput,
    AdvisorOut,
    AssignmentInput,
    AssignmentState,
    AuditOut,
    DecisionInput,
    DelegationInput,
    GrantInput,
    InviteInput,
    InviteOut,
    LifecycleInput,
    MemberOut,
    OptionOut,
    Outcome,
    Page,
    PlatformInput,
    PlatformOut,
    Purpose,
    ReasonInput,
    RequestInput,
    RequestOut,
    StudentOut,
    UserOut,
)
from app.staff_security import (
    audit,
    can,
    lock_and_check_last_admin,
    not_found,
    parameters,
    platform,
    require,
    version_check,
    workflow,
)
from app.staff_services import (
    idempotent,
    invitation_token,
    invite_out,
    member_out,
    paginate,
    request_out,
    student_out,
)

router = APIRouter(prefix="/api/v1")
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=2048)]


def invitation_action(role: str) -> str:
    return "secretary.manage" if role == "secretary" else role + ".invite"


def reason_text(db: Any, reason_id: UUID | None) -> str | None:
    reason = db.get(OperationalReason, reason_id) if reason_id else None
    return reason.text if reason else None


def global_read(db: Any, request: Request, purpose: str | None) -> None:
    if platform(db):
        if not purpose:
            raise ApiError(403, "PURPOSE_REQUIRED", "Select an operational purpose for this read.")
        audit(db, request, "oversight.read", "directory", reason=purpose.upper())


@router.get("/membership-options", response_model=Page[OptionOut])
def options(request: Request, limit: Limit = 25, cursor: Cursor = None) -> dict[str, Any]:
    with workflow(request, "membership.options") as (db, actor):
        return paginate(
            db,
            select(EnrollmentOption).where(EnrollmentOption.enabled),
            request,
            None,
            limit,
            cursor,
            lambda o: OptionOut(id=o.id, institution_id=o.institution_id, name=o.label),
        )


@router.post("/membership-requests", response_model=RequestOut, status_code=201)
def create_request(body: RequestInput, request: Request) -> dict[str, Any]:
    with workflow(request, "membership.request") as (db, actor):

        def operation() -> dict[str, Any]:
            option = db.get(EnrollmentOption, body.org_unit_id)
            if option is None or not option.enabled:
                raise not_found()
            existing = db.scalar(
                select(MembershipRequest).where(
                    MembershipRequest.user_id == actor.user.id,
                    MembershipRequest.org_unit_id == body.org_unit_id,
                    MembershipRequest.requested_role == body.requested_role,
                    MembershipRequest.status == "pending",
                )
            )
            if existing:
                return request_out(db, existing).model_dump(mode="json")
            if db.scalar(
                select(RoleGrant.id).where(
                    RoleGrant.user_id == actor.user.id,
                    RoleGrant.org_unit_id == body.org_unit_id,
                    RoleGrant.role == body.requested_role,
                    RoleGrant.status.in_(["active", "suspended"]),
                )
            ):
                raise ApiError(409, "MEMBERSHIP_EXISTS", "Review your existing membership first.")
            row = MembershipRequest(
                user_id=actor.user.id,
                institution_id=option.institution_id,
                org_unit_id=option.id,
                requested_role=body.requested_role,
                justification=body.justification,
            )
            db.add(row)
            db.flush()
            audit(
                db,
                request,
                "membership.requested",
                "request",
                row.id,
                row.org_unit_id,
                row.institution_id,
            )
            emit(db, request, "membership.requested", row)
            return request_out(db, row).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/membership-requests", response_model=Page[RequestOut])
def requests_list(
    request: Request,
    scope_id: UUID | None = None,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "membership.requests.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        stmt = select(MembershipRequest)
        if scope_id:
            stmt = stmt.where(MembershipRequest.org_unit_id == scope_id)
        return paginate(db, stmt, request, scope_id, limit, cursor, lambda r: request_out(db, r))


def decide(
    body: DecisionInput, request: Request, rid: UUID, approved: bool, purpose: str | None
) -> dict[str, Any]:
    with workflow(request, "membership.decide", purpose or "administration") as (db, actor):
        row = db.get(MembershipRequest, rid)
        if row is None:
            raise not_found()
        require(db, row.requested_role + ".approve", row.org_unit_id)
        if row.user_id == actor.user.id:
            raise ApiError(403, "SELF_APPROVAL", "You cannot decide your own membership request.")

        def operation() -> dict[str, Any]:
            version_check(request, row.version)
            if row.status != "pending":
                raise ApiError(409, "STALE_TRANSITION", "This request already has a decision.")
            if approved:
                user = db.get(User, row.user_id)
                if user is None:
                    raise not_found()
                activate(
                    db,
                    request,
                    user,
                    row.requested_role,
                    row.org_unit_id,
                    row.institution_id,
                    body.reason,
                    body.advisor_grant_id,
                )
            row.status = "approved" if approved else "rejected"
            row.decided_by = actor.user.id
            row.decision_reason = body.reason
            row.version += 1
            db.flush()
            audit(
                db,
                request,
                "membership.decided",
                "request",
                row.id,
                row.org_unit_id,
                row.institution_id,
            )
            emit(db, request, "membership.decided", row)
            return request_out(db, row).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/membership-requests/{rid}/approve", response_model=RequestOut)
def approve(rid: UUID, body: DecisionInput, request: Request) -> dict[str, Any]:
    return decide(body, request, rid, True, None)


@router.post("/membership-requests/{rid}/reject", response_model=RequestOut)
def reject(rid: UUID, body: DecisionInput, request: Request) -> dict[str, Any]:
    return decide(body, request, rid, False, None)


@router.post("/invitations", response_model=InviteOut, status_code=201)
def create_invite(body: InviteInput, request: Request) -> dict[str, Any]:
    with workflow(request, "invitation.create", "administration") as (db, actor):
        require(db, invitation_action(body.role), body.org_unit_id)
        parameters(body.role, body.capabilities, "advisor", global_admin=platform(db))
        if body.email == actor.user.email:
            raise ApiError(403, "SELF_INVITATION", "You cannot invite your own account.")

        def operation() -> dict[str, Any]:
            org = db.get(OrgUnit, body.org_unit_id)
            if org is None:
                raise not_found()
            existing = db.scalar(
                select(Invitation).where(
                    Invitation.email == body.email,
                    Invitation.org_unit_id == org.id,
                    Invitation.role == body.role,
                    Invitation.status == "pending",
                )
            )
            if existing and existing.expires_at > now():
                return invite_out(existing).model_dump(mode="json")
            if existing:
                existing.status = "expired"
                db.flush()
            if body.role == "student":
                eligible_advisor(db, body.advisor_grant_id, org.id, org.institution_id)
            row = Invitation(
                id=uuid4(),
                institution_id=org.institution_id,
                org_unit_id=org.id,
                email=body.email,
                role=body.role,
                inviter_id=actor.user.id,
                advisor_grant_id=body.advisor_grant_id,
                capabilities=body.capabilities,
                nonce=str(uuid4()),
                token_hash="",
                expires_at=now() + timedelta(hours=request.app.state.settings.invitation_hours),
            )
            row.token_hash = digest(invitation_token(row, request.app.state.settings))
            db.add(row)
            db.flush()
            audit(
                db, request, "invitation.created", "invitation", row.id, org.id, org.institution_id
            )
            emit(db, request, "invitation.send", row, deliver=True)
            return invite_out(row).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/invitations", response_model=Page[InviteOut])
def invitations(
    request: Request,
    scope_id: UUID,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "invitation.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        # List access requires an issuing permission; recipient acceptance uses its token endpoint.
        if not any(
            can(db, invitation_action(r), scope_id)
            for r in ["student", "advisor", "manager", "secretary"]
        ):
            raise not_found()
        return paginate(
            db,
            select(Invitation).where(Invitation.org_unit_id == scope_id),
            request,
            scope_id,
            limit,
            cursor,
            invite_out,
        )


@router.post("/invitations/accept", response_model=MemberOut)
def accept_invite(body: AcceptInput, request: Request) -> dict[str, Any]:
    with workflow(request, "invitation.accept", "administration") as (db, actor):
        try:
            iid = UUID(body.token.split(".")[0])
        except ValueError:
            raise ApiError(
                409, "INVALID_INVITATION", "Invitation unavailable or expired."
            ) from None
        context(db, invite_hash=digest(body.token))
        inv = db.get(Invitation, iid)
        if inv is None or inv.email != actor.user.email or inv.inviter_id == actor.user.id:
            raise ApiError(409, "INVALID_INVITATION", "Invitation unavailable or expired.")

        def operation() -> dict[str, Any]:
            if (
                inv.status != "pending"
                or inv.expires_at <= now()
                or not __import__("hmac").compare_digest(inv.token_hash, digest(body.token))
                or not db.scalar(text("SELECT inviter_allowed(:id)"), {"id": inv.id})
            ):
                raise ApiError(409, "INVALID_INVITATION", "Invitation unavailable or expired.")
            grant = activate(
                db,
                request,
                actor.user,
                inv.role,
                inv.org_unit_id,
                inv.institution_id,
                "Verified invitation acceptance",
                inv.advisor_grant_id,
                inv.capabilities,
                invitation_id=inv.id,
            )
            inv.status = "accepted"
            inv.accepted_by = actor.user.id
            inv.version += 1
            db.flush()
            audit(
                db,
                request,
                "invitation.accepted",
                "invitation",
                inv.id,
                inv.org_unit_id,
                inv.institution_id,
            )
            emit(db, request, "invitation.accepted", inv)
            return member_out(db, grant).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


def change_invite(iid: UUID, body: ReasonInput, request: Request, resend: bool) -> dict[str, Any]:
    with workflow(
        request, "invitation.resend" if resend else "invitation.revoke", "administration"
    ) as (db, actor):
        inv = db.get(Invitation, iid)
        if inv is None:
            raise not_found()
        require(db, invitation_action(inv.role), inv.org_unit_id)

        def operation() -> dict[str, Any]:
            version_check(request, inv.version)
            if inv.status not in {"pending", "expired"}:
                raise ApiError(409, "STALE_TRANSITION", "This invitation is no longer pending.")
            inv.version += 1
            if resend:
                inv.nonce = str(uuid4())
                inv.inviter_id = actor.user.id
                inv.status = "pending"
                inv.expires_at = now() + timedelta(
                    hours=request.app.state.settings.invitation_hours
                )
                inv.token_hash = digest(invitation_token(inv, request.app.state.settings))
            else:
                inv.status = "revoked"
            audit(
                db,
                request,
                "invitation.resent" if resend else "invitation.revoked",
                "invitation",
                inv.id,
                inv.org_unit_id,
                inv.institution_id,
            )
            if resend:
                emit(db, request, "invitation.send", inv, deliver=True)
            return invite_out(inv).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/invitations/{iid}/resend", response_model=InviteOut)
def resend_invite(iid: UUID, body: ReasonInput, request: Request) -> dict[str, Any]:
    return change_invite(iid, body, request, True)


@router.post("/invitations/{iid}/revoke", response_model=InviteOut)
def revoke_invite(iid: UUID, body: ReasonInput, request: Request) -> dict[str, Any]:
    return change_invite(iid, body, request, False)


@router.get("/memberships", response_model=Page[MemberOut])
def memberships(
    request: Request,
    scope_id: UUID,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "membership.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        require(db, "membership.read", scope_id)
        return paginate(
            db,
            select(RoleGrant).where(RoleGrant.org_unit_id == scope_id),
            request,
            scope_id,
            limit,
            cursor,
            lambda g: member_out(db, g),
        )


@router.get("/memberships/{gid}", response_model=MemberOut)
def membership(gid: UUID, request: Request, purpose: Purpose | None = None) -> MemberOut:
    with workflow(request, "membership.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        grant = db.get(RoleGrant, gid)
        if grant is None or not can(db, "membership.read", grant.org_unit_id):
            raise not_found()
        return member_out(db, grant)


@router.get("/students", response_model=Page[StudentOut])
def students(
    request: Request,
    scope_id: UUID,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "student.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        return paginate(
            db,
            select(StudentMembership).where(
                StudentMembership.org_unit_id == scope_id,
                text("can_student(student_memberships.id)"),
            ),
            request,
            scope_id,
            limit,
            cursor,
            lambda m: student_out(db, m),
        )


@router.get("/students/{mid}", response_model=StudentOut)
def student(mid: UUID, request: Request, purpose: Purpose | None = None) -> StudentOut:
    with workflow(request, "student.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        member = db.get(StudentMembership, mid)
        if member is None:
            raise not_found()
        return student_out(db, member)


@router.get("/eligible-advisors", response_model=Page[AdvisorOut])
def advisors(
    request: Request,
    scope_id: UUID,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "advisor.select", purpose) as (db, actor):
        global_read(db, request, purpose)
        if not any(
            can(db, a, scope_id) for a in ["assignment.manage", "student.approve", "student.invite"]
        ):
            raise not_found()

        def project(grant: RoleGrant) -> AdvisorOut:
            user = db.get(User, grant.user_id)
            if user is None:
                raise not_found()
            return AdvisorOut(
                id=grant.id,
                user_id=user.id,
                name=user.name,
                email=user.email,
                capacity=grant.capacity,
                assigned_count=db.scalar(text("SELECT advisor_load(:id)"), {"id": grant.id}) or 0,
            )

        return paginate(
            db,
            select(RoleGrant).where(
                RoleGrant.org_unit_id == scope_id,
                RoleGrant.role == "advisor",
                text("effective_grant(role_grants.id)"),
            ),
            request,
            scope_id,
            limit,
            cursor,
            project,
        )


@router.put("/students/{mid}/advisor", response_model=Outcome)
def reassign(mid: UUID, body: AssignmentInput, request: Request) -> dict[str, Any]:
    with workflow(request, "assignment.change", "administration") as (db, actor):
        member = db.get(StudentMembership, mid)
        if member is None:
            raise not_found()
        require(db, "assignment.manage", member.org_unit_id)

        def operation() -> dict[str, Any]:
            version_check(request, member.version)
            grant = db.get(RoleGrant, member.grant_id)
            if grant is None or not db.scalar(
                text("SELECT effective_grant(:id)"), {"id": grant.id}
            ):
                raise ApiError(
                    409, "MEMBERSHIP_INACTIVE", "An active student membership is required."
                )
            assign(db, request, member, body.advisor_grant_id, body.reason)
            # Secretaries manage enrollment/assignments without gaining student-record access.
            return {"status": "assigned", "id": str(member.id)}

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/role-grants", response_model=MemberOut, status_code=201)
def grant_role(body: GrantInput, request: Request) -> dict[str, Any]:
    with workflow(request, "grant.create", "administration") as (db, actor):
        require(
            db,
            "platform.manage"
            if body.role == "platform_admin"
            else "secretary.manage"
            if body.role == "secretary"
            else body.role + ".manage",
            body.org_unit_id,
        )
        parameters(body.role, body.capabilities, body.ceiling, global_admin=platform(db))

        def operation() -> dict[str, Any]:
            target = db.get(User, body.user_id)
            org = db.get(OrgUnit, body.org_unit_id)
            if target is None or org is None:
                raise not_found()
            grant = activate(
                db,
                request,
                target,
                body.role,
                org.id,
                org.institution_id,
                body.reason,
                body.advisor_grant_id,
                body.capabilities,
                ceiling=body.ceiling,
                capacity=body.capacity,
            )
            return member_out(db, grant).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.patch("/role-grants/{gid}", response_model=MemberOut)
def delegate(gid: UUID, body: DelegationInput, request: Request) -> dict[str, Any]:
    with workflow(request, "grant.delegate", "administration") as (db, actor):
        grant = db.get(RoleGrant, gid)
        if grant is None:
            raise not_found()
        require(
            db,
            "platform.manage"
            if grant.role == "platform_admin"
            else "secretary.manage"
            if grant.role == "secretary"
            else grant.role + ".manage",
            grant.org_unit_id,
        )
        parameters(grant.role, body.capabilities, body.ceiling, global_admin=platform(db))
        if grant.user_id == actor.user.id:
            raise ApiError(403, "SELF_APPROVAL", "You cannot change your own delegation.")

        def operation() -> dict[str, Any]:
            version_check(request, grant.version)
            if grant.role != "advisor" and body.capacity is not None:
                raise ApiError(422, "INVALID_CAPACITY", "Capacity applies only to advisors.")
            if (
                body.capacity is not None
                and (db.scalar(text("SELECT advisor_load(:id)"), {"id": gid}) or 0) > body.capacity
            ):
                raise ApiError(409, "ADVISOR_CAPACITY", "Existing assignments exceed this limit.")
            grant.capabilities = body.capabilities
            grant.ceiling = body.ceiling
            grant.capacity = body.capacity
            grant.version += 1
            audit(
                db,
                request,
                "grant.delegated",
                "grant",
                gid,
                grant.org_unit_id,
                grant.institution_id,
            )
            db.flush()
            return member_out(db, grant).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.patch("/memberships/{gid}", response_model=MemberOut)
def lifecycle(gid: UUID, body: LifecycleInput, request: Request) -> dict[str, Any]:
    with workflow(request, "membership.lifecycle", "administration") as (db, actor):
        grant = db.get(RoleGrant, gid)
        if grant is None:
            raise not_found()
        require(
            db,
            "platform.manage"
            if grant.role == "platform_admin"
            else "secretary.manage"
            if grant.role == "secretary"
            else grant.role + ".manage",
            grant.org_unit_id,
        )
        if grant.user_id == actor.user.id:
            raise ApiError(
                403, "SELF_APPROVAL", "Ask another authorized staff member to change your grant."
            )

        def operation() -> dict[str, Any]:
            version_check(request, grant.version)
            valid = {"active": {"suspended", "revoked"}, "suspended": {"active", "revoked"}}
            if body.status not in valid.get(grant.status, set()):
                raise ApiError(
                    409, "STALE_TRANSITION", "This membership requires a new approved request."
                )
            member = db.scalar(select(StudentMembership).where(StudentMembership.grant_id == gid))
            target = db.get(User, grant.user_id)
            if body.status == "active" and (
                target is None or target.status != "active" or not target.verified
            ):
                raise ApiError(
                    409, "IDENTITY_UNAVAILABLE", "Reactivate and verify the account first."
                )
            if body.status == "active" and member:
                require(db, "assignment.manage", grant.org_unit_id)
                eligible_advisor(db, body.advisor_grant_id, grant.org_unit_id, grant.institution_id)
            grant.status = body.status
            grant.version += 1
            db.flush()
            if body.status == "active" and member:
                assign(db, request, member, body.advisor_grant_id, body.reason)
            audit(
                db,
                request,
                "membership." + body.status,
                "grant",
                gid,
                grant.org_unit_id,
                grant.institution_id,
            )
            emit(db, request, "membership.changed", grant)
            return member_out(db, grant).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/users/{uid}/state", response_model=Outcome)
def account_state(uid: UUID, body: AccountInput, request: Request) -> dict[str, Any]:
    with workflow(request, "account.state", "administration") as (db, actor):
        require(db, "account.manage", None)
        target = db.get(User, uid)
        if target is None:
            raise not_found()

        def operation() -> dict[str, Any]:
            if body.status == "suspended":
                lock_and_check_last_admin(db, uid)
            if uid == actor.user.id:
                raise ApiError(
                    403, "SELF_LIFECYCLE", "Another super admin must change your account state."
                )
            version_check(request, target.grant_epoch)
            grants = list(db.scalars(select(RoleGrant).where(RoleGrant.user_id == uid)))
            selected = set(body.approved_grant_ids)
            eligible = {g.id for g in grants if g.status == "suspended"}
            if not selected <= eligible or (body.status == "suspended" and selected):
                raise ApiError(
                    422, "INVALID_GRANTS", "Select suspended grants to approve explicitly."
                )
            if body.status == "active" and any(
                g.id in selected and g.role == "student" for g in grants
            ):
                raise ApiError(
                    409,
                    "ADVISOR_REQUIRED",
                    "Reactivate the account, then approve student memberships with an advisor.",
                )
            db.execute(
                text("SELECT update_account(:id,:status)"), {"id": uid, "status": body.status}
            )
            db.expire_all()
            if body.status == "active":
                for grant in grants:
                    if grant.id in selected:
                        grant.status = "active"
                        grant.version += 1
            audit(db, request, "account." + body.status, "user", uid)
            return {"status": body.status, "id": str(uid)}

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/users", response_model=Page[UserOut])
def users(
    request: Request,
    purpose: Purpose | None = None,
    scope_id: UUID | None = None,
    email: str | None = Query(default=None, max_length=254),
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "users.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        if not platform(db):
            require(db, "staff.read", scope_id)
        stmt = select(User)
        if scope_id:
            stmt = stmt.where(
                User.id.in_(select(RoleGrant.user_id).where(RoleGrant.org_unit_id == scope_id))
            )
        if email:
            stmt = stmt.where(User.email == email)
        return paginate(
            db,
            stmt,
            request,
            scope_id,
            limit,
            cursor,
            lambda u: UserOut(
                id=u.id,
                email=u.email,
                name=u.name,
                status=u.status,
                verified=u.verified,
                grant_epoch=u.grant_epoch,
            ),
        )


@router.get("/platform-grants", response_model=Page[PlatformOut])
def platform_grants(
    request: Request, purpose: Purpose | None = None, limit: Limit = 25, cursor: Cursor = None
) -> dict[str, Any]:
    with workflow(request, "platform.read", purpose) as (db, actor):
        require(db, "platform.manage", None)
        global_read(db, request, purpose)
        return paginate(
            db,
            select(PlatformGrant),
            request,
            None,
            limit,
            cursor,
            lambda g: PlatformOut(id=g.id, user_id=g.user_id, status=g.status, version=g.version),
        )


@router.post("/platform-grants", response_model=PlatformOut, status_code=201)
def appoint_platform(body: PlatformInput, request: Request) -> dict[str, Any]:
    with workflow(request, "platform.appoint", "administration") as (db, actor):
        require(db, "platform.manage", None)

        def operation() -> dict[str, Any]:
            target = db.get(User, body.user_id)
            if target is None or not target.verified or target.status != "active":
                raise ApiError(409, "IDENTITY_UNAVAILABLE", "Choose a verified active account.")
            if target.id == actor.user.id:
                raise ApiError(403, "SELF_APPROVAL", "You cannot appoint yourself.")
            row = PlatformGrant(user_id=target.id)
            db.add(row)
            db.flush()
            audit(db, request, "platform.appointed", "platform_grant", row.id)
            return PlatformOut(
                id=row.id, user_id=row.user_id, status=row.status, version=row.version
            ).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/platform-grants/{gid}/state", response_model=PlatformOut)
def platform_state(gid: UUID, body: LifecycleInput, request: Request) -> dict[str, Any]:
    with workflow(request, "platform.state", "administration") as (db, actor):
        require(db, "platform.manage", None)
        row = db.get(PlatformGrant, gid)
        if row is None:
            raise not_found()

        def operation() -> dict[str, Any]:
            version_check(request, row.version)
            if row.status == "active" and body.status != "active":
                lock_and_check_last_admin(db, row.user_id)
            if body.status not in {"active", "suspended", "revoked"} or row.status == "revoked":
                raise ApiError(409, "STALE_TRANSITION", "An explicit appointment is required.")
            user = db.get(User, row.user_id)
            if body.status == "active" and (
                user is None or user.status != "active" or not user.verified
            ):
                raise ApiError(
                    409, "IDENTITY_UNAVAILABLE", "An active verified account is required."
                )
            row.status = body.status
            row.version += 1
            audit(db, request, "platform." + body.status, "platform_grant", gid)
            db.flush()
            return PlatformOut(
                id=row.id, user_id=row.user_id, status=row.status, version=row.version
            ).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/audit-events", response_model=Page[AuditOut])
def audit_events(
    request: Request,
    scope_id: UUID | None = None,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "audit.read", purpose) as (db, actor):
        if not actor.platform_grants and not any(g.role != "student" for g in actor.active):
            raise ApiError(403, "FORBIDDEN", "Administrative audit is available to staff only.")
        global_read(db, request, purpose)
        stmt = select(AuditEvent)
        if scope_id:
            stmt = stmt.where(AuditEvent.org_unit_id == scope_id)

        def project(row: AuditEvent) -> AuditOut:
            # Self-action history never re-exposes an inaccessible target identifier.
            object_id = (
                row.object_id if platform(db) or can(db, "audit.read", row.org_unit_id) else None
            )
            return AuditOut(
                id=row.id,
                actor_id=row.actor_id,
                action=row.action,
                object_type=row.object_type,
                object_id=object_id,
                org_unit_id=row.org_unit_id,
                result=row.result,
                reason_code=row.reason_code,
                correlation_id=row.correlation_id,
                reason=reason_text(db, row.reason_id),
                occurred_at=row.occurred_at,
            )

        return paginate(db, stmt, request, scope_id, limit, cursor, project, descending=True)


@router.get("/users/{uid}/history", response_model=Page[AuditOut])
def history(
    uid: UUID,
    request: Request,
    scope_id: UUID | None = None,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "history.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        target = db.get(User, uid)
        if target is None:
            raise not_found()
        if not platform(db):
            require(db, "history.read", scope_id)
        # Grant, request, invitation and assignment references are scoped afresh.
        refs = [str(uid)]
        refs += [str(g.id) for g in db.scalars(select(RoleGrant).where(RoleGrant.user_id == uid))]
        refs += [
            str(g.id)
            for g in db.scalars(
                select(OrganizationAdminGrant).where(OrganizationAdminGrant.user_id == uid)
            )
        ]
        refs += [
            str(r.id)
            for r in db.scalars(select(MembershipRequest).where(MembershipRequest.user_id == uid))
        ]
        refs += [
            str(m.id)
            for m in db.scalars(
                select(StudentMembership).where(
                    StudentMembership.user_id == uid, text("can_student(student_memberships.id)")
                )
            )
        ]
        stmt = select(AuditEvent).where(
            (AuditEvent.actor_id == uid) | (AuditEvent.object_id.in_(refs))
        )
        if scope_id:
            stmt = stmt.where(AuditEvent.org_unit_id == scope_id)
        return paginate(
            db,
            stmt,
            request,
            scope_id,
            limit,
            cursor,
            lambda r: AuditOut(
                id=r.id,
                actor_id=r.actor_id,
                action=r.action,
                object_type=r.object_type,
                object_id=r.object_id,
                org_unit_id=r.org_unit_id,
                result=r.result,
                reason_code=r.reason_code,
                correlation_id=r.correlation_id,
                reason=reason_text(db, r.reason_id),
                occurred_at=r.occurred_at,
            ),
            descending=True,
        )


@router.get("/assignment-state/{mid}", response_model=AssignmentState)
def assignment_state(
    mid: UUID, request: Request, purpose: Purpose | None = None
) -> AssignmentState:
    with workflow(request, "assignment.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        member = db.get(StudentMembership, mid)
        if member is None or not can(db, "assignment.manage", member.org_unit_id):
            raise not_found()
        return AssignmentState(
            id=member.id, version=member.version, relationship_epoch=member.relationship_epoch
        )
