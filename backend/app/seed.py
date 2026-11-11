"""Operator-only synthetic fixtures and an explicitly guarded disposable reset."""

import argparse
import os
from pathlib import Path
from uuid import UUID, uuid5

from dotenv import load_dotenv
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import Institution, OrgUnit, RoleGrant, User

NAMESPACE = UUID("20000000-0000-4000-8000-000000000001")


def fixture_id(name: str) -> UUID:
    return uuid5(NAMESPACE, name)


ACCOUNTS = {
    "student-a": ("student", "department-a", "active", True, "active"),
    "student-b": ("student", "department-b", "active", True, "active"),
    "advisor-a": ("advisor", "department-a", "active", True, "active"),
    "advisor-b": ("advisor", "department-b", "active", True, "active"),
    "secretary": ("secretary", "department-a", "active", True, "active"),
    "manager": ("manager", "department-a", "active", True, "active"),
    "platform-admin": ("platform_admin", "department-a", "active", True, "active"),
    "super-admin": ("super_admin", "department-a", "active", True, "active"),
    "multi-role": ("advisor", "department-a", "active", True, "active"),
    "pending": ("student", "department-a", "pending", True, "active"),
    "unverified": ("student", "department-a", "active", False, "active"),
    "suspended": ("student", "department-a", "active", True, "suspended"),
    "revoked": ("student", "department-a", "revoked", True, "active"),
    "other-institution": ("manager", "other-department", "active", True, "active"),
}


def seed(db: Session) -> None:
    for code in ("synthetic", "other-institution"):
        if db.get(Institution, fixture_id(code)) is None:
            db.add(Institution(id=fixture_id(code), code=code, name=f"Synthetic {code}"))
    db.flush()
    for code, kind, parent, institution in (
        ("college", "college", None, "synthetic"),
        ("other-college", "college", None, "other-institution"),
        ("department-a", "department", "college", "synthetic"),
        ("department-b", "department", "college", "synthetic"),
        ("other-department", "department", "other-college", "other-institution"),
    ):
        if db.get(OrgUnit, fixture_id(code)) is None:
            db.add(
                OrgUnit(
                    id=fixture_id(code),
                    institution_id=fixture_id(institution),
                    parent_id=fixture_id(parent) if parent else None,
                    code=code,
                    name=f"Synthetic {code.replace('-', ' ').title()}",
                    kind=kind,
                )
            )
            db.flush()
    for name, (role, org, grant_status, verified, status) in ACCOUNTS.items():
        uid = fixture_id(name)
        if db.get(User, uid) is None:
            db.add(
                User(
                    id=uid,
                    issuer="urn:advisory:synthetic",
                    subject=str(uid),
                    email=f"{name}@advisory.test",
                    name=f"Synthetic {name}",
                    verified=verified,
                    status=status,
                )
            )
            db.flush()
        institution = "other-institution" if name == "other-institution" else "synthetic"
        grant_id = fixture_id(f"grant:{name}:{org}")
        if db.get(RoleGrant, grant_id) is None:
            db.add(
                RoleGrant(
                    id=grant_id,
                    user_id=uid,
                    institution_id=fixture_id(institution),
                    org_unit_id=fixture_id(org),
                    role=role,
                    status=grant_status,
                )
            )
    for name in ("multi-role", "super-admin"):
        gid = fixture_id(f"grant:{name}:department-b")
        if db.get(RoleGrant, gid) is None:
            db.add(
                RoleGrant(
                    id=gid,
                    user_id=fixture_id(name),
                    institution_id=fixture_id("synthetic"),
                    org_unit_id=fixture_id("department-b"),
                    role="manager" if name == "multi-role" else "super_admin",
                )
            )
    db.flush()


def disposable_url(url: str, app_env: str, confirmation: str) -> str:
    parsed = make_url(url)
    if (
        app_env not in {"development", "test"}
        or parsed.host not in {"127.0.0.1", "localhost"}
        or parsed.database not in {"advisory_dev", "advisory_test"}
        or confirmation != parsed.database
        or parsed.username != "advisory_migrator"
    ):
        raise ValueError(
            "Refusing operation: require loopback disposable database and confirmation"
        )
    return url


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seed", "reset"])
    parser.add_argument("--confirm-database", required=True)
    args = parser.parse_args()
    url = disposable_url(
        os.environ["MIGRATION_DATABASE_URL"],
        os.getenv("APP_ENV", "development"),
        args.confirm_database,
    )
    engine = create_engine(url, hide_parameters=True)
    with Session(engine) as db, db.begin():
        if args.action == "reset":
            # Only the known fixture schema; retain migrations and vector extension.
            db.execute(
                text(
                    "TRUNCATE verifications, sessions, role_grants, users, "
                    "org_units, institutions CASCADE"
                )
            )
        seed(db)
        count = len(list(db.scalars(select(User.id))))
    print(f"Synthetic seed ready: {count} identities; no real records.")


if __name__ == "__main__":
    main()
