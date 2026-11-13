"""Avoid recursive worker policies when updating an index build."""

from alembic import op

revision = "0018_index_policy"
down_revision = "0017_advising_guards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION rag_version_publishable(vid uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path=pg_catalog,public AS $$
     SELECT EXISTS(SELECT 1 FROM public.source_versions v WHERE v.id=vid
     AND public.rag_publish_source(v.source_id))
    $$;
    ALTER FUNCTION rag_version_publishable(uuid) OWNER TO advisory_policy;
    REVOKE ALL ON FUNCTION rag_version_publishable(uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION rag_version_publishable(uuid) TO advisory_app,advisory_rag;
    DROP POLICY builds ON index_builds;
    CREATE POLICY builds ON index_builds TO advisory_app,advisory_rag
     USING(rag_live() AND rag_build(id,false))
     WITH CHECK(rag_live() AND rag_version_publishable(source_version_id));
    ALTER TABLE embedding_configs ADD CHECK(dimension=768);
    """)


def downgrade() -> None:
    raise RuntimeError("Preserve scoped index policies; use forward migrations")
