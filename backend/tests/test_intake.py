"""Real PostgreSQL boundaries and immutable student/document workflows."""

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import context, make_engine
from app.ingest_worker import ProcessingError, process_once
from app.intake_models import IngestionJob, ProfileVersion, SourceVersion
from app.intake_schemas import synthetic_definition
from app.models import OutboxEvent, RoleGrant
from app.seed import fixture_id
from tests.conftest import login
from tests.test_staff import mutate

MID = fixture_id("grant:student-a:department-a")
A = fixture_id("department-a")
INST = fixture_id("synthetic")
BASE = f"students/{MID}/profile"


@pytest.fixture(autouse=True)
def private_files(settings, tmp_path):
    settings.private_storage_path = tmp_path / "private"
    settings.ingest_database_url = SecretStr(
        "postgresql+psycopg://advisory_ingest:local-ingest-only@127.0.0.1:5432/advisory_test"
    )


def profile(client):
    r = client.get("/api/v1/" + BASE)
    assert r.status_code == 200, r.text
    return r.json()


def save(client, facts=None, version=0, status="draft", schema=None, confirmed=False, key=None):
    current = profile(client)
    return mutate(
        client,
        "PATCH",
        BASE,
        {
            "schema_id": schema or current["schema"]["id"],
            "status": status,
            "facts": facts or {},
            "catalog_confirmed": confirmed,
        },
        version=version,
        key=key,
    )


def target():
    return {
        "institution_id": str(INST),
        "org_unit_id": str(A),
        "student_membership_id": str(MID),
        "visibility": "student",
        "metadata": {"title": "Synthetic evidence"},
    }


def upload(client, content="Synthetic student evidence", key=None):
    return mutate(client, "POST", "sources/text", {**target(), "text": content}, version=0, key=key)


def test_profile_resume_history_review_and_context(client, seeded):
    login(client)
    p = profile(client)
    assert p["status"] == "not_started" and "catalog_year" in p["missing_fields"]
    r = save(client, {"program": {"value": "Synthetic Program"}})
    assert r.status_code == 200, r.text
    assert r.json()["facts"]["program"]["verification"] == "self_reported"
    old_context = r.json()["context_version"]
    assert save(client, version=0).status_code == 409
    assert save(client, status="complete", version=1).status_code == 422
    r = save(
        client,
        {
            "catalog_year": {"value": "2026"},
            "completed_courses": {"value": [{"course_id": "SYN101"}]},
        },
        version=1,
        status="complete",
        confirmed=True,
    )
    assert r.status_code == 200, r.text
    assert "completed" not in r.json()["facts"]["completed_courses"]["value"][0]
    assert client.get("/api/v1/" + BASE + "/context", params={"context": old_context}).json()[
        "stale"
    ]
    assert client.get("/api/v1/" + BASE + "/history").json()["total"] == 2
    login(client, "advisor-a", True)
    r = mutate(
        client,
        "POST",
        BASE + "/reviews",
        {
            "field": "catalog_year",
            "decision": "disputed",
            "reason": "Synthetic catalog clarification",
        },
        version=2,
    )
    assert r.status_code == 200, r.text
    assert r.json()["facts"]["catalog_year"]["verification"] == "self_reported"
    assert r.json()["reviews"][0]["decision"] == "disputed"
    login(client)
    r = save(client, {"catalog_year": {"value": "2026", "last_confirmed": "2026-01-01"}}, version=3)
    assert r.status_code == 200, r.text
    assert r.json()["reviews"] == []
    with Session(seeded) as db:
        events = list(
            db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "profile.changed"))
        )
        assert len(events) == 4
        assert all(e.state == "recorded" for e in events)


