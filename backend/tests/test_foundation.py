from datetime import timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import context, make_engine
from app.identity import MockIdentityProvider
from app.models import AdvisorAssignment, LoginSession, OrgUnit, RoleGrant, User, Verification
from app.security import ApiError, digest, now, require_recent
from app.seed import disposable_url, fixture_id, seed
from tests.conftest import login, post


def test_health_and_errors(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").json() == {"status": "alive"}
    assert client.get("/api/v1/health/ready").status_code == 200
    response = client.get("/api/v1/me", headers={"X-Correlation-Id": "injected"})
    assert response.status_code == 401
    assert response.json()["correlation_id"] != "injected"
    assert response.headers["cache-control"] == "no-store"
    assert "database" not in response.text.lower()


def test_database_down_readiness(client: TestClient) -> None:
    app = client.app
    previous = app.state.engine
    app.state.engine = make_engine("postgresql+psycopg://absent@127.0.0.1:1/missing")
    assert client.get("/api/v1/health/live").status_code == 200
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "absent" not in response.text
    app.state.engine.dispose()
    app.state.engine = previous


@pytest.mark.parametrize(
    "account,role",
    [
        ("student-a", "student"),
        ("advisor-a", "advisor"),
        ("secretary", "secretary"),
        ("manager", "manager"),
        ("platform-admin", "platform_admin"),
        ("super-admin", "super_admin"),
    ],
)
def test_each_role_lands(client: TestClient, account: str, role: str) -> None:
    login(client, account, mfa=role != "student")
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    me = response.json()
    assert any(g["role"] == role for g in me["active_grants"])
    assert "org.read" in me["capabilities"]
    assert me["identity_mode"] == "synthetic"
    assert client.get("/api/v1/org-units/" + me["active_scope"]).status_code == 200


@pytest.mark.parametrize(
    "account",
    [
        "student-a",
        "advisor-a",
        "secretary",
        "manager",
        "platform-admin",
        "super-admin",
        "multi-role",
    ],
)
def test_wrong_scope_and_institution(client: TestClient, account: str) -> None:
    login(client, account, mfa=account != "student-a")
    for name in (["department-b"] if account not in {"multi-role", "super-admin"} else []) + [
        "other-department"
    ]:
        org_id = str(fixture_id(name))
        response = client.get("/api/v1/org-units/" + org_id)
        assert response.status_code == 404
        assert name not in response.text
        assert client.get("/api/v1/me", params={"scope_id": org_id}).status_code == 404
        assert client.get("/api/v1/org-units", params={"scope_id": org_id}).status_code == 404
    ids = {r["id"] for r in client.get("/api/v1/org-units").json()}
    expected = {str(fixture_id("department-a"))}
    if account in {"multi-role", "super-admin"}:
        expected.add(str(fixture_id("department-b")))
    assert ids == expected
    assert client.get("/api/v1/org-units/" + str(uuid4())).status_code == 404


@pytest.mark.parametrize("account", ["pending", "unverified", "revoked"])
def test_no_active_membership(client: TestClient, account: str) -> None:
    login(client, account)
    me = client.get("/api/v1/me").json()
    assert me["scopes"] == [] and me["active_grants"] == []
    assert me["capabilities"] == []
    assert client.get("/api/v1/org-units").json() == []
    assert client.get(f"/api/v1/org-units/{fixture_id('department-a')}").status_code == 404


def test_staff_mfa_is_explicit_and_rotates_session(client: TestClient) -> None:
    login(client, "manager")
    before = client.cookies.get("advisory_session")
    me = client.get("/api/v1/me").json()
    assert me["mfa_required"] and me["scopes"] == []
    assert client.get("/api/v1/org-units").json() == []
    assert post(client, "auth/simulator/step-up").status_code == 200
    assert before != client.cookies.get("advisory_session")
    assert not client.get("/api/v1/me").json()["mfa_required"]
    assert client.get("/api/v1/org-units").json()


def test_csrf_and_injected_identity(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v1/auth/sign-in",
            json={"email": "manager@advisory.test"},
            headers={"X-User-Role": "super_admin"},
        ).status_code
        == 401
    )
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert (
        client.post(
            "/api/v1/auth/sign-in",
            json={"email": "manager@advisory.test"},
            headers={"Origin": "http://evil.test", "X-CSRF-Token": csrf},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/sign-in",
            json={"email": "manager@advisory.test"},
            headers={"Origin": "http://localhost:3000"},
        ).status_code
        == 403
    )
    assert (
        post(
            client,
            "auth/sign-in",
            {"email": "student-a@advisory.test", "role": "super_admin", "mfa": True},
        ).status_code
        == 422
    )


