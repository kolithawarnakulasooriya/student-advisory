from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap
from app.models import (
    AdvisorAssignment,
    AuditEvent,
    Invitation,
    MembershipRequest,
    OutboxEvent,
    PlatformGrant,
    RoleGrant,
    StudentMembership,
    User,
)
from app.security import digest, now
from app.seed import fixture_id
from tests.conftest import login

A = fixture_id("department-a")
B = fixture_id("department-b")
ADVISOR = fixture_id("grant:advisor-a:department-a")
ADVISOR2 = fixture_id("grant:advisor-a2:department-a")
MEMBER = fixture_id("grant:student-a:department-a")


def mutate(client, method, path, body, version=None, key=None):
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    headers = {
        "Origin": "http://localhost:3000",
        "X-CSRF-Token": csrf,
        "Idempotency-Key": key or str(uuid4()),
    }
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return client.request(method, "/api/v1/" + path, json=body, headers=headers)


def create_user(owner, email="new-student@advisory.test"):
    with Session(owner) as db, db.begin():
        u = User(
            issuer="urn:advisory:synthetic",
            subject=str(uuid4()),
            email=email,
            name="Synthetic new identity",
            verified=True,
            status="active",
        )
        db.add(u)
        db.flush()
        uid = u.id
    return uid


def promote(owner):
    with Session(owner) as db, db.begin():
        bootstrap(db, "super-admin@advisory.test")


def test_student_summary_boundaries(client):
    login(client, "student-a")
    assert client.get(f"/api/v1/students/{MEMBER}").status_code == 200
    for account, mfa, status in [
        ("advisor-a", True, 200),
        ("unassigned-advisor", True, 404),
        ("secretary", True, 404),
        ("student-b", False, 404),
        ("manager", True, 200),
    ]:
        login(client, account, mfa)
        r = client.get(f"/api/v1/students/{MEMBER}")
        assert r.status_code == status, r.text
    login(client, "secretary", True)
    r = client.get(f"/api/v1/memberships?scope_id={A}")
    assert r.status_code == 200, r.text
    assert r.json()["total"] > 0
    assert client.get(f"/api/v1/students?scope_id={A}").json()["total"] == 0


def test_request_approval_requires_advisor_and_is_atomic(client, seeded):
    uid = create_user(seeded)
    login(client, "new-student")
    opts = client.get("/api/v1/membership-options")
    assert opts.status_code == 200 and len(opts.json()["items"]) == 2
    key = str(uuid4())
    request = mutate(
        client,
        "POST",
        "membership-requests",
        {
            "org_unit_id": str(A),
            "requested_role": "student",
            "justification": "Synthetic enrollment",
        },
        key=key,
    )
    assert request.status_code == 201, request.text
    assert (
        mutate(
            client,
            "POST",
            "membership-requests",
            {
                "org_unit_id": str(A),
                "requested_role": "student",
                "justification": "Synthetic enrollment",
            },
            key=key,
        ).json()["id"]
        == request.json()["id"]
    )
    rid = request.json()["id"]
    login(client, "manager", True)
    r = mutate(
        client, "POST", f"membership-requests/{rid}/approve", {"reason": "Synthetic approval"}, 1
    )
    assert r.status_code == 409, r.text
    with Session(seeded) as db:
        assert db.get(MembershipRequest, rid).status == "pending"
        assert not db.scalar(select(RoleGrant).where(RoleGrant.user_id == uid))
    r = mutate(
        client,
        "POST",
        f"membership-requests/{rid}/approve",
        {"reason": "Synthetic approval", "advisor_grant_id": str(ADVISOR)},
        1,
    )
    assert r.status_code == 200, r.text
    with Session(seeded) as db:
        grant = db.scalar(select(RoleGrant).where(RoleGrant.user_id == uid))
        member = db.scalar(select(StudentMembership).where(StudentMembership.grant_id == grant.id))
        assert member and db.scalar(
            select(AdvisorAssignment).where(
                AdvisorAssignment.student_membership_id == member.id,
                AdvisorAssignment.ended_at.is_(None),
            )
        )
        assert db.scalar(select(AuditEvent).where(AuditEvent.object_id == rid))
    assert (
        mutate(
            client,
            "POST",
            f"membership-requests/{rid}/approve",
            {"reason": "Synthetic approval", "advisor_grant_id": str(ADVISOR)},
            1,
        ).status_code
        == 409
    )


