"""Add versioned profiles and private intake without replacing existing records."""

from pathlib import Path

from alembic import op

revision = "0012_student_intake"
down_revision = "0011_organization_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute((Path(__file__).parent / "0012_student_intake_schema.sql").read_text())
    op.execute(Path(__file__).with_suffix(".sql").read_text())


def downgrade() -> None:
    raise RuntimeError("Preserve academic/source history; use forward migrations")
