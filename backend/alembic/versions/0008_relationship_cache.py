"""Invalidate both sides' permission caches when a relationship changes."""

from alembic import op

revision = "0008_relationship_cache"
down_revision = "0007_membership_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION assignment_epoch_changed() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    BEGIN
     UPDATE public.student_memberships SET relationship_epoch=relationship_epoch+1,version=version+1
      WHERE id=NEW.student_membership_id;
     UPDATE public.users SET grant_epoch=grant_epoch+1 WHERE id IN (
       SELECT user_id FROM public.student_memberships WHERE id=NEW.student_membership_id
       UNION SELECT user_id FROM public.role_grants WHERE id=NEW.advisor_grant_id);
     RETURN NULL;
    END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("Do not weaken relationship cache invalidation")