def test_profile_idempotency_validation_schema_adoption(client, seeded):
    login(client)
    key = str(uuid4())
    r = save(client, {"program": {"value": "Synthetic Program"}}, key=key)
    assert r.status_code == 200, r.text
    assert save(client, {"program": {"value": "Synthetic Program"}}, key=key).json() == r.json()
    assert save(client, {"catalog_year": {"value": "1900"}}, version=1).status_code == 422
    assert (
        save(
            client,
            {"program": {"value": "Synthetic Program", "verification": "verified"}},
            version=1,
        ).status_code
        == 422
    )
    login(client, "manager", True)
    definition = synthetic_definition().model_dump(mode="json")
    definition["fields"].append(
        {"key": "goal_detail", "label": "Goal detail", "kind": "text", "required": True}
    )
    r = mutate(
        client,
        "POST",
        f"departments/{A}/onboarding-schemas",
        {"definition": definition, "activate": True},
        version=1,
    )
    assert r.status_code == 201, r.text
    schema = r.json()["active_schema_id"]
    login(client)
    assert profile(client)["schema_update_available"]
    r = save(client, version=1, schema=schema)
    assert r.status_code == 200, r.text
    assert r.json()["facts"]["program"]["value"] == "Synthetic Program"
    assert "goal_detail" in r.json()["missing_fields"]
    assert client.get("/api/v1/" + BASE + "/history").json()["total"] == 2


@pytest.mark.parametrize(
    "account,mfa,status",
    [
        ("student-b", False, 404),
        ("advisor-b", True, 404),
        ("secretary", True, 404),
        ("secretary-no-delegation", True, 404),
        ("platform-admin", True, 404),
        ("pending", False, 404),
        ("suspended", False, 401),
        ("revoked", False, 404),
        ("other-institution", True, 404),
        ("unverified", False, 403),
    ],
)
def test_profile_access_matrix(client, account, mfa, status):
    if account == "suspended":
        from tests.conftest import post

        assert post(client, "auth/sign-in", {"email": "suspended@advisory.test"}).status_code == 401
    else:
        login(client, account, mfa)
    response = client.get("/api/v1/" + BASE)
    assert response.status_code == status, response.text
    assert client.get("/api/v1/" + BASE + "/history").status_code == status
    assert client.get("/api/v1/" + BASE + "/context?context=x").status_code == status


def test_sources_scope_metadata_and_revocation(client, seeded):
    login(client, "advisor-a", True)
    r = upload(client)
    assert r.status_code == 201, r.text
    s = r.json()
    sid = s["id"]
    vid = s["source_version_id"]
    assert s["state"] == "uploaded" and not s["download_available"]
    assert client.get(f"/api/v1/sources/{sid}/versions/{vid}/download").status_code == 404
    forged = {
        **target(),
        "visibility": "institution",
        "student_membership_id": None,
        "org_unit_id": None,
    }
    assert (
        mutate(
            client, "POST", "sources/text", {**forged, "text": "Synthetic"}, version=0
        ).status_code
        == 404
    )
    login(client)
    assert client.get(f"/api/v1/sources/{sid}").status_code == 200
    assert upload(client).status_code == 404
    for account, mfa in [
        ("student-b", False),
        ("advisor-b", True),
        ("secretary", True),
        ("platform-admin", True),
    ]:
        login(client, account, mfa)
        assert client.get(f"/api/v1/sources/{sid}").status_code == 404
        assert client.get(f"/api/v1/sources/{sid}/versions").status_code == 404
        assert client.get("/api/v1/sources").json()["total"] == 0
    login(client, "advisor-a", True)
    grant = fixture_id("grant:advisor-a:department-a")
    with Session(seeded) as db, db.begin():
        row = db.get(RoleGrant, grant)
        row.status = "suspended"
    assert client.get(f"/api/v1/sources/{sid}").status_code in {401, 404}