def test_manager_requests_only_super_admin_and_bootstrap_not_automatic(client, seeded):
    create_user(seeded, "new-manager@advisory.test")
    login(client, "new-manager")
    r = mutate(
        client,
        "POST",
        "membership-requests",
        {
            "org_unit_id": str(A),
            "requested_role": "manager",
            "justification": "Synthetic manager request",
        },
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    login(client, "super-admin", True)
    # Department-level legacy labels never appoint managers or imply global authority.
    assert (
        mutate(
            client, "POST", f"membership-requests/{rid}/approve", {"reason": "Review"}, 1
        ).status_code
        == 404
    )
    promote(seeded)
    r = mutate(
        client, "POST", f"membership-requests/{rid}/approve", {"reason": "Synthetic appointment"}, 1
    )
    assert r.status_code == 200, r.text
    with Session(seeded) as db, db.begin():
        with pytest.raises(ValueError):
            bootstrap(db, "new-manager@advisory.test")
    assert client.get("/api/v1/users").status_code == 403
    assert client.get("/api/v1/users?purpose=administration").status_code == 200


def test_delegation_and_no_self_approval(client, seeded):
    login(client, "manager", True)
    r = client.get(f"/api/v1/memberships?scope_id={A}").json()
    secretary = next(g for g in r["items"] if g["email"] == "secretary-no-delegation@advisory.test")
    response = mutate(
        client,
        "PATCH",
        f"role-grants/{secretary['id']}",
        {"capabilities": ["student.approve"], "reason": "Synthetic delegation"},
        secretary["version"],
    )
    assert response.status_code == 200, response.text
    assert (
        mutate(
            client,
            "PATCH",
            f"role-grants/{secretary['id']}",
            {"capabilities": ["student.read"], "reason": "Forbidden record access"},
            response.json()["version"],
        ).status_code
        == 422
    )
    login(client, "secretary-no-delegation", True)
    requests = client.get(f"/api/v1/membership-requests?scope_id={A}").json()["items"]
    pending = next(r for r in requests if r["requested_role"] == "student")
    assert (
        mutate(
            client,
            "POST",
            f"membership-requests/{pending['id']}/approve",
            {"reason": "Delegated approval", "advisor_grant_id": str(ADVISOR)},
            pending["version"],
        ).status_code
        == 200
    )
    assert (
        mutate(
            client,
            "POST",
            "invitations",
            {
                "email": "blocked@advisory.test",
                "org_unit_id": str(A),
                "role": "student",
                "advisor_grant_id": str(ADVISOR),
            },
        ).status_code
        == 403
    )
    login(client, "manager", True)
    assert (
        mutate(
            client,
            "POST",
            "invitations",
            {"email": "manager@advisory.test", "org_unit_id": str(A), "role": "advisor"},
        ).status_code
        == 403
    )
    r = mutate(
        client,
        "POST",
        "membership-requests",
        {
            "org_unit_id": str(A),
            "requested_role": "advisor",
            "justification": "Own additional role",
        },
    )
    assert r.status_code == 201, r.text
    assert (
        mutate(
            client,
            "POST",
            f"membership-requests/{r.json()['id']}/approve",
            {"reason": "Self appointment"},
            1,
        ).status_code
        == 403
    )


def test_reassignment_revokes_former_advisor_and_stale_updates(client, seeded):
    login(client, "manager", True)
    before = client.get(f"/api/v1/students/{MEMBER}").json()
    r = mutate(
        client,
        "PUT",
        f"students/{MEMBER}/advisor",
        {"advisor_grant_id": str(ADVISOR2), "reason": "Synthetic reassignment"},
        before["version"],
    )
    assert r.status_code == 200, r.text
    assert (
        mutate(
            client,
            "PUT",
            f"students/{MEMBER}/advisor",
            {"advisor_grant_id": str(ADVISOR), "reason": "Stale reassignment"},
            before["version"],
        ).status_code
        == 409
    )
    login(client, "advisor-a", True)
    assert client.get(f"/api/v1/students/{MEMBER}").status_code == 404
    assert client.get(f"/api/v1/students?scope_id={A}").json()["total"] == 0
    login(client, "advisor-a2", True)
    assert client.get(f"/api/v1/students/{MEMBER}").status_code == 200
    with Session(seeded) as db:
        member = db.get(StudentMembership, MEMBER)
        assert member.relationship_epoch > before["relationship_epoch"]
        assert (
            len(
                list(
                    db.scalars(
                        select(AdvisorAssignment).where(
                            AdvisorAssignment.student_membership_id == MEMBER
                        )
                    )
                )
            )
            == 2
        )


def test_suspension_session_revocation_and_explicit_reactivation(client, seeded):
    promote(seeded)
    login(client, "manager", True)
    token = client.cookies.get("advisory_session")
    login(client, "super-admin", True)
    user = client.get("/api/v1/users?purpose=administration&email=manager@advisory.test").json()[
        "items"
    ][0]
    r = mutate(
        client,
        "POST",
        f"users/{user['id']}/state",
        {"status": "suspended", "reason": "Synthetic suspension"},
        user["grant_epoch"],
    )
    assert r.status_code == 200, r.text
    with Session(seeded) as db:
        grants = list(db.scalars(select(RoleGrant).where(RoleGrant.user_id == user["id"])))
        assert all(g.status == "suspended" for g in grants)
        epoch = db.get(User, user["id"]).grant_epoch
    # The old cookie is denied even though its original absolute timeout has not elapsed.
    with TestClient(client.app, base_url="http://localhost:3000") as old:
        old.cookies.set("advisory_session", token)
        assert old.get("/api/v1/me").status_code == 401
    r = mutate(
        client,
        "POST",
        f"users/{user['id']}/state",
        {"status": "active", "reason": "Account only", "approved_grant_ids": []},
        epoch,
    )
    assert r.status_code == 200, r.text
    with Session(seeded) as db:
        assert all(
            g.status == "suspended"
            for g in db.scalars(select(RoleGrant).where(RoleGrant.user_id == user["id"]))
        )


def test_last_super_admin_guard(client, seeded):
    promote(seeded)
    login(client, "super-admin", True)
    rows = client.get("/api/v1/platform-grants?purpose=administration").json()["items"]
    assert len(rows) == 1
    r = mutate(
        client,
        "POST",
        f"platform-grants/{rows[0]['id']}/state",
        {"status": "revoked", "reason": "Attempt removal"},
        rows[0]["version"],
    )
    assert r.status_code == 409 and r.json()["code"] == "LAST_SUPER_ADMIN", r.text


def test_audit_survives_denial_and_is_append_only(client, seeded):
    login(client, "secretary", True)
    assert client.get(f"/api/v1/students/{MEMBER}").status_code == 404
    with Session(seeded) as db:
        row = db.scalar(
            select(AuditEvent).where(AuditEvent.result == "deny").order_by(AuditEvent.id.desc())
        )
        assert row and row.actor_id == fixture_id("secretary")
        assert row.object_id is None
    for table in ["audit_events", "users"]:
        with Session(client.app.state.engine) as db:
            with pytest.raises(DBAPIError):
                db.execute(text(f"DELETE FROM {table}"))


def test_cursors_bound_to_actor_scope_and_counts(client):
    login(client, "manager", True)
    for endpoint in ("membership-options", f"eligible-advisors?scope_id={A}"):
        separator = "&" if "?" in endpoint else "?"
        first = client.get(f"/api/v1/{endpoint}{separator}limit=1").json()
        assert len(first["items"]) == 1 and first["total"] >= 2 and first["next_cursor"]
        following = client.get(
            f"/api/v1/{endpoint}{separator}limit=1&cursor={first['next_cursor']}"
        ).json()
        assert following["items"][0]["id"] != first["items"][0]["id"]
        assert client.get(f"/api/v1/{endpoint}{separator}limit=101").status_code == 422
    data = client.get(f"/api/v1/memberships?scope_id={A}&limit=1").json()
    assert data["total"] > 1 and data["next_cursor"]
    assert (
        len(
            client.get(
                f"/api/v1/memberships?scope_id={A}&limit=1&cursor={data['next_cursor']}"
            ).json()["items"]
        )
        == 1
    )
    login(client, "secretary", True)
    assert (
        client.get(
            f"/api/v1/memberships?scope_id={A}&limit=1&cursor={data['next_cursor']}"
        ).status_code
        == 409
    )
    assert client.get(f"/api/v1/memberships?scope_id={B}").status_code == 403


def test_invite_delivery_and_acceptance(client, seeded, settings):
    from app.mail_worker import deliver_once

    create_user(seeded, "invited@advisory.test")
    login(client, "manager", True)
    r = mutate(
        client,
        "POST",
        "invitations",
        {
            "org_unit_id": str(A),
            "email": "invited@advisory.test",
            "role": "student",
            "advisor_grant_id": str(ADVISOR),
        },
    )
    assert r.status_code == 201, r.text
    assert "token" not in r.text
    cfg = settings.model_copy(
        update={
            "mail_database_url": settings.database_url.__class__(
                "postgresql+psycopg://advisory_mail:local-mail-only@127.0.0.1:5432/advisory_test"
            )
        }
    )
    assert deliver_once(cfg) == 1
    messages = httpx.get("http://127.0.0.1:8025/api/v1/messages").json()["messages"]
    message = next(
        m for m in messages if any(t["Address"] == "invited@advisory.test" for t in m["To"])
    )
    detail = httpx.get("http://127.0.0.1:8025/api/v1/message/" + message["ID"]).json()
    token = detail["Text"].split("#invitation=")[1].split()[0]
    with Session(seeded) as db:
        inv = db.get(Invitation, r.json()["id"])
        assert inv.token_hash == digest(token) and inv.token_hash != token
    login(client, "invited")
    key = str(uuid4())
    accepted = mutate(client, "POST", "invitations/accept", {"token": token}, key=key)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["advisor_grant_id"] == str(ADVISOR)
    assert (
        mutate(client, "POST", "invitations/accept", {"token": token}, key=key).status_code == 200
    )
    assert mutate(client, "POST", "invitations/accept", {"token": token}).status_code == 409


def test_capacity_contention_and_duplicate_decision(client, seeded):
    # Two independent authenticated staff sessions contend for the final synthetic capacity slot.
    with Session(seeded) as db, db.begin():
        grant = db.get(RoleGrant, ADVISOR2)
        grant.capacity = 1
    ids = []
    for name in ["capacity-one", "capacity-two"]:
        create_user(seeded, f"{name}@advisory.test")
        login(client, name)
        r = mutate(
            client,
            "POST",
            "membership-requests",
            {
                "org_unit_id": str(A),
                "requested_role": "student",
                "justification": "Synthetic capacity test",
            },
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    with (
        TestClient(client.app, base_url="http://localhost:3000") as first,
        TestClient(client.app, base_url="http://localhost:3000") as second,
    ):
        login(first, "manager", True)
        login(second, "manager", True)

        def approve_slot(pair):
            c, rid = pair
            return mutate(
                c,
                "POST",
                f"membership-requests/{rid}/approve",
                {"reason": "Capacity allocation", "advisor_grant_id": str(ADVISOR2)},
                1,
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(approve_slot, [(first, ids[0]), (second, ids[1])]))
    assert sorted(statuses) == [200, 409]
    with Session(seeded) as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(AdvisorAssignment).where(
                            AdvisorAssignment.advisor_grant_id == ADVISOR2,
                            AdvisorAssignment.ended_at.is_(None),
                        )
                    )
                )
            )
            == 1
        )


