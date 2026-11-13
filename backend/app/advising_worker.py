"""Durable local knowledge/generation worker. Model calls never hold business transactions."""

import argparse
import hashlib
import json
import re
import time
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.advising_models import (
    AdvisingJob,
    AdvisorDraft,
    Conversation,
    EmbeddingConfig,
    EvidenceChunk,
    GovernanceEvaluation,
    GovernanceVersion,
    IndexBuild,
    KnowledgeState,
    RetrievalTrace,
    SourcePublication,
    StudentMessage,
    ValidatedAnswer,
)
from app.advising_services import active_governance, active_guidance, context_key, context_snapshot
from app.config import Settings
from app.db import context, make_engine, safe_runtime_role, transaction
from app.inference import InferenceError, ModelAdapter, ResourceBusy, heavy_resource
from app.intake_models import ExtractionArtifact, ProfileVersion, Source, SourceVersion
from app.models import OutboxEvent
from app.private_storage import PrivateStorage
from app.profiles import allowed
from app.retrieval import candidates, citation_payload, reranked, selection_valid
from app.security import ApiError, now
from app.staff_security import WORKFLOW_LOCK

EVALUATION_FIXTURE: dict[str, Any] = {
    "version": "quote-selection-v1",
    "question": "Which synthetic course is required?",
    "evidence": [{"id": "E1", "text": "Synthetic catalog fixture: SYN101 is required."}],
}
EVALUATION_HASH = hashlib.sha256(
    json.dumps(EVALUATION_FIXTURE, sort_keys=True).encode()
).hexdigest()


def install_scope(db: Session, job: AdvisingJob) -> None:
    context(
        db,
        user_id=str(job.actor_id),
        mfa="true",
        purpose=job.purpose,
        rag_job=str(job.id),
        rag_token=str(job.lease_token),
    )


def authorized(db: Session, job: AdvisingJob) -> bool:
    return allowed(db, "rag_worker_live()") and allowed(
        db,
        "rag_job_target(:kind,:target,:cid,false)",
        kind=job.kind,
        target=job.target_id,
        cid=job.conversation_id,
    )


def current(db: Session, job: AdvisingJob) -> bool:
    if not authorized(db, job):
        return False
    if job.kind in {"answer", "draft"}:
        try:
            assert job.student_membership_id and job.conversation_id
            return job.context_snapshot == context_snapshot(
                db, job.actor_id, job.student_membership_id, job.conversation_id
            )
        except ApiError:
            return False
    return True


def load_job(db: Session, jid: UUID, token: UUID) -> AdvisingJob | None:
    job = db.get(AdvisingJob, jid)
    if (
        not job
        or job.lease_token != token
        or job.state != "running"
        or not job.lease_until
        or job.lease_until <= now()
    ):
        return None
    install_scope(db, job)
    return job


def event(
    db: Session,
    job: AdvisingJob,
    event_type: str,
    aggregate: UUID,
    version: int,
    iid: UUID,
    scope: UUID | None,
) -> None:
    db.execute(
        insert(OutboxEvent)
        .inline()
        .values(
            id=uuid4(),
            event_type=event_type,
            aggregate_id=aggregate,
            aggregate_version=version,
            schema_version=1,
            institution_id=iid,
            org_unit_id=scope,
            actor_id=job.actor_id,
            state="recorded",
            attempts=0,
        )
    )