def test_registration_verification_no_grant(client: TestClient, seeded: Engine) -> None:
    response = post(
        client,
        "auth/register",
        {"email": "New.Name+tag@Advisory.TEST", "name": "Synthetic new identity"},
    )
    assert response.status_code == 201
    token = response.json()["simulator_challenge"]
    before = client.cookies.get("advisory_session")
    me = client.get("/api/v1/me").json()
    uid = me["user_id"]
    assert me["email"] == "New.Name+tag@advisory.test" and not me["verified"]
    assert post(client, "auth/verify", {"challenge": token}).status_code == 200
    assert client.cookies.get("advisory_session") != before
    me = client.get("/api/v1/me").json()
    assert me["verified"] and me["active_grants"] == []
    assert me["membership_state"] == "awaiting_membership"
    assert post(client, "auth/verify", {"challenge": token}).status_code == 409
    assert post(client, "auth/logout").status_code == 200
    assert post(client, "auth/sign-in", {"email": me["email"]}).status_code == 200
    assert client.get("/api/v1/me").json()["user_id"] == uid
    with Session(seeded) as db:
        assert db.get(User, uid) is not None
        challenge = db.scalar(select(Verification).where(Verification.token_hash == digest(token)))
        assert challenge and challenge.used
        assert challenge.token_hash != token


def test_verification_expiry_and_wrong_user(client: TestClient, seeded: Engine) -> None:
    login(client, "unverified")
    token = post(client, "auth/simulator/challenge").json()["simulator_challenge"]
    with Session(seeded) as db, db.begin():
        challenge = db.scalar(select(Verification).where(Verification.token_hash == digest(token)))
        assert challenge
        challenge.expires_at = now() - timedelta(seconds=1)
    assert post(client, "auth/verify", {"challenge": token}).status_code == 409
    token = post(client, "auth/simulator/challenge").json()["simulator_challenge"]
    login(client, "student-b")
    assert post(client, "auth/verify", {"challenge": token}).status_code == 409


def test_logout_revocation_and_cookie_settings(client: TestClient, seeded: Engine) -> None:
    login(client)
    token = client.cookies.get("advisory_session")
    assert token
    response = client.get("/api/v1/auth/csrf")
    assert "csrf_token" in response.json()
    assert post(client, "auth/logout").status_code == 200
    assert client.get("/api/v1/me").status_code == 401
    client.cookies.set("advisory_session", token)
    assert client.get("/api/v1/me").status_code == 401
    with Session(seeded) as db:
        row = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token)))
        assert row and row.revoked
        assert row.token_hash != token
    client.cookies.clear()
    cookie = client.get("/api/v1/auth/csrf").headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


