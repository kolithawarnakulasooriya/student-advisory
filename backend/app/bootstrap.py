"""One-time audited operator bootstrap. Never available as an HTTP endpoint."""

import argparse
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.models import AuditEvent, PlatformControl, PlatformGrant, User
from app.schemas import EmailInput
from app.seed import disposable_url
from app.staff_security import WORKFLOW_LOCK


def bootstrap(db: Session, email: str) -> PlatformGrant:
    db.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": WORKFLOW_LOCK})
    control = db.get(PlatformControl, 1)
    if (
        control is None
        or control.bootstrap_completed
        or db.scalar(select(PlatformGrant.id).limit(1))
    ):
        raise ValueError("Bootstrap is disabled after its first successful appointment")
    user = db.scalar(select(User).where(User.email == EmailInput(email=email).email))
    if user is None or not user.verified or user.status != "active":
        raise ValueError("Bootstrap requires an existing verified active synthetic identity")
    grant = PlatformGrant(user_id=user.id)
    db.add(grant)
    db.flush()
    control.bootstrap_completed = True
    db.add(
        AuditEvent(
            actor_id=None,
            action="platform.bootstrap",
            object_type="platform_grant",
            object_id=str(grant.id),
            result="allow",
            reason_code="OPERATOR_BOOTSTRAP",
            correlation_id=str(uuid4()),
        )
    )
    return grant


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--confirm-database", required=True)
    args = parser.parse_args()
    url = disposable_url(
        os.environ["MIGRATION_DATABASE_URL"],
        os.getenv("APP_ENV", "development"),
        args.confirm_database,
    )
    with Session(create_engine(url, hide_parameters=True)) as db, db.begin():
        bootstrap(db, args.email)
    print("Audited synthetic platform bootstrap complete; bootstrap is now disabled.")


if __name__ == "__main__":
    main()
