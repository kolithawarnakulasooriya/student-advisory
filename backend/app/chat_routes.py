"""Typed student/advisor actions. Notes and drafts never join student message projections."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.advising_contract import RevisionRoute
from app.advising_models import (
    AdvisingCase,
    AdvisingJob,
    AdvisorDraft,
    AdvisorGuidance,
    CaseEvent,
    Conversation,
    EvidenceChunk,
    SourcePublication,
    StaffNote,
    StudentMessage,
    ValidatedAnswer,
)
from app.advising_schemas import (
    AnswerOut,
    CaseEventOut,
    CaseInput,
    CaseOut,
    CaseTransition,
    CitationOut,
    ConversationInput,
    ConversationOut,
    DraftInput,
    DraftOut,
    GuidanceInput,
    JobOut,
    MessageOut,
    NoteInput,
    NoteOut,
    PublishDraft,
    QuestionInput,
)
from app.advising_services import active_guidance, conversation_for, enqueue, job_out, public_answer
from app.assignments import current_assignment
from app.intake_models import SourceVersion
from app.models import User
from app.outbox import emit
from app.profiles import allowed, member_for
from app.security import ApiError, now
from app.staff_routes import Cursor, Limit, global_read
from app.staff_schemas import Page, Purpose
from app.staff_security import audit, not_found, version_check, workflow
from app.staff_services import idempotent, paginate

router = APIRouter(prefix="/api/v1", route_class=RevisionRoute)


def conversation_out(c: Conversation) -> ConversationOut:
    return ConversationOut.model_validate(c, from_attributes=True)


@router.get("/conversations", response_model=Page[ConversationOut])
def conversations(
    request: Request,
    student_membership_id: UUID,
    limit: Limit = 25,
    cursor: Cursor = None,
    purpose: Purpose | None = None,
) -> dict[str, Any]:
    with workflow(request, "conversation.list", purpose) as (db, actor):
        global_read(db, request, purpose)
        member_for(db, student_membership_id)
        return paginate(
            db,
            select(Conversation).where(Conversation.student_membership_id == student_membership_id),
            request,
            student_membership_id,
            limit,
            cursor,
            conversation_out,
        )


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(body: ConversationInput, request: Request) -> dict[str, Any]:
    with workflow(request, "conversation.create") as (db, actor):
        member = member_for(db, body.student_membership_id)
        if not allowed(db, "profile_owner(:id)", id=member.id):
            raise not_found()

        def operation() -> dict[str, Any]:
            conversation = Conversation(
                student_membership_id=member.id,
                institution_id=member.institution_id,
                org_unit_id=member.org_unit_id,
                title=body.title,
            )
            db.add(conversation)
            db.flush()
            audit(
                db,
                request,
                "conversation.created",
                "conversation",
                conversation.id,
                member.org_unit_id,
                member.institution_id,
            )
            return conversation_out(conversation).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/conversations/{cid}", response_model=ConversationOut)
def get_conversation(
    cid: UUID, request: Request, purpose: Purpose | None = None
) -> ConversationOut:
    with workflow(request, "conversation.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        c = conversation_for(db, cid)
        audit(
            db, request, "conversation.read", "conversation", cid, c.org_unit_id, c.institution_id
        )
        return conversation_out(c)


def message_out(db: Any, m: StudentMessage) -> MessageOut:
    author = db.get(User, m.author_id)
    jobs = list(
        db.scalars(
            select(AdvisingJob)
            .where(AdvisingJob.message_id == m.id, AdvisingJob.kind == "answer")
            .order_by(AdvisingJob.attempt)
        )
    )
    answers = list(
        db.scalars(
            select(ValidatedAnswer)
            .where(ValidatedAnswer.message_id == m.id)
            .order_by(ValidatedAnswer.created_at)
        )
    )
    return MessageOut(
        id=m.id,
        author_id=m.author_id,
        author_name=author.name if author else "Student",
        type="student_question",
        text=m.text,
        created_at=m.created_at,
        jobs=[job_out(j) for j in jobs],
        answers=[
            AnswerOut(
                id=a.id,
                message_id=a.message_id,
                disposition=a.disposition,
                payload=public_answer(db, a),
                created_at=a.created_at,
            )
            for a in answers
        ],
    )


@router.get("/conversations/{cid}/messages", response_model=Page[MessageOut])
def messages(
    cid: UUID,
    request: Request,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "conversation.messages", purpose) as (db, actor):
        global_read(db, request, purpose)
        c = conversation_for(db, cid)
        audit(
            db,
            request,
            "conversation.messages.read",
            "conversation",
            cid,
            c.org_unit_id,
            c.institution_id,
        )
        return paginate(
            db,
            select(StudentMessage).where(StudentMessage.conversation_id == cid),
            request,
            cid,
            limit,
            cursor,
            lambda m: message_out(db, m),
        )


@router.post("/conversations/{cid}/messages", response_model=MessageOut, status_code=201)
def question(cid: UUID, body: QuestionInput, request: Request) -> dict[str, Any]:
    with workflow(request, "student.question") as (db, actor):
        c = conversation_for(db, cid)
        if not allowed(db, "rag_owner(:id)", id=cid):
            raise not_found()

        def operation() -> dict[str, Any]:
            version_check(request, c.version)
            message = StudentMessage(conversation_id=cid, author_id=actor.user.id, text=body.text)
            db.add(message)
            db.flush()
            c.version += 1
            db.flush()
            job = enqueue(db, request, actor, "answer", message.id, conversation=c, message=message)
            emit(db, request, "student.message.created", c, aggregate_id=message.id)
            emit(db, request, "generation.requested", c, aggregate_id=job.id)
            audit(
                db,
                request,
                "student.question.created",
                "conversation",
                cid,
                c.org_unit_id,
                c.institution_id,
            )
            return message_out(db, message).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/jobs/{jid}", response_model=JobOut)
def job(jid: UUID, request: Request, purpose: Purpose | None = None) -> JobOut:
    with workflow(request, "advising.job.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        j = db.get(AdvisingJob, jid)
        if not j or not allowed(db, "rag_job_read(:id)", id=jid):
            raise not_found()
        return job_out(j)


@router.post("/jobs/{jid}/retry", response_model=JobOut, status_code=201)
def retry(jid: UUID, request: Request) -> dict[str, Any]:
    with workflow(request, "advising.job.retry") as (db, actor):
        previous = db.get(AdvisingJob, jid)
        if not previous or previous.kind not in {"answer", "draft"}:
            raise not_found()
        c = conversation_for(db, previous.conversation_id)  # type: ignore[arg-type]
        if not allowed(
            db, "rag_owner(:id)" if previous.kind == "answer" else "rag_advisor(:id)", id=c.id
        ):
            raise not_found()

        def operation() -> dict[str, Any]:
            version_check(request, previous.version)
            latest = db.scalar(
                select(AdvisingJob)
                .where(
                    AdvisingJob.message_id == previous.message_id, AdvisingJob.kind == previous.kind
                )
                .order_by(AdvisingJob.attempt.desc())
                .limit(1)
            )
            if (
                not latest
                or latest.id != previous.id
                or previous.state not in {"failed", "cancelled", "blocked"}
                or previous.attempt >= 3
            ):
                raise ApiError(
                    409, "RETRY_UNAVAILABLE", "Refresh the question or ask a new question."
                )
            m = db.get(StudentMessage, previous.message_id)
            assert m
            result = enqueue(
                db,
                request,
                actor,
                previous.kind,
                m.id,
                conversation=c,
                message=m,
                attempt=previous.attempt + 1,
            )
            return job_out(result).model_dump(mode="json")

        return idempotent(db, request, actor, {}, operation)


def guidance_out(db: Any, g: AdvisorGuidance, active_ids: set[UUID]) -> MessageOut:
    user = db.get(User, g.author_id)
    return MessageOut(
        id=g.id,
        author_id=g.author_id,
        author_name=user.name if user else "Advisor",
        type="student_visible_guidance",
        text=g.text,
        created_at=g.created_at,
        effective_from=g.effective_from,
        effective_until=g.effective_until,
        supersedes_id=g.supersedes_id,
        active=g.id in active_ids,
        preferences=g.preferences,
    )


@router.get("/conversations/{cid}/guidance", response_model=Page[MessageOut])
def guidance_list(
    cid: UUID,
    request: Request,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "guidance.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        c = conversation_for(db, cid)
        active = {g.id for g in active_guidance(db, cid)}
        audit(db, request, "guidance.read", "conversation", cid, c.org_unit_id, c.institution_id)
        return paginate(
            db,
            select(AdvisorGuidance).where(AdvisorGuidance.conversation_id == cid),
            request,
            cid,
            limit,
            cursor,
            lambda g: guidance_out(db, g, active),
        )


def persist_guidance(
    db: Any, request: Request, c: Conversation, actor: Any, body: GuidanceInput
) -> MessageOut:
    if not allowed(db, "rag_advisor(:id)", id=c.id):
        raise not_found()
    if body.supersedes_id:
        original = db.get(AdvisorGuidance, body.supersedes_id)
        if not original or original.conversation_id != c.id:
            raise not_found()
        if db.scalar(
            select(AdvisorGuidance.id).where(AdvisorGuidance.supersedes_id == original.id)
        ):
            raise ApiError(
                409, "GUIDANCE_SUPERSEDED", "Refresh and choose the current guidance version."
            )
    effective = body.effective_from or now()
    if body.effective_until and body.effective_until <= effective:
        raise ApiError(422, "INVALID_EXPIRY", "Guidance must expire after it takes effect.")
    guidance = AdvisorGuidance(
        conversation_id=c.id,
        author_id=actor.user.id,
        text=body.text,
        effective_from=effective,
        effective_until=body.effective_until,
        supersedes_id=body.supersedes_id,
        preferences=body.preferences.model_dump(mode="json"),
    )
    db.add(guidance)
    c.guidance_epoch += 1
    c.version += 1
    db.flush()
    emit(db, request, "advisor.guidance.added", c, aggregate_id=guidance.id)
    audit(
        db, request, "advisor.guidance.added", "conversation", c.id, c.org_unit_id, c.institution_id
    )
    return guidance_out(db, guidance, {g.id for g in active_guidance(db, c.id)})


@router.post("/conversations/{cid}/guidance", response_model=MessageOut, status_code=201)
def add_guidance(cid: UUID, body: GuidanceInput, request: Request) -> dict[str, Any]:
    with workflow(request, "advisor.guidance.add") as (db, actor):
        c = conversation_for(db, cid)
        if not allowed(db, "rag_advisor(:id)", id=cid):
            raise not_found()

        def operation() -> dict[str, Any]:
            version_check(request, c.version)
            return persist_guidance(db, request, c, actor, body).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/guidance/{gid}/supersede", response_model=MessageOut, status_code=201)
def supersede(gid: UUID, body: GuidanceInput, request: Request) -> dict[str, Any]:
    with workflow(request, "advisor.guidance.supersede") as (db, actor):
        original = db.get(AdvisorGuidance, gid)
        if not original:
            raise not_found()
        c = conversation_for(db, original.conversation_id)
        if not allowed(db, "rag_advisor(:id)", id=c.id):
            raise not_found()

        def operation() -> dict[str, Any]:
            version_check(request, c.version)
            return persist_guidance(
                db, request, c, actor, body.model_copy(update={"supersedes_id": gid})
            ).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/conversations/{cid}/notes", response_model=Page[NoteOut])
def notes(
    cid: UUID,
    request: Request,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "staff.notes.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        c = conversation_for(db, cid)
        if not allowed(db, "rag_staff(:id)", id=c.student_membership_id):
            raise not_found()
        audit(db, request, "staff.notes.read", "conversation", cid, c.org_unit_id, c.institution_id)
        return paginate(
            db,
            select(StaffNote).where(StaffNote.conversation_id == cid),
            request,
            cid,
            limit,
            cursor,
            lambda n: NoteOut.model_validate(n, from_attributes=True),
        )


@router.post("/conversations/{cid}/notes", response_model=NoteOut, status_code=201)
def add_note(cid: UUID, body: NoteInput, request: Request) -> dict[str, Any]:
    with workflow(request, "staff.note.create") as (db, actor):
        c = conversation_for(db, cid)
        if not allowed(db, "rag_advisor(:id)", id=cid):
            raise not_found()

        def operation() -> dict[str, Any]:
            note = StaffNote(conversation_id=cid, author_id=actor.user.id, text=body.text)
            db.add(note)
            db.flush()
            audit(
                db,
                request,
                "staff.note.created",
                "staff_note",
                note.id,
                c.org_unit_id,
                c.institution_id,
            )
            return NoteOut.model_validate(note, from_attributes=True).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.post("/conversations/{cid}/advisor-drafts", response_model=JobOut, status_code=201)
def draft(cid: UUID, body: DraftInput, request: Request) -> dict[str, Any]:
    with workflow(request, "advisor.draft.request") as (db, actor):
        c = conversation_for(db, cid)
        if not allowed(db, "rag_advisor(:id)", id=cid):
            raise not_found()
        m = db.get(StudentMessage, body.message_id)
        if not m or m.conversation_id != cid:
            raise not_found()

        def operation() -> dict[str, Any]:
            version_check(request, c.version)
            last = db.scalar(
                select(AdvisingJob)
                .where(AdvisingJob.message_id == m.id, AdvisingJob.kind == "draft")
                .order_by(AdvisingJob.attempt.desc())
                .limit(1)
            )
            if last:
                raise ApiError(409, "DRAFT_EXISTS", "Review the existing draft or retry its job.")
            return job_out(
                enqueue(db, request, actor, "draft", m.id, conversation=c, message=m)
            ).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/conversations/{cid}/advisor-drafts", response_model=Page[DraftOut])
def drafts(
    cid: UUID,
    request: Request,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "advisor.draft.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        conversation_for(db, cid)
        if not allowed(db, "rag_advisor(:id)", id=cid):
            raise not_found()
        return paginate(
            db,
            select(AdvisorDraft).where(AdvisorDraft.conversation_id == cid),
            request,
            cid,
            limit,
            cursor,
            lambda d: DraftOut.model_validate(d, from_attributes=True),
        )


@router.post("/advisor-drafts/{did}/publish", response_model=MessageOut, status_code=201)
def publish_draft(did: UUID, body: PublishDraft, request: Request) -> dict[str, Any]:
    with workflow(request, "advisor.draft.publish") as (db, actor):
        draft_row = db.get(AdvisorDraft, did)
        if not draft_row:
            raise not_found()
        c = conversation_for(db, draft_row.conversation_id)
        if not allowed(db, "rag_advisor(:id)", id=c.id):
            raise not_found()

        def operation() -> dict[str, Any]:
            version_check(request, c.version)
            j = db.get(AdvisingJob, draft_row.job_id)
            from app.advising_services import context_snapshot

            if not j or j.context_snapshot != context_snapshot(
                db, j.actor_id, c.student_membership_id, c.id
            ):
                raise ApiError(
                    409,
                    "STALE_DRAFT",
                    "Request a draft using the current context before publishing.",
                )
            return persist_guidance(
                db,
                request,
                c,
                actor,
                GuidanceInput(text=body.text, effective_until=body.effective_until),
            ).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/citations/{eid}", response_model=CitationOut)
def citation(eid: UUID, request: Request, purpose: Purpose | None = None) -> CitationOut:
    with workflow(request, "citation.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        chunk = db.get(EvidenceChunk, eid)
        if not chunk or not allowed(db, "rag_citation(:id)", id=eid):
            raise not_found()
        frozen = None
        for answer in db.scalars(
            select(ValidatedAnswer).where(
                ValidatedAnswer.payload["citations"].contains([{"id": str(eid)}])
            )
        ):
            frozen = next(
                (c for c in public_answer(db, answer).get("citations", []) if c["id"] == str(eid)),
                None,
            )
            if frozen:
                break
        version = db.get(SourceVersion, chunk.source_version_id)
        if frozen:
            sid = UUID(frozen["source_id"])
            status = frozen.get("status", "withdrawn")
            result = CitationOut(
                id=eid,
                source_id=sid,
                source_version_id=chunk.source_version_id,
                title=frozen["title"],
                locator=frozen["locator"],
                text=frozen.get("quote"),
                status=status,
                published_at=frozen.get("published_at"),
            )
        elif version:
            publication = db.get(SourcePublication, version.source_id)
            if not publication or publication.status != "published":
                raise not_found()
            result = CitationOut(
                id=eid,
                source_id=version.source_id,
                source_version_id=version.id,
                title=version.metadata_fields["title"],
                locator=chunk.locator,
                text=chunk.text,
                status="published",
                published_at=publication.published_at,
            )
        else:
            raise not_found()
        audit(db, request, "citation.read", "source", result.source_id)
        return result


def case_out(db: Any, row: AdvisingCase) -> CaseOut:
    assignment = current_assignment(db, row.student_membership_id)
    if assignment and not allowed(db, "effective_grant(:id)", id=assignment.advisor_grant_id):
        assignment = None
    return CaseOut.model_validate(
        {
            **{
                k: getattr(row, k)
                for k in (
                    "id",
                    "student_membership_id",
                    "conversation_id",
                    "institution_id",
                    "org_unit_id",
                    "status",
                    "version",
                    "reason",
                    "created_at",
                )
            },
            "assigned_advisor_id": assignment.advisor_grant_id if assignment else None,
            "route": "advisor" if assignment else "manager_queue",
        }
    )


@router.post("/cases", response_model=CaseOut, status_code=201)
def create_case(body: CaseInput, request: Request) -> dict[str, Any]:
    with workflow(request, "case.create") as (db, actor):
        member = member_for(db, body.student_membership_id)
        if (
            body.conversation_id
            and conversation_for(db, body.conversation_id).student_membership_id != member.id
        ):
            raise not_found()

        def operation() -> dict[str, Any]:
            row = AdvisingCase(
                student_membership_id=member.id,
                conversation_id=body.conversation_id,
                institution_id=member.institution_id,
                org_unit_id=member.org_unit_id,
                reason=body.reason,
            )
            db.add(row)
            db.flush()
            db.add(
                CaseEvent(case_id=row.id, actor_id=actor.user.id, status="open", text=body.reason)
            )
            emit(db, request, "case.created", row)
            audit(db, request, "case.created", "case", row.id, row.org_unit_id, row.institution_id)
            return case_out(db, row).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)


@router.get("/cases", response_model=Page[CaseOut])
def cases(
    request: Request,
    scope_id: UUID,
    student_membership_id: UUID | None = None,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "case.list", purpose) as (db, actor):
        global_read(db, request, purpose)
        stmt = select(AdvisingCase).where(AdvisingCase.org_unit_id == scope_id)
        if student_membership_id:
            stmt = stmt.where(AdvisingCase.student_membership_id == student_membership_id)
        return paginate(db, stmt, request, scope_id, limit, cursor, lambda c: case_out(db, c))


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: UUID, request: Request, purpose: Purpose | None = None) -> CaseOut:
    with workflow(request, "case.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        row = db.get(AdvisingCase, case_id)
        if not row:
            raise not_found()
        audit(db, request, "case.read", "case", case_id, row.org_unit_id, row.institution_id)
        return case_out(db, row)


@router.get("/cases/{case_id}/history", response_model=Page[CaseEventOut])
def case_history(
    case_id: UUID,
    request: Request,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "case.history", purpose) as (db, actor):
        global_read(db, request, purpose)
        if not db.get(AdvisingCase, case_id):
            raise not_found()
        return paginate(
            db,
            select(CaseEvent).where(CaseEvent.case_id == case_id),
            request,
            case_id,
            limit,
            cursor,
            lambda e: CaseEventOut.model_validate(e, from_attributes=True),
        )


@router.patch("/cases/{case_id}", response_model=CaseOut)
def transition_case(case_id: UUID, body: CaseTransition, request: Request) -> dict[str, Any]:
    with workflow(request, "case.transition", "support_review") as (db, actor):
        row = db.get(AdvisingCase, case_id)
        if not row:
            raise not_found()
        staff = allowed(db, "rag_staff(:id)", id=row.student_membership_id)

        def operation() -> dict[str, Any]:
            version_check(request, row.version)
            transitions = {
                "open": {"assigned", "in_progress", "cancelled"},
                "assigned": {"in_progress", "cancelled"},
                "in_progress": {"waiting_for_student", "resolved", "cancelled"},
                "waiting_for_student": {"in_progress", "resolved", "cancelled"},
                "resolved": {"open"},
                "cancelled": {"open"},
            }
            if body.status not in transitions.get(row.status, set()) or (
                not staff and body.status not in {"cancelled", "open"}
            ):
                raise ApiError(
                    409,
                    "INVALID_TRANSITION",
                    "Choose an allowed case transition for your current role.",
                )
            row.status = body.status
            row.version += 1
            db.add(
                CaseEvent(
                    case_id=row.id, actor_id=actor.user.id, status=body.status, text=body.text
                )
            )
            db.flush()
            emit(db, request, "case.updated", row)
            audit(db, request, "case.updated", "case", case_id, row.org_unit_id, row.institution_id)
            return case_out(db, row).model_dump(mode="json")

        return idempotent(db, request, actor, body.model_dump(mode="json"), operation)