def test_concurrent_last_admin_removals(client, seeded):
    promote(seeded)
    login(client, "super-admin", True)
    r = mutate(
        client,
        "POST",
        "platform-grants",
        {"user_id": str(fixture_id("manager")), "reason": "Synthetic second administrator"},
    )
    assert r.status_code == 201, r.text
    with (
        TestClient(client.app, base_url="http://localhost:3000") as first,
        TestClient(client.app, base_url="http://localhost:3000") as second,
    ):
        login(first, "super-admin", True)
        login(second, "manager", True)
        grants = first.get("/api/v1/platform-grants?purpose=administration").json()["items"]

        def remove_own(c, uid):
            grant = next(g for g in grants if g["user_id"] == str(uid))
            return mutate(
                c,
                "POST",
                f"platform-grants/{grant['id']}/state",
                {"status": "revoked", "reason": "Concurrent demotion"},
                grant["version"],
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(remove_own, first, fixture_id("super-admin"))
            b = pool.submit(remove_own, second, fixture_id("manager"))
            statuses = [a.result(timeout=15), b.result(timeout=15)]
    assert sorted(statuses) == [200, 409], statuses
    with Session(seeded) as db:
        assert (
            len(list(db.scalars(select(PlatformGrant).where(PlatformGrant.status == "active"))))
            == 1
        )


def test_suspending_advisor_preserves_students_and_removes_access(client):
    login(client, "manager", True)
    r = mutate(
        client,
        "PATCH",
        f"memberships/{ADVISOR}",
        {"status": "suspended", "reason": "Advisor departure"},
        1,
    )
    assert r.status_code == 200, r.text
    assert client.get(f"/api/v1/students/{MEMBER}").json()["advisor_grant_id"] is None
    login(client, "advisor-a", True)
    assert client.get(f"/api/v1/students/{MEMBER}").status_code == 404
    login(client, "student-a")
    assert client.get(f"/api/v1/students/{MEMBER}").status_code == 200


def test_platform_ceiling_and_cross_scope_delegation(client, seeded):
    promote(seeded)
    login(client, "super-admin", True)
    target = create_user(seeded, "delegated@advisory.test")
    bad = mutate(
        client,
        "POST",
        "role-grants",
        {
            "user_id": str(target),
            "org_unit_id": str(A),
            "role": "platform_admin",
            "capabilities": ["manager.approve"],
            "ceiling": "student",
            "reason": "Invalid ceiling",
        },
    )
    assert bad.status_code == 422, bad.text
    r = mutate(
        client,
        "POST",
        "role-grants",
        {
            "user_id": str(target),
            "org_unit_id": str(A),
            "role": "platform_admin",
            "capabilities": ["student.approve", "membership.read"],
            "ceiling": "student",
            "reason": "Student enrollment only",
        },
    )
    assert r.status_code == 201, r.text
    login(client, "delegated", True)
    assert client.get(f"/api/v1/memberships?scope_id={A}").status_code == 200
    assert client.get(f"/api/v1/memberships?scope_id={B}").status_code == 403
    assert (
        mutate(
            client,
            "POST",
            "invitations",
            {"email": "not-allowed@advisory.test", "org_unit_id": str(A), "role": "advisor"},
        ).status_code
        == 403
    )
    assert (
        mutate(
            client,
            "POST",
            "platform-grants",
            {"user_id": str(fixture_id("student-b")), "reason": "Escalation attempt"},
        ).status_code
        == 403
    )


def test_invite_rotation_wrong_identity_expiry_and_revoked_sender(client, seeded, settings):
    from app.mail_worker import deliver_once
    from app.staff_services import invitation_token

    login(client, "manager", True)
    r = mutate(
        client,
        "POST",
        "invitations",
        {
            "org_unit_id": str(A),
            "email": "student-b@advisory.test",
            "role": "student",
            "advisor_grant_id": str(ADVISOR),
        },
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    with Session(seeded) as db:
        old = invitation_token(db.get(Invitation, iid), settings)
    resent = mutate(client, "POST", f"invitations/{iid}/resend", {"reason": "Rotate invitation"}, 1)
    assert resent.status_code == 200, resent.text
    with Session(seeded) as db:
        new = invitation_token(db.get(Invitation, iid), settings)
    assert old != new
    login(client, "student-a")
    assert mutate(client, "POST", "invitations/accept", {"token": new}).status_code == 409
    login(client, "student-b")
    assert mutate(client, "POST", "invitations/accept", {"token": old}).status_code == 409
    with Session(seeded) as db, db.begin():
        inv = db.get(Invitation, iid)
        inv.expires_at = now() - timedelta(seconds=1)
    assert mutate(client, "POST", "invitations/accept", {"token": new}).status_code == 409
    # A fresh pending invitation becomes undeliverable when its issuer loses authority.
    login(client, "manager", True)
    r = mutate(
        client,
        "POST",
        "invitations",
        {"org_unit_id": str(A), "email": "future@advisory.test", "role": "advisor"},
    )
    assert r.status_code == 201, r.text
    with Session(seeded) as db, db.begin():
        grant = db.get(RoleGrant, fixture_id("grant:manager:department-a"))
        grant.status = "revoked"
    cfg = settings.model_copy(
        update={
            "mail_database_url": settings.database_url.__class__(
                "postgresql+psycopg://advisory_mail:local-mail-only@127.0.0.1:5432/advisory_test"
            )
        }
    )
    while deliver_once(cfg):
        pass
    with Session(seeded) as db:
        assert all(
            e.state == "cancelled"
            for e in db.scalars(
                select(OutboxEvent).where(OutboxEvent.event_type == "invitation.send")
            )
        )


def test_pending_student_can_accept_invite_and_resolves_request(client, seeded, settings):
    from app.staff_services import invitation_token

    login(client, "manager", True)
    r = mutate(
        client,
        "POST",
        "invitations",
        {
            "org_unit_id": str(A),
            "email": "pending@advisory.test",
            "role": "student",
            "advisor_grant_id": str(ADVISOR),
        },
    )
    assert r.status_code == 201, r.text
    with Session(seeded) as db:
        token = invitation_token(db.get(Invitation, r.json()["id"]), settings)
    login(client, "pending")
    r = mutate(client, "POST", "invitations/accept", {"token": token})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/me").json()["membership_state"] == "active"
    assert all(
        row["status"] == "approved"
        for row in client.get("/api/v1/membership-requests").json()["items"]
    )


@pytest.mark.parametrize(
    "account,mfa",
    [
        ("student-a", False),
        ("advisor-a", True),
        ("unassigned-advisor", True),
        ("secretary-no-delegation", True),
        ("pending", False),
        ("unverified", False),
    ],
)
def test_privileged_route_denial_matrix(client, account, mfa):
    login(client, account, mfa)
    reads = [
        f"/memberships?scope_id={A}",
        f"/memberships/{MEMBER}",
        f"/invitations?scope_id={A}",
        f"/eligible-advisors?scope_id={A}",
        f"/users?scope_id={A}",
        f"/users/{fixture_id('manager')}/history?scope_id={A}",
        "/platform-grants?purpose=administration",
        f"/assignment-state/{MEMBER}",
    ]
    for path in reads:
        r = client.get("/api/v1" + path)
        assert r.status_code in {403, 404}, (account, path, r.text)
    for method, path, body in [
        ("PATCH", f"memberships/{MEMBER}", {"status": "suspended", "reason": "Unauthorized"}),
        (
            "PUT",
            f"students/{MEMBER}/advisor",
            {"advisor_grant_id": str(ADVISOR2), "reason": "Unauthorized"},
        ),
        (
            "POST",
            "role-grants",
            {
                "user_id": str(fixture_id("student-b")),
                "org_unit_id": str(A),
                "role": "manager",
                "reason": "Unauthorized",
            },
        ),
        (
            "POST",
            "platform-grants",
            {"user_id": str(fixture_id("student-b")), "reason": "Unauthorized"},
        ),
        (
            "POST",
            f"users/{fixture_id('manager')}/state",
            {"status": "suspended", "reason": "Unauthorized"},
        ),
    ]:
        r = mutate(client, method, path, body, 1)
        assert r.status_code in {403, 404}, (account, path, r.text)


def test_recent_auth_and_audit_rationale_reference(client, seeded):
    from app.models import LoginSession, OperationalReason

    login(client, "manager", True)
    token = client.cookies.get("advisory_session")
    with Session(seeded) as db, db.begin():
        session = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token)))
        session.auth_time = now() - timedelta(minutes=11)
    r = mutate(
        client,
        "PATCH",
        f"memberships/{ADVISOR}",
        {"status": "suspended", "reason": "Synthetic rationale"},
        1,
    )
    assert r.status_code == 403 and r.json()["code"] == "RECENT_AUTH_REQUIRED", r.text
    login(client, "manager", True)
    r = mutate(
        client,
        "PATCH",
        f"memberships/{ADVISOR}",
        {"status": "suspended", "reason": "Synthetic rationale"},
        1,
    )
    assert r.status_code == 200, r.text
    with Session(seeded) as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "membership.suspended"))
        assert (
            event.reason_id
            and db.get(OperationalReason, event.reason_id).text == "Synthetic rationale"
        )
    events = client.get(f"/api/v1/audit-events?scope_id={A}").json()["items"]
    assert any(e["reason"] == "Synthetic rationale" for e in events)


