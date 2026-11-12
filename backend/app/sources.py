"""Authorized source intake. Extraction never constitutes publication."""

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from pydantic import Json
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intake_models import ExtractionArtifact, IngestionJob, Source, SourceVersion
from app.intake_schemas import SourceMetadata, SourceOut, SourceTarget, TextInput
from app.models import StudentMembership
from app.outbox import emit
from app.private_storage import PrivateStorage
from app.profiles import allowed
from app.security import ApiError, AuthContext
from app.staff_routes import Cursor, Limit, global_read
from app.staff_schemas import Page, Purpose
from app.staff_security import audit, not_found, version_check, workflow
from app.staff_services import idempotent, paginate

router = APIRouter(prefix="/api/v1")
MEDIA = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


def storage(request: Request) -> PrivateStorage:
    return PrivateStorage(request.app.state.settings.private_storage_path)


def source_for(db: Session, sid: UUID, writing: bool = False) -> Source:
    source = db.get(Source, sid)
    if not source or not allowed(db, "source_allowed(:sid,:writing)", sid=sid, writing=writing):
        raise not_found()
    return source


def source_out(db: Session, source: Source, version: SourceVersion | None = None) -> SourceOut:
    version = version or db.scalar(
        select(SourceVersion)
        .where(SourceVersion.source_id == source.id)
        .order_by(SourceVersion.version.desc())
        .limit(1)
    )
    assert version
    job = db.scalar(
        select(IngestionJob)
        .where(IngestionJob.source_version_id == version.id)
        .order_by(IngestionJob.attempt.desc())
        .limit(1)
    )
    artifact = db.scalar(
        select(ExtractionArtifact).where(ExtractionArtifact.source_version_id == version.id)
    )
    return SourceOut(
        id=source.id,
        institution_id=source.institution_id,
        org_unit_id=source.org_unit_id,
        student_membership_id=source.student_membership_id,
        visibility=source.visibility,
        version=version.version,
        source_version_id=version.id,
        filename=version.filename,
        metadata=SourceMetadata.model_validate(version.metadata_fields),
        state="archived" if source.archived else job.state if job else "uploaded",
        attempt=job.attempt if job else 0,
        error_code=job.error_code if job else None,
        archived=source.archived,
        download_available=bool(artifact),
        artifact_available=bool(artifact),
        ocr=artifact.ocr if artifact else False,
        created_at=version.created_at,
    )


def authorize_target(db: Session, target: SourceTarget) -> Source | None:
    if not allowed(
        db,
        "source_permission(:iid,:oid,:mid,:visibility,true)",
        iid=target.institution_id,
        oid=target.org_unit_id,
        mid=target.student_membership_id,
        visibility=target.visibility,
    ):
        raise not_found()
    if target.source_id:
        source = source_for(db, target.source_id, True)
        if (
            source.institution_id,
            source.org_unit_id,
            source.student_membership_id,
            source.visibility,
        ) != (
            target.institution_id,
            target.org_unit_id,
            target.student_membership_id,
            target.visibility,
        ):
            raise ApiError(
                422, "IMMUTABLE_SCOPE", "Create a separate authorized source for a new scope."
            )
        return source
    return None


def enqueue(
    db: Session,
    source: Source,
    version: SourceVersion,
    actor: AuthContext,
    purpose: str,
    attempt: int = 1,
) -> None:
    member = (
        db.get(StudentMembership, source.student_membership_id)
        if source.student_membership_id
        else None
    )
    db.add(
        IngestionJob(
            source_version_id=version.id,
            actor_id=actor.user.id,
            grant_epoch=actor.user.grant_epoch,
            relationship_epoch=member.relationship_epoch if member else None,
            purpose=purpose,
            attempt=attempt,
        )
    )


