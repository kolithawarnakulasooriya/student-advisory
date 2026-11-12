"""Qualify schema institution checks against the inserted snapshot."""

from alembic import op

revision = "0015_schema_institution_guard"
down_revision = "0014_intake_guards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DROP POLICY schema_insert ON onboarding_schemas;
    CREATE POLICY schema_insert ON onboarding_schemas FOR INSERT TO advisory_app WITH CHECK(
     intake_cap('profile.configure',org_unit_id) AND author_id=actor_id() AND EXISTS(
      SELECT 1 FROM org_units o WHERE o.id=onboarding_schemas.org_unit_id
      AND o.institution_id=onboarding_schemas.institution_id AND o.kind='department'));
    """)


def downgrade() -> None:
    raise RuntimeError("Preserve schema institution boundaries; use forward migrations")