def test_rejection_idempotency_payload_and_requester_status(client):
    login(client, "manager", True)
    rows = client.get(f"/api/v1/membership-requests?scope_id={A}").json()["items"]
    row = next(r for r in rows if r["email"] == "pending@advisory.test")
    key = str(uuid4())
    r = mutate(
        client,
        "POST",
        f"membership-requests/{row['id']}/reject",
        {"reason": "Synthetic rejection"},
        1,
        key,
    )
    assert r.status_code == 200, r.text
    assert (
        mutate(
            client,
            "POST",
            f"membership-requests/{row['id']}/reject",
            {"reason": "Different payload"},
            1,
            key,
        ).status_code
        == 409
    )
    login(client, "pending")
    rows = client.get("/api/v1/membership-requests").json()["items"]
    assert rows[0]["status"] == "rejected" and rows[0]["decision_reason"] == "Synthetic rejection"
    assert client.get("/api/v1/me").json()["active_grants"] == []


def test_suspended_student_requires_assignment_delegation_and_advisor(client, seeded):
    login(client, "manager", True)
    row = client.get(f"/api/v1/memberships/{MEMBER}").json()
    r = mutate(
        client,
        "PATCH",
        f"memberships/{MEMBER}",
        {"status": "suspended", "reason": "Review"},
        row["version"],
    )
    assert r.status_code == 200, r.text
    suspended_version = r.json()["version"]
    with Session(seeded) as db, db.begin():
        grant = db.get(RoleGrant, fixture_id("grant:secretary-no-delegation:department-a"))
        grant.capabilities = ["student.manage"]
    login(client, "secretary-no-delegation", True)
    assert (
        mutate(
            client,
            "PATCH",
            f"memberships/{MEMBER}",
            {"status": "active", "reason": "Review", "advisor_grant_id": str(ADVISOR)},
            suspended_version,
        ).status_code
        == 403
    )
    login(client, "manager", True)
    assert (
        mutate(
            client,
            "PATCH",
            f"memberships/{MEMBER}",
            {"status": "active", "reason": "Reviewed"},
            suspended_version,
        ).status_code
        == 409
    )
    r = mutate(
        client,
        "PATCH",
        f"memberships/{MEMBER}",
        {"status": "active", "reason": "Reviewed", "advisor_grant_id": str(ADVISOR)},
        suspended_version,
    )
    assert r.status_code == 200, r.text