def persist_source(
    db: Session,
    request: Request,
    actor: AuthContext,
    target: SourceTarget,
    data: bytes,
    filename: str,
    media: str,
) -> dict[str, Any]:
    source = authorize_target(db, target)
    payload = target.model_dump(mode="json") | {
        "hash": hashlib.sha256(data).hexdigest(),
        "filename": filename,
        "media_type": media,
    }

    def operation() -> dict[str, Any]:
        nonlocal source
        version_check(request, source.version if source else 0)
        if source is None:
            source = Source(
                institution_id=target.institution_id,
                org_unit_id=target.org_unit_id,
                student_membership_id=target.student_membership_id,
                visibility=target.visibility,
                owner_id=actor.user.id,
                version=0,
            )
            db.add(source)
            db.flush()
        source.version += 1
        key = storage(request).write(data)
        # Rollback may leave a private orphan; it cannot expose an object.
        version = SourceVersion(
            source_id=source.id,
            version=source.version,
            filename=filename,
            media_type=media,
            content_hash=payload["hash"],
            object_key=key,
            metadata_fields=target.metadata.model_dump(mode="json"),
            author_id=actor.user.id,
        )
        db.add(version)
        db.flush()
        enqueue(db, source, version, actor, "document_management")
        emit(db, request, "source.uploaded", source)
        audit(
            db,
            request,
            "source.uploaded",
            "source",
            source.id,
            source.org_unit_id,
            source.institution_id,
        )
        db.flush()
        return source_out(db, source, version).model_dump(mode="json")

    return idempotent(db, request, actor, payload, operation)


@router.post("/sources/text", response_model=SourceOut, status_code=201)
def create_text(body: TextInput, request: Request) -> dict[str, Any]:
    with workflow(request, "source.upload", "document_management") as (db, actor):
        data = body.text.encode("utf-8")
        if len(data) > request.app.state.settings.max_upload_bytes:
            raise ApiError(413, "FILE_TOO_LARGE", "The text exceeds the configured size limit.")
        return persist_source(db, request, actor, body, data, "pasted-text.txt", "text/plain")


