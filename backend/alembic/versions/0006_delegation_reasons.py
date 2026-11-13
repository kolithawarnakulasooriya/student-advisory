"""Preserve operational rationale references and enforce delegated appointment ceilings."""

from pathlib import Path

from alembic import op

revision = "0006_delegation_reasons"
down_revision = "0005_staff_guards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute((Path(__file__).parent / "0006_delegation_reasons.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("Retain operational history")