def test_worker_real_db_commit_retry_and_revocation(client, seeded, settings, monkeypatch):
    login(client, "advisor-a", True)
    s = upload(client).json()
    calls = []

    def parser(cfg, key, media, mode):
        calls.append(mode)
        if mode == "scan":
            return {"clean": True}
        return {
            "segments": [{"line": 1, "text": "Synthetic evidence"}],
            "ocr": False,
            "extractor_version": "synthetic-test-only",
        }

    monkeypatch.setattr("app.ingest_worker.sandbox", parser)
    assert process_once(settings) == 1
    assert calls == ["scan", "extract"]
    r = client.get("/api/v1/sources/" + s["id"])
    assert r.json()["state"] == "needs_review", r.text
    assert r.json()["download_available"]
    assert (
        client.get(
            f"/api/v1/sources/{s['id']}/versions/{s['source_version_id']}/download"
        ).status_code
        == 200
    )
    assert process_once(settings) == 0
    s2 = upload(client, "Synthetic second document").json()

    def failure(*args):
        raise ProcessingError("SCANNER_UNAVAILABLE")

    monkeypatch.setattr("app.ingest_worker.sandbox", failure)
    assert process_once(settings) == 1
    assert client.get("/api/v1/sources/" + s2["id"]).json()["error_code"] == "SCANNER_UNAVAILABLE"
    r = mutate(client, "POST", f"sources/{s2['id']}/retry", {}, version=1)
    assert r.status_code == 200, r.text
    assert r.json()["attempt"] == 2
    with Session(seeded) as db, db.begin():
        db.get(RoleGrant, fixture_id("grant:advisor-a:department-a")).status = "suspended"
    assert process_once(settings) == 1
    with Session(seeded) as db:
        jobs = list(
            db.scalars(
                select(IngestionJob).where(
                    IngestionJob.source_version_id == s2["source_version_id"]
                )
            )
        )
        assert {j.state for j in jobs} == {"failed", "cancelled"}
        assert (
            len(
                list(
                    db.scalars(
                        select(OutboxEvent).where(OutboxEvent.event_type == "source.extracted")
                    )
                )
            )
            == 1
        )


def test_worker_revoked_during_extraction_and_expired_lease(client, seeded, settings, monkeypatch):
    login(client, "advisor-a", True)
    s = upload(client).json()

    def parser(cfg, key, media, mode):
        if mode == "extract":
            with Session(seeded) as db, db.begin():
                db.get(RoleGrant, fixture_id("grant:advisor-a:department-a")).status = "suspended"
        return (
            {"clean": True}
            if mode == "scan"
            else {
                "segments": [{"text": "Synthetic"}],
                "ocr": False,
                "extractor_version": "synthetic-test",
            }
        )

    monkeypatch.setattr("app.ingest_worker.sandbox", parser)
    process_once(settings)
    with Session(seeded) as db:
        job = db.scalar(
            select(IngestionJob).where(IngestionJob.source_version_id == s["source_version_id"])
        )
        assert job.state == "cancelled"
    login(client, "manager", True)
    s = upload(client).json()
    with Session(seeded) as db, db.begin():
        job = db.scalar(
            select(IngestionJob).where(IngestionJob.source_version_id == s["source_version_id"])
        )
        job.state = "extracting"
        job.lease_token = uuid4()
        job.lease_until = __import__("app.security", fromlist=["now"]).now() - timedelta(seconds=1)
    process_once(settings)
    assert client.get("/api/v1/sources/" + s["id"]).json()["error_code"] == "WORKER_INTERRUPTED"


def test_forced_rls_and_immutable_snapshots(client, settings):
    login(client)
    save(client, {"program": {"value": "Synthetic Program"}})
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as db, db.begin():
            assert list(db.scalars(select(ProfileVersion))) == []
            assert list(db.scalars(select(SourceVersion))) == []
        with Session(engine) as db, db.begin():
            context(db, user_id=str(fixture_id("student-a")), mfa="false")
            assert len(list(db.scalars(select(ProfileVersion)))) == 1
            with pytest.raises(DBAPIError):
                db.execute(text("UPDATE profile_versions SET status='complete'"))
        with Session(engine) as db, db.begin():
            assert list(db.scalars(select(ProfileVersion))) == []
    finally:
        engine.dispose()


