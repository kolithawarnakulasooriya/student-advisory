"""Add organization administration without promoting existing grants."""

from pathlib import Path

from alembic import op

revision = "0010_organization_admin"
down_revision = "0009_manager_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute((Path(__file__).with_suffix(".sql")).read_text())


def downgrade() -> None:
    raise RuntimeError("Preserve organization history; use forward migrations")