@router.post("/sources/uploads", response_model=SourceOut, status_code=201)
def upload_source(
    request: Request,
    target: Annotated[Json[SourceTarget], Form()],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    body = target
    with workflow(request, "source.upload", "document_management") as (db, actor):
        authorize_target(db, body)
        name = re.sub(
            r"[^A-Za-z0-9._ -]",
            "_",
            (file.filename or "document").replace("\\", "/").split("/")[-1],
        )[:160]
        extension = Path(name).suffix.lower()
        if extension not in MEDIA:
            raise ApiError(422, "UNSUPPORTED_FILE", "Use PDF, DOCX, text, or Markdown.")
        data = file.file.read(request.app.state.settings.max_upload_bytes + 1)
        if not data or len(data) > request.app.state.settings.max_upload_bytes:
            raise ApiError(413, "FILE_TOO_LARGE", "The file is empty or exceeds the size limit.")
        if (
            extension == ".pdf"
            and not data.startswith(b"%PDF-")
            or (extension == ".docx" and not data.startswith(b"PK\x03\x04"))
        ):
            raise ApiError(422, "INVALID_FILE", "The file contents do not match its type.")
        return persist_source(db, request, actor, body, data, name, MEDIA[extension])


@router.get("/sources", response_model=Page[SourceOut])
def list_sources(
    request: Request,
    scope_id: UUID | None = None,
    student_membership_id: UUID | None = None,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "source.list", purpose) as (db, actor):
        global_read(db, request, purpose)
        stmt = select(Source)
        if scope_id:
            stmt = stmt.where(Source.org_unit_id == scope_id)
        if student_membership_id:
            stmt = stmt.where(Source.student_membership_id == student_membership_id)
        result = paginate(db, stmt, request, scope_id, limit, cursor, lambda s: source_out(db, s))
        for item in result["items"]:
            entry = item if isinstance(item, SourceOut) else SourceOut.model_validate(item)
            audit(
                db,
                request,
                "source.list.read",
                "source",
                entry.id,
                entry.org_unit_id,
                entry.institution_id,
            )
        return result


@router.get("/sources/{sid}", response_model=SourceOut)
def get_source(
    sid: UUID, request: Request, response: Response, purpose: Purpose | None = None
) -> SourceOut:
    with workflow(request, "source.read", purpose) as (db, actor):
        global_read(db, request, purpose)
        source = source_for(db, sid)
        audit(db, request, "source.read", "source", sid, source.org_unit_id, source.institution_id)
        result = source_out(db, source)
        response.headers["ETag"] = f'"{result.version}"'
        return result


@router.get("/sources/{sid}/versions", response_model=Page[SourceOut])
def source_history(
    sid: UUID,
    request: Request,
    purpose: Purpose | None = None,
    limit: Limit = 25,
    cursor: Cursor = None,
) -> dict[str, Any]:
    with workflow(request, "source.history", purpose) as (db, actor):
        global_read(db, request, purpose)
        source = source_for(db, sid)
        audit(
            db,
            request,
            "source.history.read",
            "source",
            sid,
            source.org_unit_id,
            source.institution_id,
        )
        return paginate(
            db,
            select(SourceVersion).where(SourceVersion.source_id == sid),
            request,
            sid,
            limit,
            cursor,
            lambda v: source_out(db, source, v),
        )


@router.patch("/sources/{sid}/metadata", response_model=SourceOut)
def source_metadata(sid: UUID, body: SourceMetadata, request: Request) -> dict[str, Any]:
    with workflow(request, "source.metadata", "document_management") as (db, actor):
        source = source_for(db, sid, True)
        current = db.scalar(
            select(SourceVersion).where(
                SourceVersion.source_id == sid, SourceVersion.version == source.version
            )
        )
        assert current
        target = SourceTarget(
            institution_id=source.institution_id,
            org_unit_id=source.org_unit_id,
            student_membership_id=source.student_membership_id,
            visibility=source.visibility,
            metadata=body,
            source_id=sid,
        )
        return persist_source(
            db,
            request,
            actor,
            target,
            storage(request).read(current.object_key),
            current.filename,
            current.media_type,
        )


@router.post("/sources/{sid}/retry", response_model=SourceOut)
def retry_source(sid: UUID, request: Request) -> dict[str, Any]:
    with workflow(request, "source.retry", "document_management") as (db, actor):
        source = source_for(db, sid, True)

        def operation() -> dict[str, Any]:
            version_check(request, source.version)
            current = source_out(db, source)
            if current.state not in {"failed", "cancelled"} or current.attempt >= 3:
                raise ApiError(
                    409,
                    "RETRY_UNAVAILABLE",
                    "Replace this file or resolve processing before retrying.",
                )
            version = db.get(SourceVersion, current.source_version_id)
            assert version
            enqueue(db, source, version, actor, "document_management", current.attempt + 1)
            db.flush()
            audit(
                db,
                request,
                "source.retried",
                "source",
                sid,
                source.org_unit_id,
                source.institution_id,
            )
            return source_out(db, source).model_dump(mode="json")

        return idempotent(db, request, actor, {}, operation)


@router.post("/sources/{sid}/archive", response_model=SourceOut)
def archive_source(sid: UUID, request: Request) -> dict[str, Any]:
    with workflow(request, "source.archive", "document_management") as (db, actor):
        source = source_for(db, sid, True)

        def operation() -> dict[str, Any]:
            version_check(request, source.version)
            source.archived = True
            # Content version stays fixed; archive is a separate terminal resource state.
            audit(
                db,
                request,
                "source.archived",
                "source",
                sid,
                source.org_unit_id,
                source.institution_id,
            )
            db.flush()
            return source_out(db, source).model_dump(mode="json")

        return idempotent(db, request, actor, {}, operation)


@router.get("/sources/{sid}/versions/{vid}/download")
def download_source(
    sid: UUID, vid: UUID, request: Request, purpose: Purpose | None = None
) -> Response:
    with workflow(request, "source.download", purpose) as (db, actor):
        global_read(db, request, purpose)
        source = source_for(db, sid)
        version = db.get(SourceVersion, vid)
        artifact = db.scalar(
            select(ExtractionArtifact).where(ExtractionArtifact.source_version_id == vid)
        )
        if not version or version.source_id != sid or not artifact:
            raise not_found()
        audit(
            db,
            request,
            "source.downloaded",
            "source",
            sid,
            source.org_unit_id,
            source.institution_id,
        )
        return Response(
            storage(request).read(version.object_key),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{version.filename}"'},
        )


@router.get("/sources/{sid}/versions/{vid}/extraction")
def extraction(
    sid: UUID, vid: UUID, request: Request, purpose: Purpose | None = None
) -> dict[str, Any]:
    with workflow(request, "source.extraction", purpose) as (db, actor):
        global_read(db, request, purpose)
        source = source_for(db, sid)
        version = db.get(SourceVersion, vid)
        artifact = db.scalar(
            select(ExtractionArtifact).where(ExtractionArtifact.source_version_id == vid)
        )
        if not version or version.source_id != sid or not artifact:
            raise not_found()
        audit(
            db,
            request,
            "source.extraction.read",
            "source",
            sid,
            source.org_unit_id,
            source.institution_id,
        )
        result: dict[str, Any] = json.loads(storage(request).read(artifact.object_key))
        return result