def test_configure_and_source_mutations_enforce_scope(client, seeded):
    login(client, "student-a")
    definition = synthetic_definition().model_dump(mode="json")
    assert (
        mutate(
            client,
            "POST",
            f"departments/{A}/onboarding-schemas",
            {"definition": definition},
            version=1,
        ).status_code
        == 404
    )
    login(client, "manager", True)
    r = upload(client)
    assert r.status_code == 201, r.text
    source = r.json()
    sid = source["id"]
    key = str(uuid4())
    r = mutate(
        client,
        "PATCH",
        f"sources/{sid}/metadata",
        {"title": "Synthetic corrected title"},
        version=1,
        key=key,
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    assert client.get(f"/api/v1/sources/{sid}/versions").json()["total"] == 2
    assert (
        mutate(
            client, "PATCH", f"sources/{sid}/metadata", {"title": "Stale"}, version=1
        ).status_code
        == 409
    )
    assert (
        mutate(
            client,
            "PATCH",
            f"sources/{sid}/metadata",
            {"title": "Forged", "visibility": "institution"},
            version=2,
        ).status_code
        == 422
    )
    r = mutate(client, "POST", f"sources/{sid}/archive", {}, version=2)
    assert r.status_code == 200, r.text
    assert r.json()["archived"]
    assert mutate(client, "POST", f"sources/{sid}/retry", {}, version=2).status_code == 404
    login(client, "advisor-b", True)
    for path, method, body in [
        (f"sources/{sid}/metadata", "PATCH", {"title": "Forged"}),
        (f"sources/{sid}/retry", "POST", {}),
        (f"sources/{sid}/archive", "POST", {}),
    ]:
        assert mutate(client, method, path, body, version=2).status_code == 404


def test_upload_headers_filename_size_and_anonymous(client, settings):
    assert client.get("/api/v1/" + BASE).status_code == 401
    login(client, "advisor-a", True)
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    headers = {
        "Origin": "http://localhost:3000",
        "X-CSRF-Token": csrf,
        "If-Match": '"0"',
        "Idempotency-Key": str(uuid4()),
    }
    r = client.post(
        "/api/v1/sources/uploads",
        data={"target": json.dumps(target())},
        files={"file": ("../../synthetic.txt", b"Synthetic safe text", "text/plain")},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["filename"] == "synthetic.txt"
    headers["Idempotency-Key"] = str(uuid4())
    r = client.post(
        "/api/v1/sources/uploads",
        data={"target": json.dumps(target())},
        files={"file": ("forged.pdf", b"Synthetic non-PDF", "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    settings.max_upload_bytes = 1024
    headers["Idempotency-Key"] = str(uuid4())
    r = client.post(
        "/api/v1/sources/uploads",
        data={"target": json.dumps(target())},
        files={"file": ("large.txt", b"x" * 1025, "text/plain")},
        headers=headers,
    )
    assert r.status_code == 413, r.text


def test_profile_cannot_complete_with_stale_catalog_after_adopting_schema(client):
    login(client)
    assert (
        save(
            client,
            {"program": {"value": "Synthetic Program"}, "catalog_year": {"value": "2026"}},
            status="complete",
            confirmed=True,
        ).status_code
        == 200
    )
    login(client, "manager", True)
    definition = synthetic_definition().model_dump(mode="json")
    for q in definition["fields"]:
        if q["key"] == "catalog_year":
            q["choices"] = ["2027"]
    r = mutate(
        client, "POST", f"departments/{A}/onboarding-schemas", {"definition": definition}, version=1
    )
    assert r.status_code == 201, r.text
    sid = r.json()["active_schema_id"]
    login(client)
    r = save(client, version=1, status="complete", schema=sid, confirmed=True)
    assert r.status_code == 422, r.text


def test_schema_only_delegate_has_no_profile_source_or_worker_access(client, seeded):
    from app.models import OrganizationAdminGrant

    # A metadata-only organization delegate must not gain operational records authority.
    with Session(seeded) as db, db.begin():
        db.add(
            OrganizationAdminGrant(
                user_id=fixture_id("platform-admin"),
                institution_id=INST,
                scope_kind="institution",
                status="active",
            )
        )
    login(client, "platform-admin", True)
    assert client.get("/api/v1/" + BASE).status_code == 404
    assert client.get("/api/v1/sources").json()["total"] == 0
    assert (
        mutate(
            client,
            "POST",
            f"departments/{A}/onboarding-schemas",
            {"definition": synthetic_definition().model_dump(mode="json")},
            version=1,
        ).status_code
        == 404
    )


def test_concurrent_profile_writes_append_once(client, seeded):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    login(client)
    with TestClient(client.app, base_url="http://localhost:3000") as second:
        login(second)

        def write(c):
            return save(c, {"program": {"value": "Synthetic Program"}}, version=0).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(write, [client, second]))
        assert sorted(codes) == [200, 409]
    with Session(seeded) as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(ProfileVersion).where(ProfileVersion.student_membership_id == MID)
                    )
                )
            )
            == 1
        )
        assert (
            len(
                list(
                    db.scalars(
                        select(OutboxEvent).where(
                            OutboxEvent.event_type == "profile.changed",
                            OutboxEvent.aggregate_id == MID,
                        )
                    )
                )
            )
            == 1
        )