def finish_index(engine: Engine, cfg: Settings, jid: UUID, token: UUID) -> None:
    with transaction(engine) as db:
        job = load_job(db, jid, token)
        if not job or not current(db, job):
            return
        build = db.get(IndexBuild, job.target_id)
        assert build
        version = db.get(SourceVersion, build.source_version_id)
        assert version
        source = db.get(Source, version.source_id)
        assert source
        configuration = db.get(EmbeddingConfig, build.config_id)
        assert configuration
        artifact = db.scalar(
            select(ExtractionArtifact).where(ExtractionArtifact.source_version_id == version.id)
        )
        if not artifact:
            raise InferenceError("EXTRACTION_REQUIRED")
        key = artifact.object_key
        extractor_version = artifact.extractor_version
        source_hash = version.content_hash
        build.state = "building"
        db.flush()
        spec = configuration.fingerprint
        source_id = source.id
        iid = source.institution_id
        scope = source.org_unit_id
        vid = version.id
        source_version_number = version.version
        bid = build.id
    adapter = ModelAdapter(cfg)
    if adapter.fingerprint != spec:
        raise InferenceError("MODEL_REVISION_MISMATCH")
    data = json.loads(PrivateStorage(cfg.private_storage_path).read(key))
    pieces = []
    for segment in data["segments"]:
        for lo, hi, quote in adapter.split(segment["text"]):
            locator = {k: v for k, v in segment.items() if k != "text"} | {
                "start": lo,
                "end": hi,
                "extractor_version": extractor_version,
                "source_hash": source_hash,
                "chunker_version": "exact-spans-v1-300-overlap40",
            }
            pieces.append((quote, locator))
    if not pieces or len(pieces) > 2000:
        raise InferenceError("INVALID_CHUNK_COUNT")
    vectors = []
    for start in range(0, len(pieces), 8):
        # Reauthorize between embedding batches; no revoked source data reaches a new call.
        with transaction(engine) as db:
            job = load_job(db, jid, token)
            if not job or not current(db, job):
                raise InferenceError("AUTHORIZATION_CHANGED")
        vectors.extend(adapter.embed([p[0] for p in pieces[start : start + 8]]))
    with transaction(engine) as db:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": WORKFLOW_LOCK})
        job = load_job(db, jid, token)
        if not job:
            return
        if not current(db, job):
            job.state = "cancelled"
            job.error_code = "AUTHORIZATION_CHANGED"
            return
        build = db.get(IndexBuild, bid)
        assert build
        for ordinal, ((quote, locator), vector) in enumerate(zip(pieces, vectors, strict=True)):
            db.add(
                EvidenceChunk(
                    build_id=bid,
                    ordinal=ordinal,
                    source_version_id=vid,
                    text=quote,
                    locator=locator,
                    content_hash=hashlib.sha256(quote.encode()).hexdigest(),
                    token_count=adapter.tokens("embedding", quote),
                    embedding=vector,
                )
            )
        db.flush()
        build.chunk_count = len(pieces)
        build.state = "ready"
        build.error_code = None
        event(db, job, "source.indexed", source_id, source_version_number, iid, scope)
        job.state = "completed"
        job.version += 1
        job.lease_token = None
        job.lease_until = None


def base_payload(snapshot: dict[str, Any], disposition: str, reason: str) -> dict[str, Any]:
    return {
        "status": disposition,
        "reason_code": reason,
        "citations": [],
        "guidance": [],
        "rule_checks": [],
        "context_version": context_key(snapshot),
        "stale": False,
        "human_help_available": True,
        "assumptions": ["Academic facts are student-reported unless separately confirmed."],
    }


def point_checks(
    definition: dict[str, Any], facts: dict[str, Any], selected: set[str]
) -> list[dict[str, Any]]:
    courses = facts.get("completed_courses", {}).get("value") or []
    completed = {c["course_id"] for c in courses if c.get("completed") is True}
    unknown = {c["course_id"] for c in courses if c.get("completed") is None}
    results = []
    for rule in definition.get("rules", []):
        if rule["evidence_id"] not in selected:
            continue
        if rule["kind"] == "prerequisite":
            required = set(rule["requires"])
            result = "reported_satisfied" if required <= completed else "unknown"
            results.append(
                {
                    "course_id": rule["course_id"],
                    "kind": rule["kind"],
                    "result": result,
                    "evidence_id": rule["evidence_id"],
                    "missing_facts": sorted(required - completed | (required & unknown)),
                }
            )
        else:
            results.append(
                {
                    "course_id": rule["course_id"],
                    "kind": "course_limit",
                    "maximum": rule["maximum"],
                    "result": "published_limit",
                    "evidence_id": rule["evidence_id"],
                }
            )
    return results


