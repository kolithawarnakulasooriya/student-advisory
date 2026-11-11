from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, pool_size=5, hide_parameters=True)


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
