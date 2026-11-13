"""Keep administrative delegation history separate from organization metadata history."""

from alembic import op

revision = "0011_organization_history"
down_revision = "0010_organization_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DROP POLICY organization_audit_read ON audit_events;
    CREATE POLICY organization_audit_read ON audit_events FOR SELECT TO advisory_app
     USING(action LIKE 'organization.%' AND action NOT LIKE 'organization.grant.%'
       AND public.can_manage_org(institution_id,org_unit_id));
    """)


def downgrade() -> None:
    raise RuntimeError("Preserve organization audit boundaries; use forward migrations")