def run_answer(engine: Engine, cfg: Settings, jid: UUID, token: UUID) -> None:
    with transaction(engine) as db:
        job = load_job(db, jid, token)
        if not job or not current(db, job):
            return
        assert job.student_membership_id and job.conversation_id and job.message_id
        mid, cid = job.student_membership_id, job.conversation_id
        conversation = db.get(Conversation, cid)
        assert conversation
        message = db.get(StudentMessage, job.message_id)
        assert message
        profile = db.scalar(
            select(ProfileVersion)
            .where(ProfileVersion.student_membership_id == mid)
            .order_by(ProfileVersion.version.desc())
            .limit(1)
        )
        knowledge = db.get(KnowledgeState, conversation.institution_id)
        configuration = (
            db.get(EmbeddingConfig, knowledge.config_id)
            if knowledge and knowledge.config_id
            else None
        )
        snapshot = dict(job.context_snapshot)
        question = message.text
        profile_complete = bool(profile and profile.status == "complete")
        facts = profile.facts if profile else {}
        missing = [k for k in ("program", "catalog_year") if not facts.get(k, {}).get("value")]
        disputed = bool(
            profile
            and any(
                r["decision"] == "disputed" and r["field"] in {"program", "catalog_year"}
                for r in profile.reviews
            )
        )
        guidance: list[dict[str, Any]] = [
            {
                "id": str(g.id),
                "author_id": str(g.author_id),
                "text": g.text,
                "preferences": g.preferences,
            }
            for g in active_guidance(db, cid)
        ]
        rules = active_governance(
            db, conversation.institution_id, conversation.org_unit_id, "rules"
        )
        preferences = active_governance(
            db, conversation.institution_id, conversation.org_unit_id, "preferences"
        )
        if preferences:
            missing.extend(
                k
                for k in preferences.definition.get("clarification_fields", [])
                if not facts.get(k, {}).get("value")
            )
        terminology = preferences.definition.get("terminology", {}) if preferences else {}
        prompt = active_governance(
            db, conversation.institution_id, conversation.org_unit_id, "prompt"
        )
        rule_definition = rules.definition if rules else {}
        style = prompt.definition.get("style", "concise") if prompt else "concise"
        fingerprint = configuration.fingerprint if configuration else None
    payload = base_payload(snapshot, "needs_advisor", "NO_SUPPORTING_EVIDENCE")
    trace_ids = []
    blocked = False
    if missing or not profile_complete or disputed:
        payload = base_payload(snapshot, "needs_clarification", "PROFILE_REVIEW_REQUIRED")
        payload["missing_fields"] = missing or ["profile_review"]
    elif re.search(
        r"\b(waiv(?:e|er|ing)|exceptions?|override|bypass|skip)\b", question, re.I
    ) or any(
        g["preferences"].get("requested_exception")
        or re.search(r"\b(waiv(?:e|er|ing)|exceptions?|override|bypass|skip)\b", g["text"], re.I)
        for g in guidance
    ):
        payload = base_payload(snapshot, "needs_advisor", "POLICY_EXCEPTION_REQUIRES_REVIEW")
    elif fingerprint:
        adapter = ModelAdapter(cfg)
        if fingerprint != adapter.fingerprint:
            raise InferenceError("MODEL_REVISION_MISMATCH")
        if adapter.tokens("reranker", question) > 128:
            payload = base_payload(snapshot, "needs_clarification", "QUESTION_TOO_LONG")
        else:
            vector = adapter.embed([question], query=True)[0]
            with transaction(engine) as db:
                job = load_job(db, jid, token)
                if not job or not current(db, job):
                    raise InferenceError("AUTHORIZATION_CHANGED")
                rows = candidates(db, mid, question, vector)
            ranked = reranked(adapter, question, rows)
            trace_ids = [str(r["id"]) for r in ranked]
            # Local synthetic calibration admission floor, not an institutional accuracy claim.
            chosen = [row for row in ranked if row["rerank_score"] >= -8.0][:4]
            # Equal-rank duplicate applicable catalogs are conservatively sent for human review.
            catalog_groups: dict[str, set[str]] = {}
            for row in ranked:
                meta = row["metadata_fields"]
                if meta.get("document_class") == "catalog":
                    key = json.dumps(
                        [
                            meta.get(k)
                            for k in (
                                "program",
                                "track",
                                "catalog_start",
                                "catalog_end",
                                "authority_rank",
                            )
                        ]
                    )
                    catalog_groups.setdefault(key, set()).add(str(row["source_id"]))
            if any(len(ids) > 1 for ids in catalog_groups.values()):
                payload = base_payload(snapshot, "needs_advisor", "POTENTIAL_POLICY_CONFLICT")
            elif chosen:
                evidence = [
                    {"id": f"E{i + 1}", "text": row["text"]} for i, row in enumerate(chosen)
                ]
                # Latest access/context must still match before sending retrieved text to chat.
                with transaction(engine) as db:
                    job = load_job(db, jid, token)
                    if not job or not current(db, job):
                        raise InferenceError("AUTHORIZATION_CHANGED")
                selection = adapter.select(question, evidence, guidance, style=style)
                if not selection_valid(selection, evidence):
                    selection = adapter.select(
                        question, evidence, guidance, style=style, repair=True
                    )
                if not selection_valid(selection, evidence):
                    payload = base_payload(snapshot, "needs_advisor", "ANSWER_VALIDATION_FAILED")
                    blocked = True
                else:
                    payload = base_payload(
                        snapshot,
                        selection["disposition"],
                        "EVIDENCE"
                        if selection["disposition"] == "answered"
                        else selection["reason_code"].upper(),
                    )
                    if selection["disposition"] == "answered":
                        by_id = {f"E{i + 1}": row for i, row in enumerate(chosen)}
                        payload["citations"] = [
                            citation_payload(by_id[ref]) for ref in selection["evidence_ids"]
                        ]
                        payload["rule_checks"] = point_checks(
                            rule_definition, facts, {c["id"] for c in payload["citations"]}
                        )
                        if any(
                            g["preferences"].get("max_courses")
                            and check.get("maximum")
                            and g["preferences"]["max_courses"] > check["maximum"]
                            for g in guidance
                            for check in payload["rule_checks"]
                        ):
                            payload["status"] = "needs_advisor"
                            payload["reason_code"] = "POLICY_CONFLICT"
    payload["guidance"] = guidance
    payload["terminology"] = terminology
    with transaction(engine) as db:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": WORKFLOW_LOCK})
        job = load_job(db, jid, token)
        if not job:
            return
        evidence_current = all(
            allowed(
                db,
                "rag_published(:vid,:mid,true)",
                vid=UUID(cite["source_version_id"]),
                mid=job.student_membership_id,
            )
            for cite in payload["citations"]
        )
        if not current(db, job) or not evidence_current:
            job.state = "cancelled"
            job.error_code = "STALE_CONTEXT"
            job.version += 1
            return
        conversation = db.get(Conversation, job.conversation_id)
        assert conversation
        db.add(RetrievalTrace(job_id=jid, evidence_ids=trace_ids, context_snapshot=snapshot))
        if job.kind == "draft":
            db.add(
                AdvisorDraft(
                    job_id=jid,
                    conversation_id=conversation.id,
                    actor_id=job.actor_id,
                    payload=payload,
                )
            )
        else:
            assert job.message_id
            db.add(
                ValidatedAnswer(
                    job_id=jid,
                    conversation_id=conversation.id,
                    message_id=job.message_id,
                    disposition=payload["status"],
                    payload=payload,
                )
            )
        event(
            db,
            job,
            "advisor.draft.completed" if job.kind == "draft" else "generation.completed",
            job.message_id or job.target_id,
            job.attempt,
            conversation.institution_id,
            conversation.org_unit_id,
        )
        db.flush()
        job.state = "blocked" if blocked else "completed"
        job.version += 1
        job.lease_token = None
        job.lease_until = None


