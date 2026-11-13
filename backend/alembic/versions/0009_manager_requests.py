"""Manager self-service requests route exclusively to platform super admins (ID-03)."""

from pathlib import Path

from alembic import op

revision = "0009_manager_requests"
down_revision = "0008_relationship_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute((Path(__file__).parent / "0009_manager_requests.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("Keep manager-request approval restricted")
