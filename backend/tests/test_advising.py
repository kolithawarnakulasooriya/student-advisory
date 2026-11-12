"""Real PostgreSQL publication, retrieval, chat/guidance and case boundaries."""

import json
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.advising_models import (
    AdvisingJob,
)
from app.advising_worker import process_once
from app.intake_models import ExtractionArtifact
from app.private_storage import PrivateStorage
from tests.conftest import login
from tests.test_intake import MID, save, target
from tests.test_staff import mutate


@pytest.fixture(autouse=True)
def rag_config(settings, tmp_path):
    settings.inference_provider = "mock"
    settings.rag_database_url = SecretStr(
        "postgresql+psycopg://advisory_rag:local-rag-only@127.0.0.1:5432/advisory_test"
    )
    settings.private_storage_path = tmp_path / "objects"


def complete_profile(client):
    login(client)
    r = save(
        client,
        {"program": {"value": "Synthetic Program"}, "catalog_year": {"value": "2026"}},
        status="complete",
        confirmed=True,
    )
    assert r.status_code == 200, r.text


def prepared_source(
    client,
    seeded,
    settings,
    *,
    content="Synthetic catalog 2026: SYN102 is required.",
    visibility="department",
    metadata=None,
    target_override=None,
    uploader="manager",
    source_revision=0,
):
    login(client, uploader, True)
    body = {
        **target(),
        "visibility": visibility,
        "text": content,
        "student_membership_id": str(MID) if visibility == "student" else None,
        "metadata": {
            "title": "Synthetic catalog fixture",
            "document_class": "catalog",
            "catalog_start": 2026,
            "catalog_end": 2026,
            "program": "Synthetic Program",
            **(metadata or {}),
        },
    }
    body.update(target_override or {})
    r = mutate(client, "POST", "sources/text", body, version=source_revision)
    assert r.status_code == 201, r.text
    source = r.json()
    # Synthetic extraction fixture, never a claim that a scanner ran in this test.
    key = PrivateStorage(settings.private_storage_path).write(
        json.dumps(
            {
                "segments": [{"page": 1, "text": content}],
                "ocr": False,
                "extractor_version": "synthetic-fixture",
            }
        ).encode(),
        "artifacts",
    )
    with Session(seeded) as db, db.begin():
        from app.intake_models import IngestionJob

        j = db.scalar(
            select(IngestionJob).where(
                IngestionJob.source_version_id == UUID(source["source_version_id"])
            )
        )
        j.state = "needs_review"
        db.add(
            ExtractionArtifact(
                source_version_id=UUID(source["source_version_id"]),
                job_id=j.id,
                object_key=key,
                extractor_version="synthetic-fixture",
                ocr=False,
            )
        )
    return source


def publish_source(client, seeded, settings, **kwargs):
    source = prepared_source(client, seeded, settings, **kwargs)
    r = mutate(
        client,
        "POST",
        f"sources/{source['id']}/index",
        {
            "source_version_id": source["source_version_id"],
            "reason": "Explicit review of synthetic fixture metadata",
        },
        version=source["version"],
    )
    assert r.status_code == 201, r.text
    build = r.json()
    assert process_once(settings) == 1
    r = client.get(f"/api/v1/sources/{source['id']}/publication")
    assert r.status_code == 200, r.text
    assert r.json()["builds"][0]["state"] == "ready", r.text
    r = mutate(
        client,
        "POST",
        f"sources/{source['id']}/publish",
        {"build_id": build["id"], "reason": "Publish synthetic test evidence only"},
        version=0,
    )
    assert r.status_code == 200, r.text
    return source, build


