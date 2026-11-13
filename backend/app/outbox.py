"""Durable metadata references; invitation delivery is independent of source ingestion."""

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import OutboxEvent


def emit(
    db: Session,
    request: Request,
    event: str,
    obj: Any,
    *,
    deliver: bool = False,
    aggregate_id: UUID | None = None,
    aggregate_version: int | None = None,
) -> None:
    db.add(
        OutboxEvent(
            event_type=event,
            aggregate_id=aggregate_id or obj.id,
            aggregate_version=obj.version if aggregate_version is None else aggregate_version,
            institution_id=obj.institution_id,
            org_unit_id=obj.org_unit_id,
            actor_id=request.state.actor_id,
            state="pending" if deliver else "recorded",
        )
    )