def test_smtp_retry_and_mail_role_cannot_modify_invitation_authority(client, seeded, settings):
    from app.mail_worker import deliver_once

    login(client, "manager", True)
    r = mutate(
        client,
        "POST",
        "invitations",
        {"email": "retry@advisory.test", "org_unit_id": str(A), "role": "advisor"},
    )
    assert r.status_code == 201, r.text
    mail_url = "postgresql+psycopg://advisory_mail:local-mail-only@127.0.0.1:5432/advisory_test"
    cfg = settings.model_copy(
        update={"mail_database_url": settings.database_url.__class__(mail_url), "smtp_port": 1}
    )
    assert deliver_once(cfg) == 1
    with Session(seeded) as db, db.begin():
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == r.json()["id"]))
        assert event.state == "pending" and event.last_error == "SMTP_UNAVAILABLE"
        event.available_at = now() - timedelta(seconds=1)
    assert deliver_once(cfg.model_copy(update={"smtp_port": 1025})) == 1
    from app.db import make_engine

    engine = make_engine(mail_url)
    with Session(engine) as db:
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE invitations SET role='manager'"))
    with Session(engine) as db:
        with pytest.raises(DBAPIError):
            db.execute(select(User))
    engine.dispose()


def test_cross_scope_membership_binding_and_advisor_cache_epoch(client, seeded):
    from sqlalchemy.exc import IntegrityError

    with Session(seeded) as db:
        with pytest.raises(IntegrityError):
            db.add(
                StudentMembership(
                    grant_id=fixture_id("grant:student-b:department-b"),
                    user_id=fixture_id("student-a"),
                    institution_id=fixture_id("synthetic"),
                    org_unit_id=A,
                )
            )
            db.flush()
    login(client, "advisor-a", True)
    before = client.get("/api/v1/me").json()["grant_epoch"]
    login(client, "manager", True)
    state = client.get(f"/api/v1/assignment-state/{MEMBER}").json()
    r = mutate(
        client,
        "PUT",
        f"students/{MEMBER}/advisor",
        {"advisor_grant_id": str(ADVISOR2), "reason": "Synthetic cache boundary"},
        state["version"],
    )
    assert r.status_code == 200, r.text
    login(client, "advisor-a", True)
    assert client.get("/api/v1/me").json()["grant_epoch"] > before


