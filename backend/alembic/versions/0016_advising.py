"""Add private publication, retrieval and advising records without changing active records."""

from pathlib import Path

from alembic import op

revision = "0016_advising"
down_revision = "0015_schema_institution_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    directory = Path(__file__).parent
    op.execute((directory / "0016_advising_schema.sql").read_text())
    op.execute((directory / "0016_advising_policy.sql").read_text())


def downgrade() -> None:
    raise RuntimeError("Preserve evidence and conversation history; use forward migrations")
