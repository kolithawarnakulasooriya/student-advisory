"""Constrain service columns and preserve identity boundaries during lifecycle changes."""

from alembic import op

revision = "0005_staff_guards"
down_revision = "0004_staff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    REVOKE UPDATE ON invitations,outbox_events FROM advisory_mail;
    GRANT UPDATE(status) ON invitations TO advisory_mail;
    GRANT UPDATE(state,attempts,available_at,last_error) ON outbox_events TO advisory_mail;
    REVOKE UPDATE ON invitations,platform_grants FROM advisory_app;
    GRANT UPDATE(status,version,nonce,inviter_id,token_hash,expires_at,accepted_by)
      ON invitations TO advisory_app;
    GRANT UPDATE(status,version) ON platform_grants TO advisory_app;
    GRANT UPDATE ON role_grants,platform_grants TO advisory_policy;
    DROP POLICY audit_append ON audit_events;
    CREATE POLICY audit_append ON audit_events FOR INSERT TO advisory_app
      WITH CHECK(actor_id IS NULL OR actor_id=public.actor_id());
    CREATE FUNCTION grant_binding_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
     IF NEW.id<>OLD.id OR NEW.user_id<>OLD.user_id OR NEW.role<>OLD.role
      OR NEW.org_unit_id<>OLD.org_unit_id OR NEW.institution_id<>OLD.institution_id THEN
      RAISE EXCEPTION 'Grant identity is immutable' USING ERRCODE='23514';
     END IF;
     RETURN NEW;
    END $$;
    CREATE TRIGGER grant_binding BEFORE UPDATE ON role_grants
      FOR EACH ROW EXECUTE FUNCTION grant_binding_immutable();
    CREATE OR REPLACE FUNCTION update_account(uid uuid,new_status text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    BEGIN
     IF NOT public.platform_admin() OR NOT public.current_session_live()
       OR new_status NOT IN ('active','suspended') THEN RAISE insufficient_privilege; END IF;
     UPDATE public.users SET status=new_status WHERE id=uid;
     IF new_status='suspended' THEN
      UPDATE public.role_grants SET status='suspended',version=version+1
       WHERE user_id=uid AND status='active';
      UPDATE public.platform_grants SET status='suspended',version=version+1
       WHERE user_id=uid AND status='active';
      UPDATE public.sessions SET revoked=true WHERE user_id=uid;
     END IF;
    END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("Preserve lifecycle history; use forward migrations")
