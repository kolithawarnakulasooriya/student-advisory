"""Versioned department schemas, student facts and append-only advisor reviews."""

import copy
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.intake_models import AcademicProfile, OnboardingConfig, OnboardingSchema, ProfileVersion
from app.intake_schemas import (
    ConfigOut,
    ContextOut,
    Definition,
    FactInput,
    ProfileInput,
    ProfileOut,
    ReviewInput,
    SchemaInput,
    SchemaOut,
)
from app.models import OrgUnit, StudentMembership
from app.outbox import emit
from app.security import ApiError, now
from app.staff_routes import Cursor, Limit, global_read
from app.staff_schemas import Page, Purpose
from app.staff_security import audit, not_found, version_check, workflow
from app.staff_services import idempotent, paginate

router = APIRouter(prefix="/api/v1")


def allowed(db: Session, expression: str, **values: Any) -> bool:
    return bool(db.scalar(text("SELECT " + expression), values))


def member_for(db: Session, mid: UUID) -> StudentMembership:
    member = db.get(StudentMembership, mid)
    if member is None or not allowed(db, "can_student(:mid)", mid=mid):
        raise not_found()
    return member


def config_for(db: Session, oid: UUID) -> ConfigOut:
    head = db.get(OnboardingConfig, oid)
    schemas = list(
        db.scalars(
            select(OnboardingSchema)
            .where(OnboardingSchema.org_unit_id == oid)
            .order_by(OnboardingSchema.version.desc())
        )
    )
    return ConfigOut(
        version=head.version if head else 0,
        active_schema_id=head.active_schema_id if head else None,
        schemas=[SchemaOut.model_validate(s, from_attributes=True) for s in schemas],
    )