def test_manager_requests_cannot_be_approved_by_delegated_platform_admin(client, seeded):
    from app.models import MembershipRequest

    uid = create_user(seeded, "manager-candidate@advisory.test")
    with Session(seeded) as db, db.begin():
        grant = db.get(RoleGrant, fixture_id("grant:platform-admin:department-a"))
        grant.ceiling = "manager"
        grant.capabilities = ["manager.approve", "membership.read"]
        row = MembershipRequest(
            user_id=uid,
            institution_id=fixture_id("synthetic"),
            org_unit_id=A,
            requested_role="manager",
            justification="Synthetic manager request",
        )
        db.add(row)
        db.flush()
        rid = row.id
    login(client, "platform-admin", True)
    assert "manager.approve" not in client.get("/api/v1/me").json()["capabilities"]
    assert mutate(
        client,
        "POST",
        f"membership-requests/{rid}/approve",
        {"reason": "Not the required approver"},
        1,
    ).status_code in {403, 404}


def test_anonymous_requests_are_denied_across_staff_surfaces(client):
    reads = [
        "membership-options",
        f"membership-requests?scope_id={A}",
        f"memberships?scope_id={A}",
        f"memberships/{MEMBER}",
        f"students?scope_id={A}",
        f"students/{MEMBER}",
        f"eligible-advisors?scope_id={A}",
        f"assignment-state/{MEMBER}",
        "users?purpose=administration",
        "platform-grants?purpose=administration",
        f"users/{fixture_id('manager')}/history?scope_id={A}",
        "audit-events",
    ]
    for path in reads:
        r = client.get("/api/v1/" + path)
        assert r.status_code == 401, (path, r.text)
        assert "student-a@advisory.test" not in r.text
    writes = [
        (
            "POST",
            "membership-requests",
            {"org_unit_id": str(A), "requested_role": "student", "justification": "No identity"},
        ),
        (
            "POST",
            "invitations",
            {"org_unit_id": str(A), "role": "advisor", "email": "anonymous@advisory.test"},
        ),
        ("POST", "invitations/accept", {"token": "a" * 64}),
        ("POST", f"invitations/{uuid4()}/revoke", {"reason": "No identity"}),
        ("POST", f"invitations/{uuid4()}/resend", {"reason": "No identity"}),
        ("POST", f"membership-requests/{uuid4()}/approve", {"reason": "No identity"}),
        ("POST", f"membership-requests/{uuid4()}/reject", {"reason": "No identity"}),
        ("PATCH", f"memberships/{MEMBER}", {"status": "suspended", "reason": "No identity"}),
        (
            "PUT",
            f"students/{MEMBER}/advisor",
            {"advisor_grant_id": str(ADVISOR2), "reason": "No identity"},
        ),
        (
            "POST",
            f"users/{fixture_id('manager')}/state",
            {"status": "suspended", "reason": "No identity"},
        ),
        (
            "POST",
            "platform-grants",
            {"user_id": str(fixture_id("manager")), "reason": "No identity"},
        ),
    ]
    for method, path, body in writes:
        r = mutate(client, method, path, body, 1)
        assert r.status_code == 401, (path, r.text)


