import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.seed import disposable_url, seed

MIGRATION = os.getenv(
    "TEST_MIGRATION_DATABASE_URL",
    "postgresql+psycopg://advisory_migrator:local-migrations-only@127.0.0.1:5432/advisory_test",
)


@pytest.fixture(scope="session")
def owner() -> Iterator[Engine]:
    # No test may migrate or truncate a database outside the explicit disposable allowlist.
    disposable_url(MIGRATION, "test", "advisory_test")
    bootstrap = create_engine(
        MIGRATION.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT"
    )
    with bootstrap.connect() as conn:
        if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname='advisory_test'")):
            conn.execute(text("CREATE DATABASE advisory_test"))
    bootstrap.dispose()
    env = {**os.environ, "MIGRATION_DATABASE_URL": MIGRATION}
    subprocess.run(
        ["alembic", "upgrade", "head"], cwd=Path(__file__).resolve().parents[1], env=env, check=True
    )
    engine = create_engine(MIGRATION)
    yield engine
    engine.dispose()


@pytest.fixture()
def seeded(owner: Engine) -> Engine:
    with Session(owner) as db, db.begin():
        db.execute(
            text(
                "TRUNCATE operational_reasons, audit_events, idempotency_records, "
                "outbox_events, verifications, "
                "sessions, role_grants, users, org_units, "
                "institutions CASCADE"
            )
        )
        db.execute(text("UPDATE platform_control SET bootstrap_completed=false WHERE id=1"))
        seed(db)
    return owner


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr(
            "postgresql+psycopg://advisory_app:local-app-only@127.0.0.1:5432/advisory_test"
        ),
        auth_database_url=SecretStr(
            "postgresql+psycopg://advisory_auth:local-auth-only@127.0.0.1:5432/advisory_test"
        ),
        identity_signing_key=SecretStr("synthetic-test-signing-key-at-least-32"),
    )


@pytest.fixture()
def client(seeded: Engine, settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app, base_url="http://localhost:3000") as client:
        yield client
    app.state.engine.dispose()
    app.state.auth_engine.dispose()


def post(client: TestClient, path: str, data: dict[str, object] | None = None):
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    return client.post(
        "/api/v1/" + path,
        json=data,
        headers={"Origin": "http://localhost:3000", "X-CSRF-Token": csrf},
    )


def login(client: TestClient, account: str = "student-a", mfa: bool = False) -> None:
    response = post(client, "auth/sign-in", {"email": f"{account}@advisory.test"})
    assert response.status_code == 200, response.text
    if mfa:
        assert post(client, "auth/simulator/step-up").status_code == 200
