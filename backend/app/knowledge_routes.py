"""Reviewed publication and versioned, evaluation-gated local knowledge controls."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select, text

from app.advising_contract import RevisionRoute
from app.advising_models import (
    AdvisingJob,
    GovernanceActivation,
    GovernanceEvaluation,
    GovernanceVersion,
    IndexBuild,
    IndexRelease,
    KnowledgeState,
    PublicationEvent,
    SourcePublication,
)
from app.advising_schemas import (
    ActivateInput,
    BuildOut,
    GovernanceInput,
    GovernanceOut,
    IndexedExcerptOut,
    JobOut,
    KnowledgeOut,
    PublicationOut,
    PublishedSourceOut,
    PublishSource,
    RebuildInput,
    ReviewSource,
)
from app.advising_services import (
    enqueue,
    ensure_config,
    governance_out,
    job_out,
    publication_out,
    source_publishable,
)
from app.intake_models import ExtractionArtifact, Source, SourceVersion
from app.models import Institution, OrgUnit
from app.outbox import emit
from app.profiles import allowed, member_for
from app.security import ApiError, now
from app.staff_routes import Cursor, Limit, global_read
from app.staff_schemas import Page, Purpose, ReasonInput
from app.staff_security import audit, not_found, version_check, workflow
from app.staff_services import idempotent, paginate

router = APIRouter(prefix="/api/v1", route_class=RevisionRoute)


@router.get("/sources/{sid}/publication", response_model=PublicationOut)
def publication(sid: UUID, request: Request, purpose: Purpose | None = None) -> PublicationOut:
    with workflow(request, "knowledge.publication.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        source = source_publishable(db, sid)
        audit(
            db,
            request,
            "knowledge.publication.read",
            "source",
            sid,
            source.org_unit_id,
            source.institution_id,
        )
        return publication_out(db, source)


@router.post("/sources/{sid}/index", response_model=BuildOut, status_code=201)
def index(sid: UUID, body: ReviewSource, request: Request) -> dict[str, Any]:
    with workflow(request, "knowledge.index", "knowledge_management") as (db, actor):
        source = source_publishable(db, sid)
        version = db.get(SourceVersion, body.source_version_id)
        if not version or version.source_id != sid:
            raise not_found()
        if not db.scalar(
            select(ExtractionArtifact.id).where(ExtractionArtifact.source_version_id == version.id)
        ):
            raise ApiError(
                409,
                "EXTRACTION_REQUIRED",
                "Clean extraction must finish before metadata review and indexing.",
            )

        def operation() -> dict[str, Any]:
            version_check(request, source.version)
            config, state = ensure_config(db, request.app.state.settings, source.institution_id)
            existing = db.scalar(
                select(IndexBuild).where(
                    IndexBuild.source_version_id == version.id, IndexBuild.config_id == config.id
                )
            )
            if existing:
                previous = db.scalar(
                    select(AdvisingJob)
                    .where(AdvisingJob.kind == "index", AdvisingJob.target_id == existing.id)
                    .order_by(AdvisingJob.attempt.desc())
                    .limit(1)
                )
                if previous and previous.state in {"failed", "cancelled"}:
                    if previous.attempt >= 3 or existing.chunk_count:
                        raise ApiError(
                            409,
                            "BUILD_RETRY_LIMIT",
                            "Create a replacement version after reviewing this failure.",
                        )
                    existing.state = "queued"
                    existing.error_code = None
                    enqueue(db, request, actor, "index", existing.id, attempt=previous.attempt + 1)
                return BuildOut.model_validate(existing, from_attributes=True).model_dump(
                    mode="json"
                )
            build = IndexBuild(
                source_version_id=version.id,
                config_id=config.id,
                reviewed_by=actor.user.id,
                review_reason=body.reason,
            )
            db.add(build)
            db.flush()
            request.state.rag_purpose = "knowledge_management"
            enqueue(db, request, actor, "index", build.id)
            audit(
                db,
                request,
                "source.index.requested",
                "source",
                sid,
                source.org_unit_id,
                source.institution_id,
            )
            return BuildOut.model_validate(build, from_attributes=True).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/sources/{sid}/publish", response_model=PublicationOut)
def publish(sid: UUID, body: PublishSource, request: Request) -> dict[str, Any]:
    with workflow(request, "knowledge.publish", "knowledge_management") as (db, actor):
        source = source_publishable(db, sid)

        def operation() -> dict[str, Any]:
            head = db.get(SourcePublication, sid)
            version_check(request, head.version if head else 0)
            build = db.get(IndexBuild, body.build_id)
            version = db.get(SourceVersion, build.source_version_id) if build else None
            knowledge = db.get(KnowledgeState, source.institution_id)
            if (
                not build
                or not version
                or version.source_id != sid
                or build.state != "ready"
                or not build.chunk_count
            ):
                raise ApiError(
                    409,
                    "INDEX_NOT_READY",
                    "Choose a complete reviewed index build for this source.",
                )
            if not knowledge or knowledge.config_id != build.config_id:
                raise ApiError(
                    409,
                    "INDEX_CONFIG_CHANGED",
                    "Activate a complete compatible index release first.",
                )
            if not head:
                head = SourcePublication(
                    id=sid,
                    build_id=build.id,
                    version=0,
                    publisher_id=actor.user.id,
                    reason=body.reason,
                )
                db.add(head)
            head.version += 1
            head.build_id = build.id
            head.status = "published"
            head.publisher_id = actor.user.id
            head.reason = body.reason
            head.published_at = now()
            db.add(
                PublicationEvent(
                    source_id=sid,
                    build_id=build.id,
                    version=head.version,
                    action="published",
                    actor_id=actor.user.id,
                    reason=body.reason,
                )
            )
            db.flush()
            db.refresh(knowledge)
            audit(
                db,
                request,
                "source.published",
                "source",
                sid,
                source.org_unit_id,
                source.institution_id,
            )
            emit(db, request, "source.published", source, aggregate_version=head.version)
            return publication_out(db, source).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/sources/{sid}/withdraw", response_model=PublicationOut)
def withdraw(sid: UUID, body: ReasonInput, request: Request) -> dict[str, Any]:
    with workflow(request, "knowledge.withdraw", "knowledge_management") as (db, actor):
        source = source_publishable(db, sid)

        def operation() -> dict[str, Any]:
            head = db.get(SourcePublication, sid)
            if not head:
                raise not_found()
            version_check(request, head.version)
            if head.status != "published":
                raise ApiError(409, "ALREADY_WITHDRAWN", "Refresh the publication status.")
            head.status = "withdrawn"
            head.version += 1
            head.reason = body.reason
            head.publisher_id = actor.user.id
            db.add(
                PublicationEvent(
                    source_id=sid,
                    build_id=head.build_id,
                    version=head.version,
                    action="withdrawn",
                    actor_id=actor.user.id,
                    reason=body.reason,
                )
            )
            db.flush()
            emit(db, request, "source.withdrawn", source, aggregate_version=head.version)
            audit(
                db,
                request,
                "source.withdrawn",
                "source",
                sid,
                source.org_unit_id,
                source.institution_id,
            )
            return publication_out(db, source).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/knowledge/state", response_model=KnowledgeOut)
def knowledge_state(
    institution_id: UUID, request: Request, purpose: Purpose | None = None
) -> KnowledgeOut:
    with workflow(request, "knowledge.state", purpose) as (db, actor):
        global_read(db, request, purpose)
        if not db.get(Institution, institution_id):
            raise not_found()
        state = db.get(KnowledgeState, institution_id)
        return KnowledgeOut(
            version=state.version if state else 0, config_id=state.config_id if state else None
        )


@router.post("/knowledge/rebuild/activate", response_model=KnowledgeOut)
def activate_rebuild(body: RebuildInput, request: Request) -> dict[str, Any]:
    with workflow(request, "knowledge.rebuild.activate", "knowledge_management") as (db, actor):
        if not allowed(db, "rag_cap('prompt.manage',NULL)"):
            raise not_found()
        if not db.get(Institution, body.institution_id):
            raise not_found()

        def operation() -> dict[str, Any]:
            config, state = ensure_config(db, request.app.state.settings, body.institution_id)
            version_check(request, state.version)
            publications = list(
                db.scalars(
                    select(SourcePublication)
                    .join(Source, Source.id == SourcePublication.id)
                    .where(
                        Source.institution_id == body.institution_id,
                        Source.archived.is_(False),
                        SourcePublication.status == "published",
                    )
                )
            )
            builds = [db.get(IndexBuild, bid) for bid in body.build_ids]
            if any(not b or b.state != "ready" or b.config_id != config.id for b in builds):
                raise ApiError(
                    409,
                    "INCOMPLETE_RELEASE",
                    "Every replacement build must be ready and use the pinned configuration.",
                )
            required = {db.get(IndexBuild, p.build_id).source_version_id for p in publications}  # type: ignore[union-attr]
            if {b.source_version_id for b in builds if b} != required or len(builds) != len(
                required
            ):
                raise ApiError(
                    409,
                    "INCOMPLETE_RELEASE",
                    "Rebuild every currently published source version before switching.",
                )
            by_version = {b.source_version_id: b for b in builds if b}
            manifest = []
            for pub in publications:
                previous = db.get(IndexBuild, pub.build_id)
                assert previous
                build = by_version[previous.source_version_id]
                pub.build_id = build.id
                pub.version += 1
                pub.publisher_id = actor.user.id
                pub.reason = body.reason
                db.add(
                    PublicationEvent(
                        source_id=pub.id,
                        build_id=build.id,
                        version=pub.version,
                        action="reindexed",
                        actor_id=actor.user.id,
                        reason=body.reason,
                    )
                )
                manifest.append(
                    {
                        "source_id": str(pub.id),
                        "source_version_id": str(build.source_version_id),
                        "build_id": str(build.id),
                    }
                )
            state.config_id = config.id
            state.version += 1
            db.flush()
            db.refresh(state)
            db.add(
                IndexRelease(
                    institution_id=body.institution_id,
                    config_id=config.id,
                    version=state.version,
                    manifest=manifest,
                    actor_id=actor.user.id,
                    reason=body.reason,
                )
            )
            audit(
                db,
                request,
                "knowledge.release.activated",
                "institution",
                body.institution_id,
                institution=body.institution_id,
            )
            return KnowledgeOut(version=state.version, config_id=state.config_id).model_dump(
                mode="json"
            )

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


def require_governance(db: Any, g: GovernanceVersion) -> None:
    action = "prompt.manage" if g.kind == "prompt" else "rules.manage"
    if not allowed(db, "rag_cap(:action,:scope)", action=action, scope=g.org_unit_id):
        raise not_found()


@router.get("/knowledge/governance", response_model=Page[GovernanceOut])
def list_governance(
    request: Request,
    institution_id: UUID,
    scope_id: UUID | None = None,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "governance.list", purpose) as (db, actor):
        global_read(db, request, purpose)
        if not allowed(
            db,
            "rag_cap(:action,:scope)",
            action="rules.manage" if scope_id else "prompt.manage",
            scope=scope_id,
        ):
            raise not_found()
        stmt = select(GovernanceVersion).where(
            GovernanceVersion.institution_id == institution_id,
            GovernanceVersion.org_unit_id == scope_id
            if scope_id
            else GovernanceVersion.org_unit_id.is_(None),
        )
        return paginate(db, stmt, request, scope_id, limit, cursor, lambda g: governance_out(db, g))


@router.post("/knowledge/governance", response_model=GovernanceOut, status_code=201)
def create_governance(body: GovernanceInput, request: Request) -> dict[str, Any]:
    with workflow(request, "governance.create", "knowledge_management") as (db, actor):
        probe = GovernanceVersion(
            **body.model_dump(exclude={"definition"}), definition={}, actor_id=actor.user.id
        )
        require_governance(db, probe)
        if not db.get(Institution, body.institution_id):
            raise not_found()
        if body.org_unit_id:
            org = db.get(OrgUnit, body.org_unit_id)
            if not org or org.institution_id != body.institution_id:
                raise not_found()

        def operation() -> dict[str, Any]:
            config, state = ensure_config(db, request.app.state.settings, body.institution_id)
            version_check(request, state.version)
            probe.definition = body.definition.model_dump(mode="json")
            db.add(probe)
            db.flush()
            audit(
                db,
                request,
                "governance.created",
                "governance",
                probe.id,
                body.org_unit_id,
                body.institution_id,
            )
            return governance_out(db, probe).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/knowledge/governance/{gid}/evaluate", response_model=JobOut, status_code=201)
def evaluate_governance(gid: UUID, request: Request) -> dict[str, Any]:
    with workflow(request, "governance.evaluate", "knowledge_management") as (db, actor):
        governance = db.get(GovernanceVersion, gid)
        if not governance:
            raise not_found()
        require_governance(db, governance)

        def operation() -> dict[str, Any]:
            version_check(request, 0)
            request.state.rag_purpose = "knowledge_management"
            return job_out(enqueue(db, request, actor, "evaluation", gid)).model_dump(mode="json")

        return idempotent(db, request, actor, {}, operation)


@router.post("/knowledge/governance/{gid}/activate", response_model=GovernanceOut)
def activate_governance(gid: UUID, body: ActivateInput, request: Request) -> dict[str, Any]:
    with workflow(request, "governance.activate", "knowledge_management") as (db, actor):
        governance = db.get(GovernanceVersion, gid)
        if not governance:
            raise not_found()
        require_governance(db, governance)

        def operation() -> dict[str, Any]:
            config, state = ensure_config(db, request.app.state.settings, governance.institution_id)
            version_check(request, state.version)
            evaluation = db.get(GovernanceEvaluation, body.evaluation_id)
            if (
                not evaluation
                or evaluation.governance_id != gid
                or not evaluation.passed
                or evaluation.fingerprint != config.fingerprint
                or evaluation.results.get("knowledge_version") != state.version
            ):
                raise ApiError(
                    409,
                    "EVALUATION_REQUIRED",
                    "Run a passing current evaluation before activation or rollback.",
                )
            db.add(
                GovernanceActivation(
                    governance_id=gid,
                    institution_id=governance.institution_id,
                    org_unit_id=governance.org_unit_id,
                    kind=governance.kind,
                    version=state.version + 1,
                    actor_id=actor.user.id,
                    reason=body.reason,
                )
            )
            db.flush()
            audit(
                db,
                request,
                "governance.activated",
                "governance",
                gid,
                governance.org_unit_id,
                governance.institution_id,
            )
            return governance_out(db, governance).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/sources/{sid}/indexed-excerpts", response_model=Page[IndexedExcerptOut])
def indexed_excerpts(
    sid: UUID,
    request: Request,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    from app.advising_models import EvidenceChunk
    from app.advising_schemas import IndexedExcerptOut

    with workflow(request, "knowledge.excerpts", purpose) as (db, actor):
        global_read(db, request, purpose)
        source_publishable(db, sid)
        head = db.get(SourcePublication, sid)

        def projection(row: EvidenceChunk) -> IndexedExcerptOut:
            version = db.get(SourceVersion, row.source_version_id)
            assert version
            return IndexedExcerptOut(
                id=row.id,
                source_id=sid,
                source_version_id=version.id,
                build_id=row.build_id,
                ordinal=row.ordinal,
                title=version.metadata_fields["title"],
                text=row.text,
                locator=row.locator,
                published=bool(
                    head and head.build_id == row.build_id and head.status == "published"
                ),
            )

        stmt = (
            select(EvidenceChunk)
            .join(SourceVersion, SourceVersion.id == EvidenceChunk.source_version_id)
            .where(SourceVersion.source_id == sid)
        )
        return paginate(db, stmt, request, sid, limit, cursor, projection)


@router.get("/students/{mid}/published-sources", response_model=Page[PublishedSourceOut])
def published_sources(
    mid: UUID,
    request: Request,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "publication.student.list", purpose) as (db, actor):
        global_read(db, request, purpose)
        member_for(db, mid)
        stmt = (
            select(SourcePublication)
            .join(IndexBuild, IndexBuild.id == SourcePublication.build_id)
            .where(text("rag_published(index_builds.source_version_id,:mid,true)"))
            .params(mid=mid)
        )

        def projection(row: SourcePublication) -> PublishedSourceOut:
            build = db.get(IndexBuild, row.build_id)
            assert build
            version = db.get(SourceVersion, build.source_version_id)
            assert version
            return PublishedSourceOut(
                source_id=row.id,
                source_version_id=version.id,
                title=version.metadata_fields["title"],
                published_at=row.published_at,
            )

        audit(db, request, "publication.student.list", "student", mid)
        return paginate(db, stmt, request, mid, limit, cursor, projection)