def conversation(client):
    login(client)
    r = mutate(
        client,
        "POST",
        "conversations",
        {"student_membership_id": str(MID), "title": "Synthetic advising"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def ask(client, c, question="Which course is required in my synthetic catalog?", key=None):
    current = client.get("/api/v1/conversations/" + c["id"])
    assert current.status_code == 200, current.text
    return mutate(
        client,
        "POST",
        f"conversations/{c['id']}/messages",
        {"text": question},
        version=current.json()["version"],
        key=key,
    )


def messages(client, c):
    r = client.get(f"/api/v1/conversations/{c['id']}/messages")
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_published_answer_and_citation(client, seeded, settings):
    complete_profile(client)
    source, build = publish_source(client, seeded, settings)
    c = conversation(client)
    r = ask(client, c)
    assert r.status_code == 201, r.text
    assert r.json()["answers"] == [] and r.json()["jobs"][0]["state"] == "queued"
    assert process_once(settings) == 1
    m = messages(client, c)[0]
    assert m["jobs"][0]["state"] == "completed", m
    assert m["answers"][0]["disposition"] == "answered"
    cite = m["answers"][0]["payload"]["citations"][0]
    assert cite["source_id"] == source["id"] and "SYN102" in cite["quote"]
    response = client.get("/api/v1/citations/" + cite["id"])
    assert response.status_code == 200, response.text
    assert response.json()["text"] == cite["quote"]


def test_draft_intake_versions_never_visible_to_students(client, seeded, settings):
    complete_profile(client)
    source, build = publish_source(client, seeded, settings)
    r = mutate(
        client,
        "POST",
        "sources/text",
        {
            **target(),
            "visibility": "department",
            "student_membership_id": None,
            "source_id": source["id"],
            "metadata": {"title": "PRIVATE_UNPUBLISHED_FILENAME"},
            "text": "Private draft replacement",
        },
        version=1,
    )
    assert r.status_code == 201, r.text
    login(client)
    for path in [f"sources/{source['id']}", f"sources/{source['id']}/versions", "sources"]:
        response = client.get("/api/v1/" + path)
        assert response.status_code == 200, response.text
        assert "PRIVATE_UNPUBLISHED_FILENAME" not in response.text
    assert client.get(f"/api/v1/sources/{source['id']}").json()["version"] == 1
    assert client.get(f"/api/v1/sources/{source['id']}/versions").json()["total"] == 1


def test_guidance_notes_drafts_and_follow_up(client, seeded, settings):
    complete_profile(client)
    publish_source(client, seeded, settings)
    c = conversation(client)
    ask(client, c)
    process_once(settings)
    login(client, "advisor-a", True)
    current = client.get("/api/v1/conversations/" + c["id"]).json()
    r = mutate(
        client,
        "POST",
        f"conversations/{c['id']}/guidance",
        {"text": "Keep the term to three courses.", "preferences": {"max_courses": 3}},
        version=current["version"],
    )
    assert r.status_code == 201, r.text
    r = mutate(client, "POST", f"conversations/{c['id']}/notes", {"text": "PRIVATE_NOTE_41"})
    assert r.status_code == 201, r.text
    with Session(seeded) as db:
        assert len(list(db.scalars(select(AdvisingJob)))) == 2  # index + the one student question
    login(client)
    assert client.get(f"/api/v1/conversations/{c['id']}/notes").status_code == 404
    assert client.get(f"/api/v1/conversations/{c['id']}/advisor-drafts").status_code == 404
    ask(client, c, "Which requirement applies to my next term?")
    process_once(settings)
    data = messages(client, c)
    assert "PRIVATE_NOTE_41" not in json.dumps(data)
    latest = max(data, key=lambda m: m["created_at"])
    assert latest["answers"][0]["payload"]["guidance"][0]["preferences"]["max_courses"] == 3
    login(client, "advisor-a", True)
    current = client.get("/api/v1/conversations/" + c["id"]).json()
    r = mutate(
        client,
        "POST",
        f"conversations/{c['id']}/advisor-drafts",
        {"message_id": latest["id"]},
        version=current["version"],
    )
    assert r.status_code == 201, r.text
    process_once(settings)
    drafts = client.get(f"/api/v1/conversations/{c['id']}/advisor-drafts")
    assert drafts.status_code == 200, drafts.text
    assert drafts.json()["total"] == 1
    assert "PRIVATE_NOTE_41" not in drafts.text


@pytest.mark.parametrize(
    "account,mfa",
    [("student-b", False), ("advisor-b", True), ("secretary", True), ("platform-admin", True)],
)
def test_chat_case_wrong_scope_denials(client, account, mfa):
    complete_profile(client)
    c = conversation(client)
    r = mutate(
        client,
        "POST",
        "cases",
        {"student_membership_id": str(MID), "conversation_id": c["id"], "reason": "Synthetic help"},
    )
    assert r.status_code == 201, r.text
    case = r.json()
    login(client, account, mfa)
    for path in [
        f"conversations/{c['id']}",
        f"conversations/{c['id']}/messages",
        f"conversations/{c['id']}/guidance",
        f"cases/{case['id']}",
    ]:
        assert client.get("/api/v1/" + path).status_code == 404


def test_missing_facts_case_idempotency(client, settings):
    c = conversation(client)
    key = str(uuid4())
    r = ask(client, c, key=key)
    assert r.status_code == 201, r.text
    assert ask(client, c, key=key).json()["id"] == r.json()["id"]
    process_once(settings)
    answer = messages(client, c)[0]["answers"][0]
    assert answer["disposition"] == "needs_clarification"
    key = str(uuid4())
    body = {
        "student_membership_id": str(MID),
        "conversation_id": c["id"],
        "reason": "Please clarify my synthetic catalog",
    }
    r = mutate(client, "POST", "cases", body, key=key)
    assert r.status_code == 201, r.text
    assert mutate(client, "POST", "cases", body, key=key).json()["id"] == r.json()["id"]


def test_withdrawal_redacts_history_and_prevents_inflight_commit(
    client, seeded, settings, monkeypatch
):
    from app.inference import ModelAdapter

    complete_profile(client)
    source, _ = publish_source(client, seeded, settings)
    c = conversation(client)
    ask(client, c)
    process_once(settings)
    cite = messages(client, c)[0]["answers"][0]["payload"]["citations"][0]
    ask(client, c, "Which course should I consider?")
    original = ModelAdapter.select

    def withdrawing(self, *args, **kwargs):
        login(client, "manager", True)
        r = mutate(
            client,
            "POST",
            f"sources/{source['id']}/withdraw",
            {"reason": "Withdraw during synthetic generation"},
            version=1,
        )
        assert r.status_code == 200, r.text
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ModelAdapter, "select", withdrawing)
    process_once(settings)
    login(client)
    data = messages(client, c)
    newest = max(data, key=lambda m: m["created_at"])
    assert newest["answers"] == []
    assert newest["jobs"][0]["state"] == "cancelled"
    older = min(data, key=lambda m: m["created_at"])
    assert older["answers"][0]["payload"]["citations"][0]["quote"] is None
    response = client.get("/api/v1/citations/" + cite["id"])
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "withdrawn" and response.json()["text"] is None


def test_invalid_selection_repair_and_retry_reuses_message(client, seeded, settings, monkeypatch):
    from app.inference import ModelAdapter

    complete_profile(client)
    publish_source(client, seeded, settings)
    c = conversation(client)
    ask(client, c)
    calls = []
    original = ModelAdapter.select

    def forged(self, *args, **kwargs):
        calls.append(kwargs.get("repair", False))
        return {
            "disposition": "answered",
            "evidence_ids": ["OTHER_STUDENT"],
            "reason_code": "evidence",
        }

    monkeypatch.setattr(ModelAdapter, "select", forged)
    process_once(settings)
    data = messages(client, c)
    assert calls == [False, True]
    assert data[0]["answers"][0]["disposition"] == "needs_advisor"
    j = data[0]["jobs"][0]
    r = mutate(client, "POST", f"jobs/{j['id']}/retry", {}, version=j["version"])
    assert r.status_code == 201, r.text
    monkeypatch.setattr(ModelAdapter, "select", original)
    process_once(settings)
    data = messages(client, c)
    assert len(data) == 1 and len(data[0]["jobs"]) == 2
    assert data[0]["answers"][-1]["disposition"] == "answered"


def test_model_failure_never_silently_substitutes(client, seeded, settings, monkeypatch):
    from app.inference import InferenceError, ModelAdapter

    complete_profile(client)
    publish_source(client, seeded, settings)
    c = conversation(client)
    ask(client, c)

    def offline(*args, **kwargs):
        raise InferenceError("INFERENCE_UNAVAILABLE")

    monkeypatch.setattr(ModelAdapter, "select", offline)
    process_once(settings)
    data = messages(client, c)[0]
    assert data["answers"] == [] and data["jobs"][0]["state"] == "failed"
    assert data["jobs"][0]["error_code"] == "INFERENCE_UNAVAILABLE"


def test_governance_evaluation_activation_and_stale_rollback(client, seeded, settings):
    complete_profile(client)
    source, _ = publish_source(client, seeded, settings)
    excerpts = client.get(f"/api/v1/sources/{source['id']}/indexed-excerpts")
    assert excerpts.status_code == 200, excerpts.text
    evidence = excerpts.json()["items"][0]["id"]
    body = {
        "institution_id": source["institution_id"],
        "org_unit_id": source["org_unit_id"],
        "kind": "rules",
        "definition": {
            "rules": [
                {
                    "course_id": "SYN102",
                    "kind": "prerequisite",
                    "requires": ["SYN101"],
                    "evidence_id": evidence,
                }
            ]
        },
    }
    state = client.get(
        "/api/v1/knowledge/state", params={"institution_id": source["institution_id"]}
    ).json()
    r = mutate(client, "POST", "knowledge/governance", body, version=state["version"])
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    r = mutate(client, "POST", f"knowledge/governance/{gid}/evaluate", {}, version=0)
    assert r.status_code == 201, r.text
    process_once(settings)
    params = {"institution_id": source["institution_id"], "scope_id": source["org_unit_id"]}
    r = client.get("/api/v1/knowledge/governance", params=params)
    assert r.status_code == 200, r.text
    g = r.json()["items"][0]
    assert g["evaluation_passed"], g
    activation = {"evaluation_id": g["evaluation_id"], "reason": "Synthetic rule review"}
    r = mutate(
        client, "POST", f"knowledge/governance/{gid}/activate", activation, version=state["version"]
    )
    assert r.status_code == 200, r.text
    assert r.json()["active"]
    state = client.get(
        "/api/v1/knowledge/state", params={"institution_id": source["institution_id"]}
    ).json()
    r = mutate(
        client, "POST", f"knowledge/governance/{gid}/activate", activation, version=state["version"]
    )
    assert r.status_code == 409 and r.json()["code"] == "EVALUATION_REQUIRED"

    # Activate a distinct immutable revision, then roll back only after fresh evaluation.
    newer = mutate(
        client,
        "POST",
        "knowledge/governance",
        body | {"definition": {"rules": []}},
        version=state["version"],
    )
    assert newer.status_code == 201, newer.text
    gid2 = newer.json()["id"]
    for target_gid in (gid2, gid):
        evaluation = mutate(
            client, "POST", f"knowledge/governance/{target_gid}/evaluate", {}, version=0
        )
        assert evaluation.status_code == 201, evaluation.text
        process_once(settings)
        versions = client.get("/api/v1/knowledge/governance", params=params).json()["items"]
        selected = next(g for g in versions if g["id"] == target_gid)
        head = client.get(
            "/api/v1/knowledge/state", params={"institution_id": source["institution_id"]}
        ).json()
        activated = mutate(
            client,
            "POST",
            f"knowledge/governance/{target_gid}/activate",
            {
                "evaluation_id": selected["evaluation_id"],
                "reason": "Synthetic tested release or rollback",
            },
            version=head["version"],
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["active"]
    versions = client.get("/api/v1/knowledge/governance", params=params).json()["items"]
    assert [v["id"] for v in versions if v["active"]] == [gid]


def test_private_notes_never_enter_model_and_draft_publish(client, seeded, settings, monkeypatch):
    from app.inference import ModelAdapter

    complete_profile(client)
    publish_source(client, seeded, settings)
    c = conversation(client)
    ask(client, c)
    process_once(settings)
    login(client, "advisor-a", True)
    mutate(client, "POST", f"conversations/{c['id']}/notes", {"text": "PRIVATE_NEVER_IN_MODEL_912"})
    current = client.get("/api/v1/conversations/" + c["id"]).json()
    mid = messages(client, c)[0]["id"]
    r = mutate(
        client,
        "POST",
        f"conversations/{c['id']}/advisor-drafts",
        {"message_id": mid},
        version=current["version"],
    )
    assert r.status_code == 201, r.text
    original = ModelAdapter.select
    seen = []

    def inspect(self, *args, **kwargs):
        seen.append(json.dumps([args, kwargs]))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ModelAdapter, "select", inspect)
    process_once(settings)
    assert seen and "PRIVATE_NEVER_IN_MODEL" not in "".join(seen)
    draft = client.get(f"/api/v1/conversations/{c['id']}/advisor-drafts").json()["items"][0]
    r = mutate(
        client,
        "POST",
        f"advisor-drafts/{draft['id']}/publish",
        {"text": "I reviewed this synthetic evidence.", "reviewed": True},
        version=current["version"],
    )
    assert r.status_code == 201, r.text
    login(client)
    assert client.get(f"/api/v1/conversations/{c['id']}/advisor-drafts").status_code == 404
    guidance = client.get(f"/api/v1/conversations/{c['id']}/guidance").json()["items"]
    assert guidance[0]["text"] == "I reviewed this synthetic evidence."


@pytest.mark.parametrize(
    "account",
    ["pending", "suspended", "unassigned-advisor", "platform-admin", "secretary", "student-b"],
)
def test_every_chat_projection_denies_unrelated_actors(client, settings, account):
    c = conversation(client)
    ask(client, c)
    process_once(settings)
    job = messages(client, c)[0]["jobs"][0]["id"]
    if account == "suspended":
        from tests.conftest import post

        assert post(client, "auth/sign-in", {"email": "suspended@advisory.test"}).status_code == 401
        return
    login(client, account, account not in {"pending", "student-b"})
    paths = [
        f"conversations/{c['id']}",
        f"conversations/{c['id']}/messages",
        f"conversations/{c['id']}/guidance",
        f"conversations/{c['id']}/notes",
        f"conversations/{c['id']}/advisor-drafts",
        f"jobs/{job}",
    ]
    for path in paths:
        r = client.get("/api/v1/" + path)
        assert r.status_code in {401, 403, 404}, (path, r.text)


def test_pooled_rls_and_worker_cannot_read_notes(client, settings, seeded):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from app.advising_models import Conversation, StaffNote
    from app.db import context, make_engine
    from app.seed import fixture_id

    c = conversation(client)
    login(client, "advisor-a", True)
    mutate(client, "POST", f"conversations/{c['id']}/notes", {"text": "PRIVATE_SQL_NOTE"})
    login(client)
    from app.security import COOKIE, digest

    session_hash = digest(client.cookies.get(COOKIE))
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        with Session(engine) as db, db.begin():
            assert list(db.scalars(select(Conversation))) == []
        with Session(engine) as db, db.begin():
            context(
                db, user_id=str(fixture_id("student-a")), mfa="false", session_hash=session_hash
            )
            assert len(list(db.scalars(select(Conversation)))) == 1
            assert list(db.scalars(select(StaffNote))) == []
        with Session(engine) as db, db.begin():
            assert list(db.scalars(select(Conversation))) == []
        with Session(seeded) as db:
            flags = db.execute(
                text(
                    "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class "
                    "WHERE relname IN ('evidence_chunks','conversations','staff_notes',"
                    "'advising_jobs','validated_answers','governance_versions','advising_cases')"
                )
            ).all()
            assert len(flags) == 7 and all(r[1] and r[2] for r in flags)
    finally:
        engine.dispose()
    worker = make_engine(settings.rag_database_url.get_secret_value())
    try:
        with Session(worker) as db, db.begin(), pytest.raises(DBAPIError):
            db.execute(select(StaffNote))
    finally:
        worker.dispose()


def test_profile_change_during_inference_cancels_commit(client, seeded, settings, monkeypatch):
    from app.inference import ModelAdapter

    complete_profile(client)
    publish_source(client, seeded, settings)
    c = conversation(client)
    ask(client, c)
    original = ModelAdapter.select

    def change(self, *args, **kwargs):
        login(client)
        r = save(
            client,
            {"program": {"value": "Synthetic Program"}, "catalog_year": {"value": "2026"}},
            status="complete",
            confirmed=True,
            version=client.get(f"/api/v1/students/{MID}/profile").json()["version"],
        )
        assert r.status_code == 200, r.text
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ModelAdapter, "select", change)
    process_once(settings)
    m = messages(client, c)[0]
    assert m["answers"] == [] and m["jobs"][0]["state"] == "cancelled"