def evaluate(engine: Engine, cfg: Settings, jid: UUID, token: UUID) -> None:
    with transaction(engine) as db:
        job = load_job(db, jid, token)
        if not job or not current(db, job):
            return
        governance = db.get(GovernanceVersion, job.target_id)
        assert governance
        knowledge = db.get(KnowledgeState, governance.institution_id)
        if not knowledge:
            raise InferenceError("CONFIGURATION_REQUIRED")
        knowledge_version = knowledge.version
        definition = governance.definition
        gid = governance.id
        iid, scope = governance.institution_id, governance.org_unit_id
        supported = True
        for rule in definition.get("rules", []):
            chunk = db.get(EvidenceChunk, UUID(rule["evidence_id"]))
            version = db.get(SourceVersion, chunk.source_version_id) if chunk else None
            build = db.get(IndexBuild, chunk.build_id) if chunk else None
            source = db.get(Source, version.source_id) if version else None
            publication = db.get(SourcePublication, source.id) if source else None
            if (
                not chunk
                or not version
                or not build
                or not source
                or source.org_unit_id != scope
                or source.institution_id != iid
                or version.metadata_fields.get("document_class") not in {"catalog", "policy"}
                or not publication
                or publication.status != "published"
                or publication.build_id != build.id
            ):
                supported = False
        keys = [(r["course_id"], r["kind"]) for r in definition.get("rules", [])]
        supported = supported and len(keys) == len(set(keys))
    adapter = ModelAdapter(cfg)
    selection = adapter.select(
        EVALUATION_FIXTURE["question"],
        EVALUATION_FIXTURE["evidence"],
        [],
        style=definition.get("style", "concise"),
    )
    passed = (
        supported
        and selection_valid(selection, EVALUATION_FIXTURE["evidence"])
        and selection.get("disposition") == "answered"
        and selection.get("evidence_ids") == ["E1"]
    )
    results = {
        "knowledge_version": knowledge_version,
        "reviewed_rule_references": supported,
        "positive_selection": selection_valid(selection, EVALUATION_FIXTURE["evidence"])
        and selection.get("evidence_ids") == ["E1"],
        "invalid_reference_rejected": not selection_valid(
            {"disposition": "answered", "evidence_ids": ["FORGED"], "reason_code": "evidence"},
            EVALUATION_FIXTURE["evidence"],
        ),
        "provider": "synthetic_mock" if adapter.mock else cfg.inference_provider,
    }
    with transaction(engine) as db:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": WORKFLOW_LOCK})
        job = load_job(db, jid, token)
        if not job:
            return
        knowledge = db.get(KnowledgeState, iid)
        if not current(db, job) or not knowledge or knowledge.version != knowledge_version:
            job.state = "cancelled"
            job.error_code = "STALE_CONTEXT"
            return
        db.add(
            GovernanceEvaluation(
                governance_id=gid,
                fingerprint=adapter.fingerprint,
                dataset_hash=EVALUATION_HASH,
                passed=passed,
                results=results,
            )
        )
        event(db, job, "governance.evaluated", gid, 1, iid, scope)
        db.flush()
        job.state = "completed" if passed else "blocked"
        job.version += 1
        job.lease_token = None
        job.lease_until = None


