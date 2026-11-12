from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session


def make_engine(url: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c lock_timeout=10000 -c statement_timeout=15000",
        },
    )


def context(db: Session, **values: str) -> None:
    # Context must be installed before ORM autoflush applies row policies.
    with db.no_autoflush:
        for key, value in values.items():
            db.execute(
                text("SELECT set_config(:key, :value, true)"), {"key": f"app.{key}", "value": value}
            )


@contextmanager
def transaction(engine: Engine) -> Iterator[Session]:
    with Session(engine) as db, db.begin():
        yield db


def safe_runtime_role(db: Session, expected: str) -> bool:
    row = db.execute(
        text("SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
    ).one()
    owns = db.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relowner=(SELECT oid FROM pg_roles "
            "WHERE rolname=current_user) "
            "AND c.relkind IN ('r','p'))"
        )
    )
    return row[0] == expected and not row[1] and not row[2] and not owns