def test_filters_before_reranking_and_chat(client, seeded, settings, monkeypatch):
    from app.inference import ModelAdapter

    complete_profile(client)
    source, _ = publish_source(client, seeded, settings)
    publish_source(
        client,
        seeded,
        settings,
        content="FORBIDDEN_OLD_CATALOG SYN102 is required.",
        metadata={"catalog_start": 2024, "catalog_end": 2024},
    )
    publish_source(
        client,
        seeded,
        settings,
        content="FORBIDDEN_OTHER_PROGRAM SYN102 is required.",
        metadata={"program": "Synthetic Alternate Program"},
    )
    from app.seed import fixture_id

    publish_source(
        client,
        seeded,
        settings,
        content="FORBIDDEN_PRIVATE_STUDENT SYN102 is required.",
        uploader="multi-role",
        target_override={
            "visibility": "student",
            "org_unit_id": str(fixture_id("department-b")),
            "student_membership_id": str(fixture_id("grant:student-b:department-b")),
        },
        metadata={"program": None, "catalog_start": None, "catalog_end": None},
    )
    c = conversation(client)
    seen = []
    original_rank = ModelAdapter.rerank
    original_select = ModelAdapter.select

    def rank(self, *args, **kwargs):
        seen.append(json.dumps([args, kwargs]))
        return original_rank(self, *args, **kwargs)

    def select_evidence(self, *args, **kwargs):
        seen.append(json.dumps([args, kwargs]))
        return original_select(self, *args, **kwargs)

    monkeypatch.setattr(ModelAdapter, "rerank", rank)
    monkeypatch.setattr(ModelAdapter, "select", select_evidence)
    ask(client, c)
    process_once(settings)
    assert seen and "FORBIDDEN" not in "".join(seen)
    m = messages(client, c)[0]
    assert m["answers"][0]["payload"]["citations"][0]["source_id"] == source["id"]
    p = client.get(f"/api/v1/students/{MID}/published-sources")
    assert p.status_code == 200, p.text
    assert len(p.json()["items"]) == 1