@pytest.mark.parametrize("change", ["idle", "absolute", "revoked", "suspended", "grant"])
def test_live_revocation_and_expiry(client: TestClient, seeded: Engine, change: str) -> None:
    login(client)
    token = client.cookies.get("advisory_session")
    with Session(seeded) as db, db.begin():
        session = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token)))
        assert session
        if change == "idle":
            session.last_seen = now() - timedelta(hours=1)
        elif change == "absolute":
            session.expires_at = now() - timedelta(seconds=1)
        elif change == "revoked":
            session.revoked = True
        elif change == "suspended":
            user = db.get(User, fixture_id("student-a"))
            assert user
            user.status = "suspended"
        else:
            grant = db.get(RoleGrant, fixture_id("grant:student-a:department-a"))
            assert grant
            grant.status = "revoked"
    if change == "grant":
        assert client.get("/api/v1/org-units").json() == []
    else:
        assert client.get("/api/v1/me").status_code == 401


def test_rls_and_connection_reuse(client: TestClient, settings: Settings) -> None:
    # Pool size one guarantees the second actor reuses the first actor's connection.
    engine = create_engine(settings.database_url.get_secret_value(), pool_size=1, max_overflow=0)
    for account, expected in ((None, 0), ("student-a", 1), (None, 0), ("student-b", 1), (None, 0)):
        with Session(engine) as db, db.begin():
            if account:
                context(db, user_id=str(fixture_id(account)), mfa="false")
            rows = list(db.scalars(select(OrgUnit)))
            assert len(rows) == expected
            if account:
                assert rows[0].id == fixture_id(
                    "department-a" if account == "student-a" else "department-b"
                )
            else:
                assert list(db.scalars(select(User))) == []
                assert list(db.scalars(select(RoleGrant))) == []
    engine.dispose()
    with Session(client.app.state.auth_engine) as db:
        assert list(db.scalars(select(User))) == []
        assert list(db.scalars(select(LoginSession))) == []
        assert list(db.scalars(select(Verification))) == []
        with pytest.raises(DBAPIError):
            db.execute(select(RoleGrant))


def test_runtime_roles_and_extension(client: TestClient, seeded: Engine) -> None:
    with Session(seeded) as db:
        assert db.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        rows = db.execute(
            text(
                "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname IN ('advisory_app','advisory_auth')"
            )
        ).all()
        assert len(rows) == 2 and all(not r[1] and not r[2] for r in rows)
        policies = db.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname IN ('users','sessions','verifications',"
                "'role_grants','institutions','org_units')"
            )
        ).all()
        assert len(policies) == 6 and all(r[0] and r[1] for r in policies)


@pytest.mark.parametrize("invalid", ["cross-institution", "cycle", "timezone", "parent-type"])
def test_hierarchy_constraints(seeded: Engine, invalid: str) -> None:
    with Session(seeded) as db:
        with pytest.raises(IntegrityError):
            if invalid == "parent-type":
                org = db.get(OrgUnit, fixture_id("college"))
                assert org
                org.kind = "department"
            else:
                db.add(
                    OrgUnit(
                        id=uuid4(),
                        institution_id=fixture_id("synthetic"),
                        code=str(uuid4()),
                        name="Synthetic invalid",
                        kind="college" if invalid == "cycle" else "department",
                        parent_id=fixture_id("other-college")
                        if invalid == "cross-institution"
                        else fixture_id("college"),
                        timezone="Invalid/Zone" if invalid == "timezone" else "UTC",
                    )
                )
            db.flush()


def test_seed_is_idempotent(seeded: Engine) -> None:
    with Session(seeded) as db, db.begin():
        before = len(list(db.scalars(select(User))))
        seed(db)
        assert len(list(db.scalars(select(User)))) == before
        assignment = db.scalar(
            select(AdvisorAssignment).where(
                AdvisorAssignment.student_membership_id
                == fixture_id("grant:student-a:department-a"),
                AdvisorAssignment.ended_at.is_(None),
            )
        )
        assert assignment is not None
        assignment.ended_at = now()
        db.flush()
        count = len(list(db.scalars(select(AdvisorAssignment))))
        seed(db)
        assert len(list(db.scalars(select(AdvisorAssignment)))) == count
        assert not db.scalar(
            select(AdvisorAssignment).where(
                AdvisorAssignment.student_membership_id == assignment.student_membership_id,
                AdvisorAssignment.ended_at.is_(None),
            )
        )


