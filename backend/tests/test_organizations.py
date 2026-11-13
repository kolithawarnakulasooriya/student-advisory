from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import context, make_engine
from app.models import (
    AuditEvent,
    Institution,
    Invitation,
    OrganizationAdminGrant,
    OrgUnit,
    OutboxEvent,
    RoleGrant,
    User,
)
from app.security import now
from app.seed import fixture_id
from tests.conftest import login
from tests.test_staff import create_user, mutate, promote

INST = fixture_id("synthetic")
COLLEGE = fixture_id("college")
A = fixture_id("department-a")
OTHER = fixture_id("other-institution")


def admin(client, seeded):
    promote(seeded)
    login(client, "super-admin", True)


def create_org(client, kind="college", parent=None, code=None, institution=INST):
    code = code or "synthetic-" + uuid4().hex[:10]
    r = mutate(
        client,
        "POST",
        "admin/org-units",
        {
            "institution_id": str(institution),
            "kind": kind,
            "parent_id": str(parent) if parent else None,
            "code": code,
            "name": "Synthetic " + code,
            "timezone": "America/Chicago",
            "reason": "Synthetic organization setup",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def delegate(client, uid, root=None, institution=INST):
    r = mutate(
        client,
        "POST",
        "organization-admin-grants",
        {
            "user_id": str(uid),
            "institution_id": str(institution),
            "scope_kind": "college" if root else "institution",
            "root_org_unit_id": str(root) if root else None,
            "reason": "Synthetic delegation",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_edit_enrollment_and_no_implicit_scope(client, seeded):
    admin(client, seeded)
    college = create_org(client)
    dept = create_org(client, "department", college["id"])
    assert dept["status"] == "active" and dept["enrollment_enabled"] is False
    assert dept["id"] not in {
        r["id"] for r in client.get("/api/v1/membership-options").json()["items"]
    }
    opened = mutate(
        client,
        "PUT",
        f"admin/org-units/{dept['id']}/enrollment",
        {"enabled": True, "reason": "Open synthetic requests"},
        dept["version"],
    )
    assert opened.status_code == 200, opened.text
    version = opened.json()["version"]
    edit = mutate(
        client,
        "PATCH",
        f"admin/org-units/{dept['id']}",
        {
            "name": "Renamed synthetic department",
            "code": dept["code"],
            "timezone": "UTC",
            "reason": "Rename",
        },
        version,
    )
    assert edit.status_code == 200, edit.text
    options = client.get("/api/v1/membership-options").json()["items"]
    assert (
        next(o for o in options if o["id"] == dept["id"])["name"] == "Renamed synthetic department"
    )
    stale = mutate(
        client,
        "PUT",
        f"admin/org-units/{dept['id']}/enrollment",
        {"enabled": False, "reason": "Stale toggle"},
        version,
    )
    assert stale.status_code == 409
    login(client, "manager", True)
    assert dept["id"] not in {o["id"] for o in client.get("/api/v1/org-units").json()}
    assert client.get(f"/api/v1/memberships?scope_id={dept['id']}").status_code == 403
    with Session(seeded) as db:
        assert not list(db.scalars(select(RoleGrant).where(RoleGrant.org_unit_id == dept["id"])))


@pytest.mark.parametrize(
    "account,mfa",
    [
        ("student-a", False),
        ("manager", True),
        ("secretary", True),
        ("platform-admin", True),
        ("super-admin", True),
        ("pending", False),
        ("unverified", False),
        ("other-institution", True),
    ],
)
def test_labels_and_other_roles_cannot_manage_organizations(client, account, mfa):
    login(client, account, mfa)
    assert client.get(f"/api/v1/admin/org-units?institution_id={INST}").status_code in {403, 404}
    assert client.get(f"/api/v1/admin/org-units/{A}").status_code in {403, 404}
    r = mutate(
        client,
        "POST",
        "admin/org-units",
        {
            "institution_id": str(INST),
            "kind": "college",
            "name": "Forbidden",
            "code": "forbidden",
            "timezone": "UTC",
            "reason": "Denied",
        },
    )
    assert r.status_code in {403, 404}, r.text


def test_delegation_without_department_membership_and_exact_boundary(client, seeded):
    uid = create_user(seeded, "org-only@advisory.test")
    admin(client, seeded)
    college = create_org(client)
    sibling = create_org(client)
    grant = delegate(client, uid, college["id"])
    login(client, "org-only")
    assert client.get("/api/v1/me").json()["mfa_required"] is True
    assert client.get(f"/api/v1/admin/org-units?institution_id={INST}").status_code == 403
    from tests.conftest import post

    assert post(client, "auth/simulator/step-up").status_code == 200
    me = client.get("/api/v1/me").json()
    assert me["administration_capabilities"] == ["organization.manage"] and me["scopes"] == []
    assert me["active_grants"] == []
    rows = client.get(f"/api/v1/admin/org-units?institution_id={INST}").json()
    assert rows["total"] == 1 and rows["items"][0]["id"] == college["id"]
    child = create_org(client, "department", college["id"])
    assert client.get(f"/api/v1/admin/org-units/{child['id']}").status_code == 200
    assert client.get(f"/api/v1/admin/org-units/{sibling['id']}").status_code == 404
    assert client.get(f"/api/v1/admin/org-units?institution_id={OTHER}").status_code == 404
    assert (
        mutate(
            client,
            "POST",
            "organization-admin-grants",
            {
                "user_id": str(uid),
                "institution_id": str(INST),
                "scope_kind": "institution",
                "reason": "Escalate",
            },
        ).status_code
        == 403
    )
    assert (
        mutate(
            client,
            "POST",
            "role-grants",
            {
                "user_id": str(fixture_id("student-b")),
                "org_unit_id": child["id"],
                "role": "manager",
                "reason": "Escalate",
            },
        ).status_code
        == 403
    )
    assert (
        client.get(f"/api/v1/students/{fixture_id('grant:student-a:department-a')}").status_code
        == 404
    )
    history = client.get(f"/api/v1/admin/org-units/{child['id']}/history").json()
    assert any(
        e["action"] == "organization.created" and e["reason"] == "Synthetic organization setup"
        for e in history["items"]
    )
    assert all(e["action"].startswith("organization.") for e in history["items"])
    assert client.get("/api/v1/organization-admin-grants").json()["items"][0]["id"] == grant["id"]


def test_archival_rejects_memberships_children_and_restores_closed(client, seeded):
    admin(client, seeded)
    college = create_org(client)
    dept = create_org(client, "department", college["id"])
    assert (
        mutate(
            client,
            "POST",
            f"admin/org-units/{college['id']}/archive",
            {"reason": "Archive"},
            college["version"],
        ).status_code
        == 409
    )
    before = client.get(f"/api/v1/admin/org-units/{A}?purpose=administration").json()
    assert (
        mutate(
            client, "POST", f"admin/org-units/{A}/archive", {"reason": "In-use"}, before["version"]
        ).status_code
        == 409
    )
    opened = mutate(
        client,
        "PUT",
        f"admin/org-units/{dept['id']}/enrollment",
        {"enabled": True, "reason": "Open"},
        dept["version"],
    ).json()
    archived = mutate(
        client,
        "POST",
        f"admin/org-units/{dept['id']}/archive",
        {"reason": "Archive empty"},
        opened["version"],
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["enrollment_enabled"] is False
    college_archived = mutate(
        client,
        "POST",
        f"admin/org-units/{college['id']}/archive",
        {"reason": "Archive parent"},
        college["version"],
    )
    assert college_archived.status_code == 200, college_archived.text
    assert (
        mutate(
            client,
            "POST",
            f"admin/org-units/{dept['id']}/restore",
            {"reason": "Blocked parent"},
            archived.json()["version"],
        ).status_code
        == 409
    )
    assert (
        mutate(
            client,
            "POST",
            f"admin/org-units/{college['id']}/restore",
            {"reason": "Restore parent"},
            college_archived.json()["version"],
        ).status_code
        == 200
    )
    restored = mutate(
        client,
        "POST",
        f"admin/org-units/{dept['id']}/restore",
        {"reason": "Restore child"},
        archived.json()["version"],
    )
    assert restored.status_code == 200 and restored.json()["enrollment_enabled"] is False


def test_archive_cancels_invitation_and_pending_activation(client, seeded, settings):
    from app.mail_worker import deliver_once
    from app.staff_services import invitation_token

    uid = create_user(seeded, "archive-target@advisory.test")
    admin(client, seeded)
    college = create_org(client)
    dept = create_org(client, "department", college["id"])
    opened = mutate(
        client,
        "PUT",
        f"admin/org-units/{dept['id']}/enrollment",
        {"enabled": True, "reason": "Open"},
        dept["version"],
    ).json()
    invite = mutate(
        client,
        "POST",
        "invitations",
        {"org_unit_id": dept["id"], "email": "archive-target@advisory.test", "role": "advisor"},
    )
    assert invite.status_code == 201, invite.text
    with Session(seeded) as db:
        token = invitation_token(db.get(Invitation, invite.json()["id"]), settings)
    login(client, "archive-target")
    req = mutate(
        client,
        "POST",
        "membership-requests",
        {
            "org_unit_id": dept["id"],
            "requested_role": "advisor",
            "justification": "Synthetic request",
        },
    )
    assert req.status_code == 201, req.text
    login(client, "super-admin", True)
    archived = mutate(
        client,
        "POST",
        f"admin/org-units/{dept['id']}/archive",
        {"reason": "Archive pending"},
        opened["version"],
    )
    assert archived.status_code == 200, archived.text
    assert mutate(
        client,
        "POST",
        f"membership-requests/{req.json()['id']}/approve",
        {"reason": "Old request"},
        1,
    ).status_code in {403, 404, 409}
    with Session(seeded) as db:
        assert db.get(Invitation, invite.json()["id"]).status == "revoked"
        assert (
            db.scalar(
                select(OutboxEvent.state).where(OutboxEvent.aggregate_id == invite.json()["id"])
            )
            == "cancelled"
        )
        assert not db.scalar(select(RoleGrant.id).where(RoleGrant.user_id == uid))
    cfg = settings.model_copy(
        update={
            "mail_database_url": settings.database_url.__class__(
                "postgresql+psycopg://advisory_mail:local-mail-only@127.0.0.1:5432/advisory_test"
            )
        }
    )
    assert deliver_once(cfg) == 0
    login(client, "archive-target")
    assert mutate(client, "POST", "invitations/accept", {"token": token}).status_code == 409
    assert (
        mutate(
            client,
            "POST",
            "membership-requests",
            {"org_unit_id": dept["id"], "requested_role": "student", "justification": "Archived"},
        ).status_code
        == 404
    )


def test_delegation_revocation_account_suspension_and_expiry(client, seeded):
    uid = create_user(seeded, "org-lifecycle@advisory.test")
    admin(client, seeded)
    grant = delegate(client, uid)
    with TestClient(client.app, base_url="http://localhost:3000") as other:
        login(other, "org-lifecycle", True)
        assert other.get("/api/v1/admin/institutions").json()["total"] == 1
        r = mutate(
            client,
            "POST",
            f"organization-admin-grants/{grant['id']}/state",
            {"status": "suspended", "reason": "Remove authority"},
            grant["version"],
        )
        assert r.status_code == 200, r.text
        assert other.get(f"/api/v1/admin/org-units/{A}").status_code == 404
        restored = mutate(
            client,
            "POST",
            f"organization-admin-grants/{grant['id']}/state",
            {"status": "active", "reason": "Explicit restore"},
            r.json()["version"],
        )
        assert restored.status_code == 200, restored.text
        with Session(seeded) as db:
            epoch = db.get(User, uid).grant_epoch
        assert (
            mutate(
                client,
                "POST",
                f"users/{uid}/state",
                {"status": "suspended", "reason": "Account suspended"},
                epoch,
            ).status_code
            == 200
        )
        assert other.get("/api/v1/me").status_code == 401
        with Session(seeded) as db:
            assert db.get(OrganizationAdminGrant, grant["id"]).status == "suspended"
            epoch = db.get(User, uid).grant_epoch
        assert (
            mutate(
                client,
                "POST",
                f"users/{uid}/state",
                {"status": "active", "reason": "Account restored"},
                epoch,
            ).status_code
            == 200
        )
        login(other, "org-lifecycle", True)
        assert other.get("/api/v1/me").json()["administration_capabilities"] == []
    with Session(seeded) as db, db.begin():
        db.add(
            OrganizationAdminGrant(
                user_id=uid,
                institution_id=OTHER,
                scope_kind="institution",
                valid_until=now() - timedelta(seconds=1),
            )
        )
    login(client, "org-lifecycle", True)
    assert client.get(f"/api/v1/admin/org-units?institution_id={OTHER}").status_code == 404


def test_rls_no_context_write_guards_and_pool_reuse(client, seeded, settings):
    uid = create_user(seeded, "org-policy@advisory.test")
    admin(client, seeded)
    delegate(client, uid, COLLEGE)
    engine = make_engine(settings.database_url.get_secret_value())
    with Session(engine) as db, db.begin():
        assert list(db.scalars(select(OrganizationAdminGrant))) == []
        assert list(db.scalars(select(OrgUnit))) == []
    with Session(engine) as db, db.begin():
        context(db, user_id=str(uid), mfa="true")
        assert db.scalar(text("SELECT count(*) FROM org_units")) == 3
        assert (
            db.scalar(
                text("SELECT count(*) FROM org_units WHERE institution_id=:id"), {"id": OTHER}
            )
            == 0
        )
    with Session(engine) as db, db.begin():
        assert db.scalar(text("SELECT count(*) FROM org_units")) == 0
        with pytest.raises(DBAPIError):
            db.execute(
                text(
                    "INSERT INTO org_units(id,institution_id,code,name,kind,timezone) "
                    "VALUES(:id,:inst,'deny','Denied','college','UTC')"
                ),
                {"id": uuid4(), "inst": INST},
            )
    engine.dispose()
    with Session(seeded) as db, db.begin():
        org = db.get(OrgUnit, A)
        with pytest.raises(DBAPIError):
            org.parent_id = fixture_id("other-college")
            db.flush()


def test_duplicate_creation_cursor_epoch_and_idempotency(client, seeded):
    admin(client, seeded)
    payload = {
        "institution_id": str(INST),
        "kind": "college",
        "code": "race-college",
        "name": "Synthetic concurrent college",
        "timezone": "UTC",
        "reason": "Race",
    }
    with TestClient(client.app, base_url="http://localhost:3000") as other:
        login(other, "super-admin", True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            fs = [
                pool.submit(mutate, c, "POST", "admin/org-units", payload) for c in [client, other]
            ]
            statuses = [f.result(timeout=15).status_code for f in fs]
    assert sorted(statuses) == [201, 409], statuses
    page = client.get(
        f"/api/v1/admin/org-units?institution_id={INST}&purpose=administration&limit=1"
    ).json()
    assert page["next_cursor"]
    key = str(uuid4())
    payload["code"] = "idempotent-college"
    first = mutate(client, "POST", "admin/org-units", payload, key=key)
    second = mutate(client, "POST", "admin/org-units", payload, key=key)
    assert first.status_code == 201 and first.json() == second.json()
    assert (
        client.get(
            f"/api/v1/admin/org-units?institution_id={INST}&purpose=administration&limit=1&cursor={page['next_cursor']}"
        ).status_code
        == 409
    )
    with Session(seeded) as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(AuditEvent).where(
                            AuditEvent.action == "organization.created",
                            AuditEvent.object_id == first.json()["id"],
                        )
                    )
                )
            )
            == 1
        )


@pytest.mark.parametrize(
    "change",
    [
        {"timezone": "Invalid/Timezone"},
        {"name": " "},
        {"code": "x" * 81},
        {"kind": "department", "parent_id": str(fixture_id("other-college"))},
    ],
)
def test_invalid_metadata_and_cross_institution_parent(client, seeded, change):
    admin(client, seeded)
    body = {
        "institution_id": str(INST),
        "kind": "college",
        "parent_id": None,
        "name": "Invalid synthetic input",
        "code": "invalid-input",
        "timezone": "UTC",
        "reason": "Validation",
    }
    body.update(change)
    response = mutate(client, "POST", "admin/org-units", body)
    assert response.status_code in {404, 409, 422}, response.text
    assert "Invalid/Timezone" not in response.text


def test_org_mutation_csrf_recent_auth_and_denial_audit(client, seeded):
    admin(client, seeded)
    assert (
        client.post(
            "/api/v1/admin/org-units",
            json={
                "institution_id": str(INST),
                "kind": "college",
                "name": "Denied",
                "code": "denied",
                "timezone": "UTC",
                "reason": "Missing csrf",
            },
        ).status_code
        == 403
    )
    from app.models import LoginSession
    from app.security import COOKIE, digest

    with Session(seeded) as db, db.begin():
        session = db.scalar(
            select(LoginSession).where(
                LoginSession.token_hash == digest(client.cookies.get(COOKIE))
            )
        )
        session.auth_time = now() - timedelta(minutes=11)
    response = mutate(
        client,
        "POST",
        "admin/org-units",
        {
            "institution_id": str(INST),
            "kind": "college",
            "name": "Denied",
            "code": "denied",
            "timezone": "UTC",
            "reason": "Expired auth",
        },
    )
    assert response.status_code == 403
    with Session(seeded) as db:
        denies = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "organization.create", AuditEvent.result == "deny"
                )
            )
        )
        assert len(denies) == 2
        assert all(e.reason_id is None for e in denies)


