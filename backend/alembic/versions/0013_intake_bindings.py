"""Bind active schemas to existing immutable snapshots."""

from alembic import op

revision = "0013_intake_bindings"
down_revision = "0012_student_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "active_onboarding_schema",
        "onboarding_configs",
        "onboarding_schemas",
        ["active_schema_id"],
        ["id"],
    )



def downgrade() -> None:
    raise RuntimeError("Preserve intake records; use forward migrations")
