"""Bind worker artifacts and metadata events to the currently leased job."""

from alembic import op

revision = "0022_worker_commit_guards"
down_revision = "0021_index_retry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DROP POLICY answers ON validated_answers;
    CREATE POLICY answers_read ON validated_answers FOR SELECT TO advisory_app,advisory_rag
    USING(rag_live() AND rag_conversation(conversation_id));
    CREATE POLICY answers_insert ON validated_answers FOR INSERT TO advisory_rag
    WITH CHECK(rag_worker_live() AND job_id=nullif(current_setting('app.rag_job',true),'')::uuid
    AND EXISTS(SELECT 1 FROM advising_jobs j WHERE j.id=job_id AND j.kind='answer'
    AND j.conversation_id=validated_answers.conversation_id
    AND j.message_id=validated_answers.message_id));
    DROP POLICY drafts ON advisor_drafts;
    CREATE POLICY drafts_read ON advisor_drafts FOR SELECT TO advisory_app,advisory_rag
    USING(rag_live() AND rag_advisor(conversation_id));
    CREATE POLICY drafts_insert ON advisor_drafts FOR INSERT TO advisory_rag
    WITH CHECK(rag_worker_live() AND job_id=nullif(current_setting('app.rag_job',true),'')::uuid
    AND actor_id=public.actor_id() AND rag_advisor(conversation_id)
    AND EXISTS(SELECT 1 FROM advising_jobs j WHERE j.id=job_id AND j.kind='draft'
    AND j.conversation_id=advisor_drafts.conversation_id));
    CREATE FUNCTION rag_event_target(iid uuid,scope uuid,event text,aggregate uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    SELECT EXISTS(SELECT 1 FROM public.advising_jobs j
    WHERE j.id=nullif(current_setting('app.rag_job',true),'')::uuid AND (
    (j.kind='index' AND event='source.indexed' AND EXISTS(SELECT 1 FROM public.index_builds b
    JOIN public.source_versions v ON v.id=b.source_version_id
    JOIN public.sources s ON s.id=v.source_id
    WHERE b.id=j.target_id AND s.id=aggregate AND s.institution_id=iid
    AND s.org_unit_id IS NOT DISTINCT FROM scope)) OR
    (j.kind='evaluation' AND event='governance.evaluated' AND EXISTS(
    SELECT 1 FROM public.governance_versions g WHERE g.id=j.target_id AND g.id=aggregate
    AND g.institution_id=iid AND g.org_unit_id IS NOT DISTINCT FROM scope)) OR
    (j.kind IN ('answer','draft') AND event=CASE WHEN j.kind='draft' THEN 'advisor.draft.completed'
    ELSE 'generation.completed' END AND aggregate=j.message_id AND EXISTS(
    SELECT 1 FROM public.conversations c WHERE c.id=j.conversation_id
    AND c.institution_id=iid AND c.org_unit_id=scope))))
    $$;
    ALTER FUNCTION rag_event_target(uuid,uuid,text,uuid) OWNER TO advisory_policy;
    REVOKE ALL ON FUNCTION rag_event_target(uuid,uuid,text,uuid) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION rag_event_target(uuid,uuid,text,uuid) TO advisory_rag;
    DROP POLICY rag_events ON outbox_events;
    CREATE POLICY rag_events ON outbox_events FOR INSERT TO advisory_rag
    WITH CHECK(rag_worker_live() AND actor_id=public.actor_id()
    AND rag_event_target(institution_id,org_unit_id,event_type,aggregate_id));
    """)


def downgrade() -> None:
    raise RuntimeError("Preserve worker artifact guards; use forward migrations")
