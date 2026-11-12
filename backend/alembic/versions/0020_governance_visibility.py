"""Permit creators to return new releases without exposing drafts to record readers."""

from alembic import op

revision = "0020_governance_visibility"
down_revision = "0019_knowledge_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DROP POLICY governance_read ON governance_versions;
    CREATE POLICY governance_read ON governance_versions FOR SELECT TO advisory_app,advisory_rag
    USING(rag_live() AND (rag_cap(CASE WHEN kind='prompt' THEN 'prompt.manage'
    ELSE 'rules.manage' END,org_unit_id) OR rag_governance_read(id)));
    DROP POLICY rag_versions ON source_versions;
    CREATE POLICY rag_versions ON source_versions FOR SELECT TO advisory_rag
    USING(rag_worker_live() AND (rag_publish_source(source_id) OR EXISTS(
    SELECT 1 FROM advising_jobs j WHERE j.id=nullif(current_setting('app.rag_job',true),'')::uuid
    AND rag_published(source_versions.id,j.student_membership_id,true))));
    """)


def downgrade() -> None:
    raise RuntimeError("Preserve governance history; use forward migrations")
