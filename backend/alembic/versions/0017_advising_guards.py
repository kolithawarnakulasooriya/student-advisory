"""Narrow published views and worker contexts without widening intake history."""

from pathlib import Path

from alembic import op

revision = "0017_advising_guards"
down_revision = "0016_advising"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(Path(__file__).with_suffix(".sql").read_text())


def downgrade() -> None:
    raise RuntimeError("Preserve publication privacy; use forward migrations")