def test_reassignment_during_generation_and_former_advisor_denial(
    client, seeded, settings, monkeypatch
):
    from app.inference import ModelAdapter
    from app.seed import fixture_id

    complete_profile(client)
    publish_source(client, seeded, settings)
    c = conversation(client)
    ask(client, c)
    original = ModelAdapter.select

    def reassign(self, *args, **kwargs):
        login(client, "manager", True)
        state = client.get(f"/api/v1/assignment-state/{MID}").json()
        r = mutate(
            client,
            "PUT",
            f"students/{MID}/advisor",
            {
                "advisor_grant_id": str(fixture_id("grant:advisor-a2:department-a")),
                "reason": "Synthetic reassignment during generation",
            },
            version=state["version"],
        )
        assert r.status_code == 200, r.text
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ModelAdapter, "select", reassign)
    process_once(settings)
    login(client)
    assert messages(client, c)[0]["answers"] == []
    login(client, "advisor-a", True)
    for suffix in ["", "/messages", "/guidance", "/notes", "/advisor-drafts"]:
        assert client.get("/api/v1/conversations/" + c["id"] + suffix).status_code == 404
    login(client, "advisor-a2", True)
    assert client.get("/api/v1/conversations/" + c["id"]).status_code == 200


def test_case_lifecycle_and_fallback_with_no_eligible_advisor(client, seeded):
    from app.models import RoleGrant
    from app.seed import fixture_id

    c = conversation(client)
    with Session(seeded) as db, db.begin():
        db.get(RoleGrant, fixture_id("grant:advisor-a:department-a")).status = "suspended"
    r = mutate(
        client,
        "POST",
        "cases",
        {
            "student_membership_id": str(MID),
            "conversation_id": c["id"],
            "reason": "Synthetic manager fallback",
        },
    )
    assert r.status_code == 201, r.text
    case = r.json()
    assert case["route"] == "manager_queue" and case["assigned_advisor_id"] is None
    login(client, "manager", True)
    for state in ["in_progress", "resolved", "open"]:
        r = mutate(
            client,
            "PATCH",
            f"cases/{case['id']}",
            {"status": state, "text": "Synthetic human transition"},
            version=case["version"],
        )
        assert r.status_code == 200, r.text
        case = r.json()
    history = client.get(f"/api/v1/cases/{case['id']}/history").json()
    assert history["total"] == 4


