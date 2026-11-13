"""Resolve knowledge scope inside the policy role, not through general worker grants."""

from alembic import op

revision = "0019_knowledge_scope"
down_revision = "0018_index_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION rag_knowledge_scope(iid uuid,writing boolean) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
     SELECT public.actor_live() AND (public.rag_cap('prompt.manage',NULL) OR EXISTS(
      SELECT 1 FROM public.role_grants g WHERE g.institution_id=iid AND g.user_id=public.actor_id()
      AND public.effective_grant(g.id)
      AND (NOT writing OR public.rag_cap('source.publish',g.org_unit_id))))
    $$;
    ALTER FUNCTION rag_knowledge_scope(uuid,boolean) OWNER TO advisory_policy;
    REVOKE ALL ON FUNCTION rag_knowledge_scope(uuid,boolean) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION rag_knowledge_scope(uuid,boolean) TO advisory_app,advisory_rag;
    DROP POLICY knowledge ON knowledge_states;
    CREATE POLICY knowledge ON knowledge_states TO advisory_app,advisory_rag
     USING(rag_live() AND rag_knowledge_scope(id,false))
     WITH CHECK(rag_live() AND rag_knowledge_scope(id,true));
    """)


def downgrade() -> None:
    raise RuntimeError("Preserve knowledge scope; use forward migrations")