@pytest.mark.parametrize(
    "url,env,confirmation",
    [
        ("postgresql+psycopg://advisory_migrator@remote/advisory_test", "test", "advisory_test"),
        ("postgresql+psycopg://advisory_migrator@localhost/production", "test", "production"),
        (
            "postgresql+psycopg://advisory_migrator@localhost/advisory_test",
            "production",
            "advisory_test",
        ),
        ("postgresql+psycopg://advisory_migrator@localhost/advisory_dev", "development", ""),
    ],
)
def test_reset_guard(url: str, env: str, confirmation: str) -> None:
    with pytest.raises(ValueError):
        disposable_url(url, env, confirmation)


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_env": "production"},
        {"auth_mode": "oidc"},
        {"identity_signing_key": "short"},
        {"web_origin": "http://external.test"},
        {"inference_provider": "vllm"},
    ],
)
def test_unsafe_configuration(settings: Settings, overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({**settings.model_dump(), **overrides})


@pytest.mark.parametrize(
    "claim,value",
    [
        ("iss", "wrong"),
        ("aud", "wrong"),
        ("exp", 1),
        ("sub", ""),
        ("email_verified", "true"),
        ("amr", "mfa"),
    ],
)
def test_identity_validation(settings: Settings, claim: str, value: object) -> None:
    provider = MockIdentityProvider(settings)
    valid = provider.issue("stable-subject", True)
    payload = provider.validate(valid)
    payload[claim] = value
    bad = jwt.encode(payload, settings.identity_signing_key.get_secret_value(), algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        provider.validate(bad)
    with pytest.raises(jwt.InvalidTokenError):
        provider.validate(valid + "invalid")
    del payload["exp"]
    with pytest.raises(jwt.InvalidTokenError):
        provider.validate(
            jwt.encode(payload, settings.identity_signing_key.get_secret_value(), algorithm="HS256")
        )


def test_recent_auth_hook(settings: Settings) -> None:
    session = LoginSession(auth_time=now())
    require_recent(session, settings)
    session.auth_time = now() - timedelta(hours=1)
    with pytest.raises(ApiError) as exc:
        require_recent(session, settings)
    assert exc.value.code == "RECENT_AUTH_REQUIRED"


def test_duplicate_registration_and_redacted_errors(client: TestClient) -> None:
    response = post(
        client, "auth/register", {"email": "student-a@advisory.test", "name": "Synthetic"}
    )
    assert response.status_code == 409
    assert "psycopg" not in response.text and "INSERT" not in response.text
    response = post(
        client, "auth/register", {"email": "private-content@example.com", "name": "Synthetic"}
    )
    assert response.status_code == 422
    assert "private-content" not in response.text
    assert set(client.get("/api/v1/missing").json()) == {
        "code",
        "message",
        "field_errors",
        "correlation_id",
    }


def test_identity_is_immutable_and_epoch_changes(seeded: Engine) -> None:
    with Session(seeded) as db:
        user = db.get(User, fixture_id("student-a"))
        assert user
        user.subject = "different-subject"
        with pytest.raises(IntegrityError):
            db.flush()
    with Session(seeded) as db, db.begin():
        user = db.get(User, fixture_id("student-a"))
        assert user
        before = user.grant_epoch
        grant = db.get(RoleGrant, fixture_id("grant:student-a:department-a"))
        assert grant
        grant.status = "revoked"
        db.flush()
        db.refresh(user)
        assert user.grant_epoch > before


def test_required_settings_and_safe_validation_output() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    with pytest.raises(ValidationError) as exc:
        Settings(
            _env_file=None,
            app_env="production",
            database_url="sensitive-value",
            auth_database_url="sensitive-value",
            identity_signing_key="sensitive-value",
        )
    assert "sensitive-value" not in str(exc.value)