def test_archive_races_approval_without_orphaning_membership(client, seeded):
    uid = create_user(seeded, "org-race@advisory.test")
    admin(client, seeded)
    college = create_org(client)
    dept = create_org(client, "department", college["id"])
    opened = mutate(
        client,
        "PUT",
        f"admin/org-units/{dept['id']}/enrollment",
        {"enabled": True, "reason": "Open"},
        dept["version"],
    ).json()
    login(client, "org-race")
    req = mutate(
        client,
        "POST",
        "membership-requests",
        {
            "org_unit_id": dept["id"],
            "requested_role": "advisor",
            "justification": "Concurrent activation",
        },
    ).json()
    login(client, "super-admin", True)
    with TestClient(client.app, base_url="http://localhost:3000") as other:
        login(other, "super-admin", True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            approve = pool.submit(
                mutate,
                client,
                "POST",
                f"membership-requests/{req['id']}/approve",
                {"reason": "Activate"},
                1,
            )
            archive = pool.submit(
                mutate,
                other,
                "POST",
                f"admin/org-units/{dept['id']}/archive",
                {"reason": "Archive"},
                opened["version"],
            )
            codes = [approve.result(timeout=15).status_code, archive.result(timeout=15).status_code]
    assert codes in [[200, 409], [404, 200], [403, 200], [409, 200]], codes
    with Session(seeded) as db:
        org = db.get(OrgUnit, dept["id"])
        grant = db.scalar(select(RoleGrant).where(RoleGrant.user_id == uid))
        assert (org.status == "active" and grant is not None and grant.status == "active") or (
            org.status == "archived" and grant is None
        )


def test_blank_institution_admin_and_manager_appointment_stays_separate(client, seeded):
    with Session(seeded) as db, db.begin():
        institution = Institution(code="empty-synthetic", name="Empty synthetic institution")
        db.add(institution)
        db.flush()
        iid = institution.id
    uid = create_user(seeded, "org-empty@advisory.test")
    admin(client, seeded)
    delegate(client, uid, institution=iid)
    login(client, "org-empty", True)
    assert client.get(f"/api/v1/admin/org-units?institution_id={iid}").json()["items"] == []
    college = create_org(client, institution=iid)
    dept = create_org(client, "department", college["id"], institution=iid)
    assert (
        mutate(
            client,
            "POST",
            "role-grants",
            {
                "user_id": str(fixture_id("advisor-a")),
                "org_unit_id": dept["id"],
                "role": "manager",
                "reason": "No appointment authority",
            },
        ).status_code
        == 403
    )
    login(client, "super-admin", True)
    appointed = mutate(
        client,
        "POST",
        "role-grants",
        {
            "user_id": str(fixture_id("advisor-a")),
            "org_unit_id": dept["id"],
            "role": "manager",
            "reason": "Separate explicit appointment",
        },
    )
    assert appointed.status_code == 201, appointed.text
    assert appointed.json()["role"] == "manager"
