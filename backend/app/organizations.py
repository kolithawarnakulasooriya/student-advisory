"""Organization metadata management; grants here never authorize student records."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditEvent, EnrollmentOption, Institution, OrganizationAdminGrant, OrgUnit
from app.organization_schemas import (
    EnrollmentInput,
    InstitutionOut,
    OrganizationCreate,
    OrganizationGrantInput,
    OrganizationGrantOut,
    OrganizationGrantState,
    OrganizationMetadata,
    OrganizationOut,
)
from app.security import ApiError, now
from app.staff_routes import Cursor, Limit, global_read, reason_text
from app.staff_schemas import AuditOut, Page, Purpose, ReasonInput
from app.staff_security import audit, not_found, platform, require, version_check, workflow
from app.staff_services import idempotent, paginate

router = APIRouter(prefix="/api/v1")


def can_manage(db: Session, institution: UUID, org: UUID | None) -> bool:
    return bool(
        db.scalar(
            text("SELECT can_manage_org(:institution,:org)"),
            {"institution": institution, "org": org},
        )
    )


def require_manage(db: Session, institution: UUID, org: UUID | None) -> None:
    if not can_manage(db, institution, org):
        raise not_found()


def organization_out(db: Session, org: OrgUnit) -> OrganizationOut:
    option = db.get(EnrollmentOption, org.id)
    return OrganizationOut(
        id=org.id,
        institution_id=org.institution_id,
        parent_id=org.parent_id,
        name=org.name,
        code=org.code,
        kind=org.kind,
        timezone=org.timezone,
        status=org.status,
        version=org.version,
        enrollment_enabled=bool(option and option.enabled and org.status == "active"),
    )


def get_org(db: Session, oid: UUID) -> OrgUnit:
    org = db.get(OrgUnit, oid)
    if org is None:
        raise not_found()
    require_manage(db, org.institution_id, oid)
    return org


def admin_page(
    db: Session,
    request: Request,
    stmt: Any,
    scope: UUID | None,
    limit: int,
    cursor: str | None,
    transform: Any,
) -> dict[str, Any]:
    request.state.pagination_epoch = str(db.scalar(text("SELECT organization_catalog_epoch()")))
    return paginate(db, stmt, request, scope, limit, cursor, transform)


@router.get("/admin/institutions", response_model=Page[InstitutionOut])
def institutions(
    request: Request, purpose: Purpose | None = None, limit: Limit = 25, cursor: Cursor = None
) -> dict[str, Any]:
    with workflow(request, "organization.institutions.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        if not platform(db) and not actor.organization_grants:
            raise ApiError(403, "FORBIDDEN", "Organization administration is not delegated.")
        return admin_page(
            db,
            request,
            select(Institution).where(text("can_admin_institution(institutions.id)")),
            None,
            limit,
            cursor,
            lambda i: InstitutionOut(
                id=i.id, code=i.code, name=i.name, organization_epoch=i.organization_epoch
            ),
        )


@router.get("/admin/org-units", response_model=Page[OrganizationOut])
def organizations(
    request: Request,
    institution_id: UUID,
    purpose: Purpose | None = None,
    parent_id: UUID | None = None,
    kind: Literal["college", "department"] | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "organization.list", purpose) as (db, actor):
        global_read(db, request, purpose)
        if not db.scalar(text("SELECT can_admin_institution(:id)"), {"id": institution_id}):
            raise not_found()
        stmt = select(OrgUnit).where(
            OrgUnit.institution_id == institution_id,
            text("can_manage_org(org_units.institution_id,org_units.id)"),
        )
        if kind:
            stmt = stmt.where(OrgUnit.kind == kind)
        if parent_id:
            require_manage(db, institution_id, parent_id)
            stmt = stmt.where(OrgUnit.parent_id == parent_id)
        return admin_page(
            db, request, stmt, institution_id, limit, cursor, lambda org: organization_out(db, org)
        )


@router.get("/admin/org-units/{oid}", response_model=OrganizationOut)
def organization(oid: UUID, request: Request, purpose: Purpose | None = None) -> OrganizationOut:
    with workflow(request, "organization.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        return organization_out(db, get_org(db, oid))


@router.post("/admin/org-units", response_model=OrganizationOut, status_code=201)
def create_organization(body: OrganizationCreate, request: Request) -> dict[str, Any]:
    with workflow(request, "organization.create", "administration") as (db, actor):
        require_manage(db, body.institution_id, body.parent_id)

        def operation() -> dict[str, Any]:
            if body.parent_id:
                parent = get_org(db, body.parent_id)
                if parent.kind != "college" or parent.status != "active":
                    raise ApiError(
                        409, "INVALID_PARENT", "Choose an active college in this institution."
                    )
            org = OrgUnit(**body.model_dump(exclude={"reason"}))
            db.add(org)
            db.flush()
            audit(
                db,
                request,
                "organization.created",
                "organization",
                org.id,
                org.id,
                org.institution_id,
            )
            return organization_out(db, org).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.patch("/admin/org-units/{oid}", response_model=OrganizationOut)
def edit_organization(oid: UUID, body: OrganizationMetadata, request: Request) -> dict[str, Any]:
    with workflow(request, "organization.edit", "administration") as (db, actor):
        org = get_org(db, oid)

        def operation() -> dict[str, Any]:
            version_check(request, org.version)
            for field in ("name", "code", "timezone"):
                setattr(org, field, getattr(body, field))
            # SQL revision increments even when the submitted metadata is unchanged.
            org.version += 1
            db.flush()
            db.refresh(org)
            audit(db, request, "organization.edited", "organization", oid, oid, org.institution_id)
            return organization_out(db, org).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.put("/admin/org-units/{oid}/enrollment", response_model=OrganizationOut)
def enrollment(oid: UUID, body: EnrollmentInput, request: Request) -> dict[str, Any]:
    with workflow(request, "organization.enrollment", "administration") as (db, actor):
        org = get_org(db, oid)

        def operation() -> dict[str, Any]:
            version_check(request, org.version)
            if org.kind != "department" or org.status != "active":
                raise ApiError(409, "INVALID_ORGANIZATION_STATE", "Choose an active department.")
            option = db.get(EnrollmentOption, oid)
            if option is None:
                option = EnrollmentOption(
                    id=oid, institution_id=org.institution_id, label=org.name, enabled=body.enabled
                )
                db.add(option)
            else:
                option.enabled = body.enabled
            db.flush()
            db.refresh(org)
            audit(
                db,
                request,
                "organization.enrollment.changed",
                "organization",
                oid,
                oid,
                org.institution_id,
            )
            return organization_out(db, org).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


def change_state(oid: UUID, body: ReasonInput, request: Request, status: str) -> dict[str, Any]:
    with workflow(request, "organization." + status, "administration") as (db, actor):
        org = get_org(db, oid)

        def operation() -> dict[str, Any]:
            version_check(request, org.version)
            if org.status == status:
                raise ApiError(
                    409, "STALE_TRANSITION", "Refresh this organization before continuing."
                )
            org.status = status
            db.flush()
            db.refresh(org)
            audit(
                db, request, "organization." + status, "organization", oid, oid, org.institution_id
            )
            return organization_out(db, org).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/admin/org-units/{oid}/archive", response_model=OrganizationOut)
def archive(oid: UUID, body: ReasonInput, request: Request) -> dict[str, Any]:
    return change_state(oid, body, request, "archived")


@router.post("/admin/org-units/{oid}/restore", response_model=OrganizationOut)
def restore(oid: UUID, body: ReasonInput, request: Request) -> dict[str, Any]:
    return change_state(oid, body, request, "active")


@router.get("/admin/org-units/{oid}/history", response_model=Page[AuditOut])
def history(
    oid: UUID,
    request: Request,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "organization.history", purpose) as (db, actor):
        global_read(db, request, purpose)
        get_org(db, oid)
        return paginate(
            db,
            select(AuditEvent).where(
                AuditEvent.org_unit_id == oid, AuditEvent.action.like("organization.%")
            ),
            request,
            oid,
            limit,
            cursor,
            lambda row: AuditOut(
                id=row.id,
                actor_id=row.actor_id,
                action=row.action,
                object_type=row.object_type,
                object_id=row.object_id,
                org_unit_id=row.org_unit_id,
                result=row.result,
                reason_code=row.reason_code,
                correlation_id=row.correlation_id,
                reason=reason_text(db, row.reason_id),
                occurred_at=row.occurred_at,
            ),
            descending=True,
        )


@router.get("/organization-admin-grants", response_model=Page[OrganizationGrantOut])
def grants(
    request: Request, purpose: Purpose | None = None, limit: Limit = 25, cursor: Cursor = None
) -> dict[str, Any]:
    with workflow(request, "organization.grants.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        return paginate(
            db,
            select(OrganizationAdminGrant),
            request,
            None,
            limit,
            cursor,
            OrganizationGrantOut.model_validate,
        )


@router.post("/organization-admin-grants", response_model=OrganizationGrantOut, status_code=201)
def create_grant(body: OrganizationGrantInput, request: Request) -> dict[str, Any]:
    with workflow(request, "organization.grant.create", "administration") as (db, actor):
        require(db, "platform.manage", None)

        def operation() -> dict[str, Any]:
            if body.user_id == actor.user.id:
                raise ApiError(403, "SELF_APPROVAL", "Another super admin must appoint you.")
            if body.valid_until and body.valid_until <= now():
                raise ApiError(422, "INVALID_EXPIRY", "Select a future expiry.")
            if db.get(Institution, body.institution_id) is None:
                raise not_found()
            if body.root_org_unit_id:
                root = get_org(db, body.root_org_unit_id)
                if (
                    root.institution_id != body.institution_id
                    or root.kind != "college"
                    or root.status != "active"
                ):
                    raise not_found()
            grant = OrganizationAdminGrant(**body.model_dump(exclude={"reason"}))
            db.add(grant)
            db.flush()
            audit(
                db,
                request,
                "organization.grant.created",
                "organization_grant",
                grant.id,
                grant.root_org_unit_id,
                grant.institution_id,
            )
            return OrganizationGrantOut.model_validate(grant).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/organization-admin-grants/{gid}/state", response_model=OrganizationGrantOut)
def grant_state(gid: UUID, body: OrganizationGrantState, request: Request) -> dict[str, Any]:
    with workflow(request, "organization.grant.state", "administration") as (db, actor):
        require(db, "platform.manage", None)
        row = db.get(OrganizationAdminGrant, gid)
        if row is None:
            raise not_found()

        def operation() -> dict[str, Any]:
            version_check(request, row.version)
            if body.status not in {
                "active": {"suspended", "revoked"},
                "suspended": {"active", "revoked"},
            }.get(row.status, set()):
                raise ApiError(409, "STALE_TRANSITION", "An explicit appointment is required.")
            if body.status == "active" and row.valid_until and row.valid_until <= now():
                raise ApiError(409, "GRANT_EXPIRED", "An explicit new appointment is required.")
            row.status = body.status
            row.version += 1
            db.flush()
            audit(
                db,
                request,
                "organization.grant." + body.status,
                "organization_grant",
                gid,
                row.root_org_unit_id,
                row.institution_id,
            )
            return OrganizationGrantOut.model_validate(row).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)