@pytest.mark.parametrize("flow", ["approval", "invitation"])
def test_concurrent_duplicate_activation_has_one_effect(client, seeded, settings, flow):
    from threading import Barrier

    from app.staff_services import invitation_token

    uid = create_user(seeded, "concurrent-target@advisory.test")
    token = None
    if flow == "approval":
        login(client, "concurrent-target")
        response = mutate(
            client,
            "POST",
            "membership-requests",
            {"org_unit_id": str(A), "requested_role": "student", "justification": "Race fixture"},
        )
        assert response.status_code == 201, response.text
        path = f"membership-requests/{response.json()['id']}/approve"
        body = {"reason": "Concurrent review", "advisor_grant_id": str(ADVISOR)}
    else:
        login(client, "manager", True)
        response = mutate(
            client,
            "POST",
            "invitations",
            {
                "org_unit_id": str(A),
                "email": "concurrent-target@advisory.test",
                "role": "student",
                "advisor_grant_id": str(ADVISOR),
            },
        )
        assert response.status_code == 201, response.text
        with Session(seeded) as db:
            token = invitation_token(db.get(Invitation, response.json()["id"]), settings)
        path, body = "invitations/accept", {"token": token}
    barrier = Barrier(2)
    with (
        TestClient(client.app, base_url="http://localhost:3000") as first,
        TestClient(client.app, base_url="http://localhost:3000") as second,
    ):
        for connection in (first, second):
            login(
                connection,
                "manager" if flow == "approval" else "concurrent-target",
                flow == "approval",
            )

        def attempt(connection):
            barrier.wait(timeout=10)
            return mutate(
                connection, "POST", path, body, 1 if flow == "approval" else None
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt, connection) for connection in (first, second)]
            statuses = [future.result(timeout=15) for future in futures]
    assert sorted(statuses) == [200, 409], statuses
    with Session(seeded) as db:
        grants = list(db.scalars(select(RoleGrant).where(RoleGrant.user_id == uid)))
        assert len(grants) == 1 and grants[0].status == "active"
        members = list(
            db.scalars(select(StudentMembership).where(StudentMembership.user_id == uid))
        )
        assert len(members) == 1
        assert (
            len(
                list(
                    db.scalars(
                        select(AdvisorAssignment).where(
                            AdvisorAssignment.student_membership_id == members[0].id
                        )
                    )
                )
            )
            == 1
        )
        assert (
            len(
                list(
                    db.scalars(
                        select(AuditEvent).where(
                            AuditEvent.action == "membership.activated",
                            AuditEvent.object_id == str(grants[0].id),
                        )
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
                            OutboxEvent.event_type == "membership.activated",
                            OutboxEvent.aggregate_id == grants[0].id,
                        )
                    )
                )
            )
            == 1
        )