def test_revision_headers_and_concurrent_stale_questions(client):
    c = conversation(client)
    r = client.get("/api/v1/conversations/" + c["id"])
    assert r.headers["etag"] == f'"{c["version"]}"'
    first = mutate(
        client,
        "POST",
        f"conversations/{c['id']}/messages",
        {"text": "Synthetic first question"},
        version=c["version"],
    )
    assert first.status_code == 201, first.text
    stale = mutate(
        client,
        "POST",
        f"conversations/{c['id']}/messages",
        {"text": "Stale synthetic question"},
        version=c["version"],
    )
    assert stale.status_code == 409
    assert len(messages(client, c)) == 1


def test_failed_replacement_retains_publication_and_retry_is_atomic(
    client, seeded, settings, monkeypatch
):
    from app.advising_models import EvidenceChunk
    from app.inference import InferenceError, ModelAdapter

    complete_profile(client)
    source, old_build = publish_source(client, seeded, settings)
    replacement = prepared_source(
        client,
        seeded,
        settings,
        content=" ".join(f"Synthetic paragraph {i} SYN102 is required." for i in range(300)),
        target_override={"source_id": source["id"]},
        source_revision=source["version"],
    )
    original = ModelAdapter.embed
    calls = []

    def fail_second(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise InferenceError("INFERENCE_UNAVAILABLE")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ModelAdapter, "embed", fail_second)
    body = {
        "source_version_id": replacement["source_version_id"],
        "reason": "Review synthetic replacement",
    }
    r = mutate(
        client, "POST", f"sources/{source['id']}/index", body, version=replacement["version"]
    )
    assert r.status_code == 201, r.text
    process_once(settings)
    p = client.get(f"/api/v1/sources/{source['id']}/publication").json()
    assert p["build_id"] == old_build["id"] and p["status"] == "published"
    with Session(seeded) as db:
        assert (
            list(
                db.scalars(
                    select(EvidenceChunk).where(
                        EvidenceChunk.source_version_id == UUID(replacement["source_version_id"])
                    )
                )
            )
            == []
        )
    monkeypatch.setattr(ModelAdapter, "embed", original)
    r = mutate(
        client, "POST", f"sources/{source['id']}/index", body, version=replacement["version"]
    )
    assert r.status_code == 201, r.text
    assert r.json()["id"] != old_build["id"]
    process_once(settings)
    p = client.get(f"/api/v1/sources/{source['id']}/publication").json()
    assert p["build_id"] == old_build["id"]
    new_build = next(
        b for b in p["builds"] if b["source_version_id"] == replacement["source_version_id"]
    )
    assert new_build["state"] == "ready"
    r = mutate(
        client,
        "POST",
        f"sources/{source['id']}/publish",
        {"build_id": new_build["id"], "reason": "Explicit reviewed replacement"},
        version=p["version"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["build_id"] == new_build["id"]
    from app.models import OutboxEvent

    with Session(seeded) as db:
        versions = list(
            db.scalars(
                select(OutboxEvent.aggregate_version).where(
                    OutboxEvent.event_type == "source.indexed",
                    OutboxEvent.aggregate_id == UUID(source["id"]),
                )
            )
        )
        assert sorted(versions) == [1, 2]


def test_reset_clears_model_configuration_fixture(client, seeded, settings):
    import os
    import subprocess
    import sys

    from app.advising_models import EmbeddingConfig
    from tests.conftest import MIGRATION

    with Session(seeded) as db, db.begin():
        db.add(
            EmbeddingConfig(fingerprint=str(uuid4()), definition={"synthetic": True}, dimension=768)
        )
    subprocess.run(
        [sys.executable, "-m", "app.seed", "reset", "--confirm-database", "advisory_test"],
        env={**os.environ, "MIGRATION_DATABASE_URL": MIGRATION, "APP_ENV": "test"},
        check=True,
        capture_output=True,
        text=True,
    )
    with Session(seeded) as db:
        assert list(db.scalars(select(EmbeddingConfig))) == []


def test_prompt_controls_need_superadmin_and_complete_rebuild(client, seeded, settings):
    from tests.test_staff import promote

    complete_profile(client)
    source, build = publish_source(client, seeded, settings)
    body = {
        "institution_id": source["institution_id"],
        "kind": "prompt",
        "definition": {"style": "concise"},
    }
    for who in ["manager", "platform-admin"]:
        login(client, who, True)
        r = mutate(client, "POST", "knowledge/governance", body, version=1)
        assert r.status_code == 404, r.text
    promote(seeded)
    login(client, "super-admin", True)
    me = client.get("/api/v1/me").json()
    assert "prompt.manage" in me["capabilities"]
    query = {"institution_id": source["institution_id"], "purpose": "administration"}
    state = client.get("/api/v1/knowledge/state", params=query).json()
    r = mutate(client, "POST", "knowledge/governance", body, version=state["version"])
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    r = mutate(client, "POST", f"knowledge/governance/{gid}/evaluate", {}, version=0)
    assert r.status_code == 201, r.text
    process_once(settings)
    versions = client.get("/api/v1/knowledge/governance", params=query)
    assert versions.status_code == 200, versions.text
    release = versions.json()["items"][0]
    assert release["evaluation_passed"], release
    r = mutate(
        client,
        "POST",
        f"knowledge/governance/{gid}/activate",
        {"evaluation_id": release["evaluation_id"], "reason": "Synthetic global style review"},
        version=state["version"],
    )
    assert r.status_code == 200, r.text
    state = client.get("/api/v1/knowledge/state", params=query).json()
    r = mutate(
        client,
        "POST",
        "knowledge/rebuild/activate",
        {
            "institution_id": source["institution_id"],
            "build_ids": [],
            "reason": "Synthetic incomplete rebuild",
        },
        version=state["version"],
    )
    assert r.status_code == 409, r.text
    publication = client.get(
        f"/api/v1/sources/{source['id']}/publication", params={"purpose": "administration"}
    ).json()
    assert publication["build_id"] == build["id"] and publication["version"] == 1
    r = mutate(
        client,
        "POST",
        "knowledge/rebuild/activate",
        {
            "institution_id": source["institution_id"],
            "build_ids": [build["id"]],
            "reason": "Synthetic complete compatible rebuild",
        },
        version=state["version"],
    )
    assert r.status_code == 200, r.text


def test_expired_generation_lease_recovers_without_duplicate_artifacts(client, seeded, settings):
    from datetime import timedelta

    from app.security import now

    c = conversation(client)
    ask(client, c)
    with Session(seeded) as db, db.begin():
        job = db.scalar(select(AdvisingJob).where(AdvisingJob.kind == "answer"))
        job.state = "running"
        job.version += 1
        job.lease_token = uuid4()
        job.lease_until = now() - timedelta(seconds=1)
    process_once(settings)
    m = messages(client, c)[0]
    j = m["jobs"][0]
    assert j["state"] == "failed" and j["error_code"] == "WORKER_INTERRUPTED" and m["answers"] == []
    r = mutate(client, "POST", f"jobs/{j['id']}/retry", {}, version=j["version"])
    assert r.status_code == 201, r.text
    process_once(settings)
    process_once(settings)
    m = messages(client, c)[0]
    assert len(m["answers"]) == 1 and len(m["jobs"]) == 2


def test_skip_guidance_requires_human_review_and_supersession_is_revision_checked(
    client, seeded, settings
):
    complete_profile(client)
    publish_source(client, seeded, settings)
    c = conversation(client)
    login(client, "advisor-a", True)
    version = client.get("/api/v1/conversations/" + c["id"]).json()["version"]
    body = {"text": "Skip SYN101 before SYN102."}
    r = mutate(client, "POST", f"conversations/{c['id']}/guidance", body, version=version)
    assert r.status_code == 201, r.text
    original = r.json()["id"]
    login(client)
    ask(client, c)
    process_once(settings)
    answer = messages(client, c)[0]["answers"][0]
    assert answer["disposition"] == "needs_advisor"
    assert answer["payload"]["reason_code"] == "POLICY_EXCEPTION_REQUIRES_REVIEW"
    login(client, "advisor-a", True)
    for expected in [201, 409]:
        version = client.get("/api/v1/conversations/" + c["id"]).json()["version"]
        r = mutate(
            client,
            "POST",
            f"conversations/{c['id']}/guidance",
            {"text": "Review the official prerequisite.", "supersedes_id": original},
            version=version,
        )
        assert r.status_code == expected, r.text
