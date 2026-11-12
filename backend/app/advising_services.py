"""Current-scope operations and metadata-only context fingerprints."""

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.advising_models import (
    AdvisingJob,
    AdvisorGuidance,
    Conversation,
    EmbeddingConfig,
    GovernanceActivation,
    GovernanceEvaluation,
    GovernanceVersion,
    IndexBuild,
    KnowledgeState,
    SourcePublication,
    StudentMessage,
    ValidatedAnswer,
)
from app.advising_schemas import BuildOut, GovernanceOut, JobOut, PublicationOut
from app.config import Settings
from app.intake_models import AcademicProfile, Source, SourceVersion
from app.models import StudentMembership, User
from app.profiles import allowed
from app.security import ApiError, AuthContext, now
from app.staff_security import not_found


def runtime_spec(cfg: Settings) -> tuple[str, dict[str, Any]]:
    if cfg.inference_provider == "disabled":
        raise ApiError(
            503, "INFERENCE_DISABLED", "Enable the configured local model runtime first."
        )
    if cfg.inference_provider == "mock":
        data = {"provider": "synthetic-mock", "dimension": 768, "revision": "mock-v1"}
    else:
        try:
            data = json.loads(cfg.inference_manifest_path.read_text())
        except (OSError, ValueError):
            raise ApiError(
                503, "MODEL_ARTIFACTS_UNAVAILABLE", "Prepare the pinned local model artifacts."
            ) from None
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if cfg.inference_provider == "vllm":
        fingerprint = hashlib.sha256((fingerprint + ":vllm:" + cfg.vllm_model).encode()).hexdigest()
    return fingerprint, data


def ensure_config(db: Session, cfg: Settings, iid: UUID) -> tuple[EmbeddingConfig, KnowledgeState]:
    fingerprint, definition = runtime_spec(cfg)
    config = db.scalar(select(EmbeddingConfig).where(EmbeddingConfig.fingerprint == fingerprint))
    if not config:
        config = EmbeddingConfig(fingerprint=fingerprint, definition=definition, dimension=768)
        db.add(config)
        db.flush()
    state = db.get(KnowledgeState, iid)
    if not state:
        state = KnowledgeState(id=iid, version=0, config_id=config.id)
        db.add(state)
        db.flush()
    return config, state


def active_governance(db: Session, iid: UUID, scope: UUID, kind: str) -> GovernanceVersion | None:
    activation = db.scalar(
        select(GovernanceActivation)
        .where(
            GovernanceActivation.institution_id == iid,
            GovernanceActivation.kind == kind,
            GovernanceActivation.org_unit_id.is_(None)
            if kind == "prompt"
            else GovernanceActivation.org_unit_id == scope,
        )
        .order_by(GovernanceActivation.version.desc(), GovernanceActivation.created_at.desc())
        .limit(1)
    )
    return db.get(GovernanceVersion, activation.governance_id) if activation else None


def conversation_for(db: Session, cid: UUID) -> Conversation:
    conversation = db.get(Conversation, cid)
    if not conversation or not allowed(db, "rag_conversation(:id)", id=cid):
        raise not_found()
    return conversation


def source_publishable(db: Session, sid: UUID) -> Source:
    source = db.get(Source, sid)
    if not source or not allowed(db, "rag_publish_source(:id)", id=sid):
        raise not_found()
    return source


def context_snapshot(db: Session, actor_id: UUID, mid: UUID, cid: UUID) -> dict[str, Any]:
    member = db.get(StudentMembership, mid)
    conversation = db.get(Conversation, cid)
    actor = db.get(User, actor_id)
    if not member or not conversation or not actor or not allowed(db, "can_student(:id)", id=mid):
        raise not_found()
    profile = db.get(AcademicProfile, mid)
    knowledge = db.get(KnowledgeState, member.institution_id)
    # Include active guidance IDs, so expiry invalidates output even without a write event.
    guidance = active_guidance(db, cid)
    return {
        "applicability_date": now().date().isoformat(),
        "membership_id": str(mid),
        "relationship_epoch": member.relationship_epoch,
        "profile_version": profile.version if profile else 0,
        "grant_epoch": actor.grant_epoch,
        "guidance_epoch": conversation.guidance_epoch,
        "guidance_ids": [str(g.id) for g in guidance],
        "knowledge_version": knowledge.version if knowledge else 0,
        "config_id": str(knowledge.config_id) if knowledge and knowledge.config_id else None,
    }