def test_explicit_source_grants_do_not_create_student_record_access(client, seeded):
    login(client, "manager", True)
    body = {
        **target(),
        "student_membership_id": None,
        "visibility": "department",
        "text": "Synthetic department evidence",
    }
    r = mutate(client, "POST", "sources/text", body, version=0)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    with Session(seeded) as db, db.begin():
        g = db.get(RoleGrant, fixture_id("grant:platform-admin:department-a"))
        g.capabilities = ["source.read"]
    login(client, "platform-admin", True)
    assert client.get("/api/v1/sources/" + sid).status_code == 200
    assert client.get("/api/v1/" + BASE).status_code == 404
    assert mutate(client, "POST", "sources/text", body, version=0).status_code == 404


def test_schema_insert_rls_rejects_forged_institution(client, settings):
    from app.intake_models import OnboardingSchema

    login(client, "manager", True)
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as db, db.begin():
            context(db, user_id=str(fixture_id("manager")), mfa="true")
            with pytest.raises(DBAPIError):
                db.add(
                    OnboardingSchema(
                        institution_id=fixture_id("other-institution"),
                        org_unit_id=A,
                        version=900,
                        definition=synthetic_definition().model_dump(mode="json"),
                        author_id=fixture_id("manager"),
                    )
                )
                db.flush()
    finally:
        engine.dispose()


def test_sensitive_reads_audit_actual_subjects(client, seeded):
    from app.models import AuditEvent

    login(client, "manager", True)
    source = upload(client).json()
    assert client.get("/api/v1/" + BASE).status_code == 200
    assert client.get("/api/v1/sources/" + source["id"]).status_code == 200
    with Session(seeded) as db:
        rows = list(
            db.scalars(
                select(AuditEvent).where(AuditEvent.action.in_(["profile.read", "source.read"]))
            )
        )
        assert any(r.object_id == str(MID) and r.org_unit_id == A for r in rows)
        assert any(r.object_id == source["id"] and r.institution_id == INST for r in rows)


def test_parser_timeout_reports_failure_and_removes_container(settings, tmp_path, monkeypatch):
    import subprocess

    from app.ingest_worker import sandbox
    from app.private_storage import PrivateStorage

    settings.private_storage_path = tmp_path / "objects"
    key = PrivateStorage(settings.private_storage_path).write(b"Synthetic document")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, stdout="sha256:synthetic-image\n")
        if command[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(command, settings.parser_timeout_seconds)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("app.ingest_worker.subprocess.run", run)
    with pytest.raises(ProcessingError, match="PROCESSING_TIMEOUT"):
        sandbox(settings, key, "text/plain", "extract")
    assert any(command[:3] == ["docker", "rm", "-f"] for command in calls)


def test_root_operator_cannot_launch_document_sandbox(settings, monkeypatch):
    from app.ingest_worker import sandbox

    monkeypatch.setattr("app.ingest_worker.os.getuid", lambda: 0)
    with pytest.raises(ProcessingError, match="NONROOT_OPERATOR_REQUIRED"):
        sandbox(settings, "quarantine/unused", "text/plain", "extract")


def test_private_storage_rejects_frontend_paths(settings):
    from pathlib import Path

    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="Private storage must be outside"):
        Settings.model_validate(
            {
                **settings.model_dump(),
                "private_storage_path": Path(__file__).resolve().parents[2]
                / "frontend/public/uploads",
            }
        )