@router.get("/departments/{oid}/onboarding-schemas", response_model=ConfigOut)
def get_config(
    oid: UUID, request: Request, response: Response, purpose: Purpose | None = None
) -> ConfigOut:
    with workflow(request, "profile.schema.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        if not allowed(db, "schema_read(:oid)", oid=oid):
            raise not_found()
        result = config_for(db, oid)
        response.headers["ETag"] = f'"{result.version}"'
        return result


@router.post("/departments/{oid}/onboarding-schemas", response_model=ConfigOut, status_code=201)
def save_schema(oid: UUID, body: SchemaInput, request: Request) -> dict[str, Any]:
    with workflow(request, "profile.schema.create", "administration") as (db, actor):
        org = db.get(OrgUnit, oid)
        if (
            not org
            or org.kind != "department"
            or not allowed(db, "intake_cap('profile.configure',:oid)", oid=oid)
        ):
            raise not_found()

        def operation() -> dict[str, Any]:
            head = db.get(OnboardingConfig, oid)
            version_check(request, head.version if head else 0)
            if not head:
                head = OnboardingConfig(id=oid, version=0)
                db.add(head)
            head.version += 1
            schema = OnboardingSchema(
                institution_id=org.institution_id,
                org_unit_id=oid,
                version=head.version,
                definition=body.definition.model_dump(mode="json"),
                author_id=actor.user.id,
            )
            db.add(schema)
            db.flush()
            if body.activate:
                head.active_schema_id = schema.id
            db.flush()
            audit(
                db,
                request,
                "profile.schema.created",
                "onboarding_schema",
                schema.id,
                oid,
                org.institution_id,
            )
            return config_for(db, oid).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/departments/{oid}/onboarding-schemas/{sid}/activate", response_model=ConfigOut)
def activate_schema(oid: UUID, sid: UUID, request: Request) -> dict[str, Any]:
    with workflow(request, "profile.schema.activate", "administration") as (db, actor):
        if not allowed(db, "intake_cap('profile.configure',:oid)", oid=oid):
            raise not_found()
        schema = db.get(OnboardingSchema, sid)
        if not schema or schema.org_unit_id != oid:
            raise not_found()

        def operation() -> dict[str, Any]:
            head = db.get(OnboardingConfig, oid)
            if not head:
                raise not_found()
            version_check(request, head.version)
            head.version += 1
            head.active_schema_id = sid
            db.flush()
            audit(
                db,
                request,
                "profile.schema.activated",
                "onboarding_schema",
                sid,
                oid,
                schema.institution_id,
            )
            return config_for(db, oid).model_dump(mode="json")

        return idempotent(db, request, actor, {"schema_id": str(sid)}, operation)


def latest(db: Session, mid: UUID) -> ProfileVersion | None:
    return db.scalar(
        select(ProfileVersion)
        .where(ProfileVersion.student_membership_id == mid)
        .order_by(ProfileVersion.version.desc())
        .limit(1)
    )


def missing(definition: Definition, facts: dict[str, Any]) -> list[str]:
    return [
        q.key
        for q in definition.fields
        if q.required and (q.key not in facts or facts[q.key]["value"] in (None, "", []))
    ]


def context_version(member: StudentMembership, version: int) -> str:
    return f"{member.id}:{version}:{member.relationship_epoch}"


def profile_out(
    db: Session, member: StudentMembership, snapshot: ProfileVersion | None
) -> ProfileOut:
    cfg = db.get(OnboardingConfig, member.org_unit_id)
    active = cfg.active_schema_id if cfg else None
    schema = (
        db.get(OnboardingSchema, snapshot.schema_id if snapshot else active)
        if (snapshot or active)
        else None
    )
    facts = snapshot.facts if snapshot else {}
    return ProfileOut(
        student_membership_id=member.id,
        institution_id=member.institution_id,
        org_unit_id=member.org_unit_id,
        version=snapshot.version if snapshot else 0,
        context_version=context_version(member, snapshot.version if snapshot else 0),
        status=snapshot.status if snapshot else "not_started",
        profile_schema=SchemaOut.model_validate(schema, from_attributes=True) if schema else None,
        active_schema_id=active,
        schema_update_available=bool(snapshot and snapshot.schema_id != active),
        missing_fields=missing(Definition.model_validate(schema.definition), facts)
        if schema
        else ["department_configuration"],
        facts=facts,
        reviews=snapshot.reviews if snapshot else [],
        created_at=snapshot.created_at if snapshot else None,
    )


@router.get("/students/{mid}/profile", response_model=ProfileOut)
def get_profile(
    mid: UUID, request: Request, response: Response, purpose: Purpose | None = None
) -> ProfileOut:
    with workflow(request, "profile.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        member = member_for(db, mid)
        audit(
            db, request, "profile.read", "profile", mid, member.org_unit_id, member.institution_id
        )
        result = profile_out(db, member, latest(db, mid))
        response.headers["ETag"] = f'"{result.version}"'
        return result


def validate_facts(body: ProfileInput, definition: Definition) -> None:
    questions = {q.key: q for q in definition.fields}
    for key, fact in body.facts.items():
        if key not in questions:
            # Retain historical values on schema adoption without treating them as new answers.
            raise ApiError(422, "INVALID_FIELD", "Use fields in the selected schema.")
        q = questions[key]
        value = fact.value
        valid = value is None
        if value is not None:
            if q.kind in {"text", "choice"}:
                valid = isinstance(value, str) and len(value) <= 4000
                if q.kind == "choice":
                    valid = valid and (value == "" or value in q.choices)
                if key.endswith("_term") and value:
                    valid = valid and value in definition.terms
            elif q.kind == "number":
                valid = (
                    isinstance(value, (float, int))
                    and not isinstance(value, bool)
                    and 0 <= value <= 1000
                )
            elif q.kind == "courses":
                valid = isinstance(value, list) and len(value) <= 200
                if isinstance(value, list) and valid:
                    for course in value:
                        if not isinstance(course, dict) or set(course) - {
                            "course_id",
                            "grade",
                            "completed",
                        }:
                            valid = False
                            break
                        if (
                            not isinstance(course.get("course_id"), str)
                            or not 1 <= len(str(course["course_id"])) <= 100
                        ):
                            valid = False
                            break
                        if course.get("completed") is not None and not isinstance(
                            course.get("completed"), bool
                        ):
                            valid = False
                        if course.get("grade") is not None and (
                            not isinstance(course["grade"], str) or len(course["grade"]) > 20
                        ):
                            valid = False
        if not valid or (fact.effective_term and fact.effective_term not in definition.terms):
            raise ApiError(422, "INVALID_FACT", "Check the academic fact and its applicable term.")
        if fact.last_confirmed and fact.last_confirmed > now().date():
            raise ApiError(
                422, "INVALID_CONFIRMATION", "Confirmation dates cannot be in the future."
            )
    program = body.facts.get("program")
    track = body.facts.get("track")
    if (
        program
        and track
        and track.value
        and track.value not in definition.program_tracks.get(str(program.value), [])
    ):
        raise ApiError(422, "INVALID_TRACK", "Choose a track for the selected program.")


@router.patch("/students/{mid}/profile", response_model=ProfileOut)
def save_profile(mid: UUID, body: ProfileInput, request: Request) -> dict[str, Any]:
    with workflow(request, "profile.update") as (db, actor):
        member = member_for(db, mid)
        if not allowed(db, "profile_owner(:mid)", mid=mid):
            raise not_found()

        def operation() -> dict[str, Any]:
            previous = latest(db, mid)
            version_check(request, previous.version if previous else 0)
            cfg = db.get(OnboardingConfig, member.org_unit_id)
            schema = db.get(OnboardingSchema, body.schema_id)
            if (
                not schema
                or schema.org_unit_id != member.org_unit_id
                or not cfg
                or (
                    body.schema_id != cfg.active_schema_id
                    and (not previous or body.schema_id != previous.schema_id)
                )
            ):
                raise ApiError(409, "SCHEMA_CHANGED", "Refresh and review the department schema.")
            definition = Definition.model_validate(schema.definition)
            validate_facts(body, definition)
            facts = copy.deepcopy(previous.facts) if previous else {}
            changed = set()
            for key, fact in body.facts.items():
                raw = fact.model_dump(mode="json")
                old = facts.get(key)
                if not old or any(old.get(k) != v for k, v in raw.items()):
                    facts[key] = {
                        **raw,
                        "source": "student_entered",
                        "verification": "self_reported",
                        "author_id": str(actor.user.id),
                        "recorded_at": now().isoformat(),
                    }
                    changed.add(key)
            # Validate retained facts against the adopted schema before marking it complete.
            if body.status == "complete":
                current_keys = {q.key for q in definition.fields}
                merged = body.model_copy(
                    update={
                        "facts": {
                            key: FactInput(
                                **{
                                    k: value.get(k)
                                    for k in ("value", "effective_term", "last_confirmed")
                                }
                            )
                            for key, value in facts.items()
                            if key in current_keys
                        }
                    }
                )
                validate_facts(merged, definition)
            if body.status == "complete" and (
                missing(definition, facts) or not body.catalog_confirmed
            ):
                raise ApiError(
                    422, "PROFILE_INCOMPLETE", "Complete required facts and confirm the catalog."
                )
            head = db.get(AcademicProfile, mid)
            if not head:
                head = AcademicProfile(id=mid, version=0)
                db.add(head)
            head.version += 1
            snapshot = ProfileVersion(
                student_membership_id=mid,
                institution_id=member.institution_id,
                org_unit_id=member.org_unit_id,
                version=head.version,
                schema_id=schema.id,
                status=body.status,
                facts=facts,
                author_id=actor.user.id,
                reviews=[r for r in previous.reviews if r["field"] not in changed]
                if previous
                else [],
            )
            db.add(snapshot)
            db.flush()
            emit(db, request, "profile.changed", snapshot, aggregate_id=mid)
            audit(
                db,
                request,
                "profile.changed",
                "profile",
                mid,
                member.org_unit_id,
                member.institution_id,
            )
            return profile_out(db, member, snapshot).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/students/{mid}/profile/reviews", response_model=ProfileOut)
def review_profile(mid: UUID, body: ReviewInput, request: Request) -> dict[str, Any]:
    with workflow(request, "profile.review") as (db, actor):
        member = member_for(db, mid)
        if not allowed(db, "profile_reviewer(:mid)", mid=mid):
            raise not_found()

        def operation() -> dict[str, Any]:
            previous = latest(db, mid)
            if not previous or body.field not in previous.facts:
                raise not_found()
            version_check(request, previous.version)
            head = db.get(AcademicProfile, mid)
            assert head
            head.version += 1
            snapshot = ProfileVersion(
                student_membership_id=mid,
                institution_id=member.institution_id,
                org_unit_id=member.org_unit_id,
                version=head.version,
                schema_id=previous.schema_id,
                status=previous.status,
                facts=copy.deepcopy(previous.facts),
                author_id=actor.user.id,
                reviews=[
                    *previous.reviews,
                    {
                        **body.model_dump(),
                        "author_id": str(actor.user.id),
                        "created_at": now().isoformat(),
                    },
                ],
            )
            db.add(snapshot)
            db.flush()
            emit(db, request, "profile.changed", snapshot, aggregate_id=mid)
            audit(
                db,
                request,
                "profile.reviewed",
                "profile",
                mid,
                member.org_unit_id,
                member.institution_id,
            )
            return profile_out(db, member, snapshot).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/students/{mid}/profile/history", response_model=Page[ProfileOut])
def profile_history(
    mid: UUID,
    request: Request,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "profile.history", purpose) as (db, actor):
        global_read(db, request, purpose)
        member = member_for(db, mid)
        audit(
            db,
            request,
            "profile.history.read",
            "profile",
            mid,
            member.org_unit_id,
            member.institution_id,
        )
        return paginate(
            db,
            select(ProfileVersion).where(ProfileVersion.student_membership_id == mid),
            request,
            mid,
            limit,
            cursor,
            lambda p: profile_out(db, member, p),
        )


@router.get("/students/{mid}/profile/context", response_model=ContextOut)
def profile_context(
    mid: UUID, request: Request, context: str, purpose: Purpose | None = None
) -> ContextOut:
    with workflow(request, "profile.context", purpose) as (db, actor):
        global_read(db, request, purpose)
        member = member_for(db, mid)
        audit(
            db,
            request,
            "profile.context.read",
            "profile",
            mid,
            member.org_unit_id,
            member.institution_id,
        )
        head = db.get(AcademicProfile, mid)
        current = context_version(member, head.version if head else 0)
        return ContextOut(context_version=current, stale=context != current)
