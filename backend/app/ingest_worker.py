"""Trusted host worker. Only disposable parser containers touch untrusted documents."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert, select, text
from sqlalchemy.engine import Engine

from app.config import Settings
from app.db import context, make_engine, safe_runtime_role, transaction
from app.intake_models import ExtractionArtifact, IngestionJob, Source, SourceVersion
from app.models import OutboxEvent
from app.private_storage import PrivateStorage
from app.security import now
from app.staff_security import WORKFLOW_LOCK


class ProcessingError(Exception):
    pass


def sandbox(cfg: Settings, key: str, media: str, mode: str) -> dict[str, Any]:
    if os.getuid() == 0:
        raise ProcessingError("NONROOT_OPERATOR_REQUIRED")
    store = PrivateStorage(cfg.private_storage_path)
    signatures = cfg.scanner_database_path.resolve()
    databases = list(signatures.glob("*.c[lv]d"))
    updated = signatures / "last-successful-update"
    if mode == "scan" and (
        not databases
        or not updated.is_file()
        or now().timestamp() - updated.stat().st_mtime > 48 * 3600
    ):
        raise ProcessingError("SCANNER_UNAVAILABLE")
    name = "advisory-parse-" + uuid4().hex
    try:
        image = subprocess.run(
            ["docker", "image", "inspect", cfg.parser_image, "--format", "{{.Id}}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            "--memory=2g" if mode == "scan" else "--memory=768m",
            "--memory-swap=2g" if mode == "scan" else "--memory-swap=768m",
            "--cpus=1",
            "--ulimit",
            "fsize=16777216:16777216",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m,mode=1777",
            "--mount",
            f"type=bind,src={store.path(key)},dst=/input/document,readonly",
        ]
        if mode == "scan":
            command += ["--mount", f"type=bind,src={signatures},dst=/signatures,readonly"]
        command += [image, mode, media]
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=cfg.parser_timeout_seconds,
            )
            output.seek(0)
            raw = output.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ProcessingError("EXTRACTION_TOO_LARGE")
        parsed: dict[str, Any] = json.loads(raw)
        if result.returncode or parsed.get("error_code"):
            code = parsed.get("error_code", "EXTRACTION_FAILED")
            safe_codes = {
                "UNSAFE_FILE",
                "SCANNER_UNAVAILABLE",
                "ENCRYPTED_FILE",
                "TOO_MANY_PAGES",
                "UNSAFE_ARCHIVE",
                "EXTERNAL_RESOURCE",
                "EXTRACTION_TOO_LARGE",
                "INVALID_TEXT",
                "UNREADABLE_FILE",
                "EXTRACTION_FAILED",
            }
            raise ProcessingError(code if code in safe_codes else "EXTRACTION_FAILED")
        if mode == "scan" and parsed != {"clean": True}:
            raise ProcessingError("SCANNER_UNAVAILABLE")
        if mode == "extract":
            if not isinstance(parsed.get("segments"), list) or not parsed["segments"]:
                raise ProcessingError("UNREADABLE_FILE")
            parsed["extractor_version"] = f"advisory-extractor-0.3:{image}"
        return parsed
    except subprocess.TimeoutExpired:
        raise ProcessingError("PROCESSING_TIMEOUT") from None
    except (OSError, subprocess.CalledProcessError, ValueError):
        raise ProcessingError("PROCESSOR_UNAVAILABLE") from None
    finally:
        try:
            subprocess.run(
                ["docker", "rm", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def worker_scope(db: Any, jid: UUID, token: UUID) -> None:
    context(db, job_id=str(jid), lease_token=str(token))


def current(db: Any, jid: UUID) -> bool:
    return bool(db.scalar(text("SELECT ingest_job_current(:id)"), {"id": jid}))


def process_once(cfg: Settings) -> int:
    engine = make_engine(cfg.ingest_database_url.get_secret_value())
    try:
        return process(engine, cfg)
    finally:
        engine.dispose()


def process(engine: Engine, cfg: Settings) -> int:
    with transaction(engine) as db:
        if not safe_runtime_role(db, "advisory_ingest"):
            raise ValueError("Unsafe ingestion database role")
        # Expired leases are failed explicitly; a current authorized actor may request a retry.
        expired = list(
            db.scalars(
                select(IngestionJob)
                .where(
                    IngestionJob.state.in_(["scanning", "extracting"]),
                    IngestionJob.lease_until < now(),
                )
                .with_for_update(skip_locked=True)
            )
        )
        for expired_job in expired:
            expired_job.state = "failed"
            expired_job.error_code = "WORKER_INTERRUPTED"
            expired_job.lease_token = None
            expired_job.lease_until = None
        job = db.scalar(
            select(IngestionJob)
            .where(IngestionJob.state == "uploaded")
            .order_by(IngestionJob.created_at, IngestionJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return len(expired)
        if not current(db, job.id):
            job.state = "cancelled"
            job.error_code = "AUTHORIZATION_CHANGED"
            return 1
        token = uuid4()
        job.state = "scanning"
        job.lease_token = token
        job.lease_until = now() + timedelta(seconds=cfg.parser_timeout_seconds * 2 + 60)
        db.flush()
        worker_scope(db, job.id, token)
        version = db.get(SourceVersion, job.source_version_id)
        assert version
        jid, vid, key, media, expected_hash = (
            job.id,
            version.id,
            version.object_key,
            version.media_type,
            version.content_hash,
        )
    try:
        store = PrivateStorage(cfg.private_storage_path)
        if hashlib.sha256(store.read(key)).hexdigest() != expected_hash:
            raise ProcessingError("CONTENT_CHANGED")
        sandbox(cfg, key, media, "scan")
        with transaction(engine) as db:
            job = db.get(IngestionJob, jid)
            assert job
            if job.lease_token != token or not current(db, jid):
                if job.lease_token == token:
                    job.state = "cancelled"
                    job.error_code = "AUTHORIZATION_CHANGED"
                return 1
            job.state = "extracting"
        result = sandbox(cfg, key, media, "extract")
        artifact_key = store.write(json.dumps(result).encode(), "artifacts")
        with transaction(engine) as db:
            # Serialize the final authorization check and commit with reassignment/revocation.
            db.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": WORKFLOW_LOCK})
            job = db.scalar(select(IngestionJob).where(IngestionJob.id == jid).with_for_update())
            assert job
            if job.lease_token != token:
                return 1
            if not current(db, jid) or not job.lease_until or job.lease_until <= now():
                job.state = "cancelled"
                job.error_code = "AUTHORIZATION_CHANGED"
                return 1
            worker_scope(db, jid, token)
            version = db.get(SourceVersion, vid)
            assert version
            source = db.get(Source, version.source_id)
            assert source
            db.add(
                ExtractionArtifact(
                    source_version_id=vid,
                    job_id=jid,
                    object_key=artifact_key,
                    extractor_version=result["extractor_version"],
                    ocr=result["ocr"],
                )
            )
            db.execute(
                insert(OutboxEvent)
                .inline()
                .values(
                    id=uuid4(),
                    event_type="source.extracted",
                    aggregate_id=source.id,
                    aggregate_version=version.version,
                    institution_id=source.institution_id,
                    org_unit_id=source.org_unit_id,
                    actor_id=job.actor_id,
                    state="recorded",
                    schema_version=1,
                    attempts=0,
                )
            )
            db.flush()
            job.state = "needs_review"
            job.error_code = None
            job.lease_until = None
            job.lease_token = None
    except (ProcessingError, OSError) as exc:
        with transaction(engine) as db:
            job = db.get(IngestionJob, jid)
            if job and job.lease_token == token:
                job.state = "failed"
                job.error_code = (
                    str(exc) if isinstance(exc, ProcessingError) else "STORAGE_UNAVAILABLE"
                )
                job.lease_until = None
                job.lease_token = None
    return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    cfg = Settings()
    while True:
        processed = process_once(cfg)
        if args.once:
            return
        if not processed:
            time.sleep(2)


if __name__ == "__main__":
    main()
