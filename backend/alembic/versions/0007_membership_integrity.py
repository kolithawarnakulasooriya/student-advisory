"""Prevent cross-scope membership bindings and reconcile pending invitations atomically."""

from alembic import op

revision = "0007_membership_integrity"
down_revision = "0006_delegation_reasons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE role_grants ADD CONSTRAINT grant_membership_identity
      UNIQUE(id,user_id,institution_id,org_unit_id);
    ALTER TABLE student_memberships ADD CONSTRAINT student_grant_identity
      FOREIGN KEY(grant_id,user_id,institution_id,org_unit_id)
      REFERENCES role_grants(id,user_id,institution_id,org_unit_id);
    ALTER TABLE membership_requests ADD FOREIGN KEY(institution_id,org_unit_id)
      REFERENCES org_units(institution_id,id);
    ALTER TABLE invitations ADD FOREIGN KEY(institution_id,org_unit_id)
      REFERENCES org_units(institution_id,id);
    GRANT UPDATE ON membership_requests TO advisory_policy;
    CREATE OR REPLACE FUNCTION accept_invited_grant(iid uuid) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    DECLARE inv public.invitations; gid uuid; current_status text;
    BEGIN
     SELECT * INTO inv FROM public.invitations WHERE id=iid;
     IF NOT FOUND OR NOT public.accepting_scope(inv.org_unit_id)
     OR inv.token_hash IS DISTINCT FROM current_setting('app.invite_hash',true) THEN
       RAISE insufficient_privilege;
     END IF;
     SELECT id,status INTO gid,current_status FROM public.role_grants
      WHERE user_id=public.actor_id()
      AND org_unit_id=inv.org_unit_id AND role=inv.role
      AND status IN ('active','pending','invited','suspended');
     IF gid IS NOT NULL THEN
      IF current_status NOT IN ('pending','invited') THEN
       RAISE EXCEPTION 'Membership already exists' USING ERRCODE='23505';
      END IF;
      UPDATE public.role_grants SET status='active',capabilities=inv.capabilities,version=version+1
       WHERE id=gid;
     ELSE
      gid:=gen_random_uuid();
      INSERT INTO public.role_grants(id,user_id,institution_id,org_unit_id,role,status,
       capabilities,ceiling,version) VALUES(gid,public.actor_id(),inv.institution_id,
       inv.org_unit_id,inv.role,'active',inv.capabilities,'advisor',1);
     END IF;
     UPDATE public.membership_requests SET status='approved',decided_by=inv.inviter_id,
      decision_reason='Activated through verified invitation acceptance',version=version+1
      WHERE user_id=public.actor_id() AND org_unit_id=inv.org_unit_id
      AND requested_role=inv.role AND status='pending';
     PERFORM set_config('app.accepting',gid::text,true);
     RETURN gid;
    END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("Preserve membership identities")