def process(engine: Engine, cfg: Settings) -> int:
    with transaction(engine) as db:
        if not safe_runtime_role(db, "advisory_rag"):
            raise ValueError("Unsafe RAG worker role")
        for expired in db.scalars(
            select(AdvisingJob)
            .where(AdvisingJob.state == "running", AdvisingJob.lease_until < now())
            .with_for_update(skip_locked=True)
        ):
            expired.state = "failed"
            expired.error_code = "WORKER_INTERRUPTED"
            expired.version += 1
            expired.lease_token = None
            expired.lease_until = None
        job = db.scalar(
            select(AdvisingJob)
            .where(AdvisingJob.state == "queued")
            .order_by(AdvisingJob.created_at, AdvisingJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return 0
        job.state = "running"
        job.version += 1
        job.lease_token = uuid4()
        job.lease_until = now() + timedelta(seconds=600)
        db.flush()
        install_scope(db, job)
        if not current(db, job):
            job.state = "cancelled"
            job.error_code = "STALE_CONTEXT"
            job.version += 1
            return 1
        jid, token, kind = job.id, job.lease_token, job.kind
    try:
        if kind == "index":
            finish_index(engine, cfg, jid, token)
        elif kind == "evaluation":
            evaluate(engine, cfg, jid, token)
        else:
            run_answer(engine, cfg, jid, token)
    except (InferenceError, ApiError, OSError, ValueError, KeyError) as exc:
        with transaction(engine) as db:
            job = load_job(db, jid, token)
            if job:
                code = str(exc) if isinstance(exc, InferenceError) else "PROCESSING_FAILED"
                job.state = "cancelled" if code == "AUTHORIZATION_CHANGED" else "failed"
                job.error_code = code
                job.version += 1
                if kind == "index":
                    build = db.get(IndexBuild, job.target_id)
                    if build:
                        build.state = "failed"
                        build.error_code = code
                job.lease_token = None
                job.lease_until = None
    return 1


def process_once(cfg: Settings) -> int:
    engine = make_engine(cfg.rag_database_url.get_secret_value())
    try:
        try:
            with heavy_resource(engine):
                return process(engine, cfg)
        except ResourceBusy:
            return 0
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    cfg = Settings()
    while True:
        count = process_once(cfg)
        if args.once:
            return
        if not count:
            time.sleep(2)


if __name__ == "__main__":
    main()