def context_key(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def active_guidance(db: Session, cid: UUID) -> list[AdvisorGuidance]:
    rows = list(
        db.scalars(
            select(AdvisorGuidance)
            .where(AdvisorGuidance.conversation_id == cid)
            .order_by(AdvisorGuidance.created_at, AdvisorGuidance.id)
        )
    )
    superseded = {g.supersedes_id for g in rows if g.effective_from <= now()}
    return [
        g
        for g in rows
        if g.id not in superseded
        and g.effective_from <= now()
        and (g.effective_until is None or g.effective_until > now())
    ]


def enqueue(
    db: Session,
    request: Request,
    actor: AuthContext,
    kind: str,
    target: UUID,
    *,
    conversation: Conversation | None = None,
    message: StudentMessage | None = None,
    attempt: int = 1,
) -> AdvisingJob:
    snapshot = (
        context_snapshot(db, actor.user.id, conversation.student_membership_id, conversation.id)
        if conversation
        else {}
    )
    if kind in {"answer", "draft"}:
        count = (
            db.scalar(
                select(func.count())
                .select_from(AdvisingJob)
                .where(
                    AdvisingJob.actor_id == actor.user.id,
                    AdvisingJob.state.in_(["queued", "running"]),
                )
            )
            or 0
        )
        if count >= 4:
            raise ApiError(
                429, "QUEUE_FULL", "Wait for an existing question or draft before retrying."
            )
    job = AdvisingJob(
        kind=kind,
        target_id=target,
        actor_id=actor.user.id,
        grant_epoch=actor.user.grant_epoch,
        student_membership_id=conversation.student_membership_id if conversation else None,
        conversation_id=conversation.id if conversation else None,
        message_id=message.id if message else None,
        purpose=getattr(request.state, "rag_purpose", "support_review"),
        context_snapshot=snapshot,
        attempt=attempt,
    )
    db.add(job)
    db.flush()
    return job


def job_out(job: AdvisingJob) -> JobOut:
    return JobOut.model_validate(job, from_attributes=True)


def publication_out(db: Session, source: Source) -> PublicationOut:
    builds = list(
        db.scalars(
            select(IndexBuild)
            .join(SourceVersion, SourceVersion.id == IndexBuild.source_version_id)
            .where(SourceVersion.source_id == source.id)
            .order_by(IndexBuild.id)
        )
    )
    head = db.get(SourcePublication, source.id)
    return PublicationOut(
        source_id=source.id,
        version=head.version if head else 0,
        build_id=head.build_id if head else None,
        status=head.status if head else "unpublished",
        builds=[BuildOut.model_validate(b, from_attributes=True) for b in builds],
    )


def governance_out(db: Session, g: GovernanceVersion) -> GovernanceOut:
    active = active_governance(db, g.institution_id, g.org_unit_id or g.institution_id, g.kind)
    evaluation = db.scalar(
        select(GovernanceEvaluation)
        .where(GovernanceEvaluation.governance_id == g.id)
        .order_by(GovernanceEvaluation.created_at.desc())
        .limit(1)
    )
    return GovernanceOut(
        id=g.id,
        institution_id=g.institution_id,
        org_unit_id=g.org_unit_id,
        kind=g.kind,
        definition=g.definition,
        active=bool(active and active.id == g.id),
        evaluation_id=evaluation.id if evaluation else None,
        evaluation_passed=evaluation.passed if evaluation else False,
        created_at=g.created_at,
    )


def public_answer(db: Session, answer: ValidatedAnswer) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(json.dumps(answer.payload))
    job = db.get(AdvisingJob, answer.job_id)
    if job and job.student_membership_id:
        try:
            payload["stale"] = context_key(
                context_snapshot(
                    db, job.actor_id, job.student_membership_id, answer.conversation_id
                )
            ) != payload.get("context_version")
        except ApiError:
            payload["stale"] = True
    for citation in payload.get("citations", []):
        pub = db.get(SourcePublication, UUID(citation["source_id"]))
        source = db.get(Source, UUID(citation["source_id"]))
        if not pub or pub.status != "published" or not source or source.archived:
            citation["status"] = "withdrawn"
            citation["quote"] = None
        else:
            build = db.get(IndexBuild, pub.build_id)
            citation["status"] = (
                "published"
                if build and str(build.source_version_id) == citation["source_version_id"]
                else "superseded"
            )
    return payload
