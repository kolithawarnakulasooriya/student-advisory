"""Allow authorized publishers to requeue failed, immutable-version index attempts."""

from alembic import op

revision = "0021_index_retry"
down_revision = "0020_governance_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT UPDATE(state,error_code) ON index_builds TO advisory_app;")


def downgrade() -> None:
    raise RuntimeError("Preserve index attempts; use forward migrations")
