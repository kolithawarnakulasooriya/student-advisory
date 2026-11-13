CREATE FUNCTION rag_intake_source(sid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.sources s WHERE s.id=sid AND
 public.source_permission(s.institution_id,s.org_unit_id,s.student_membership_id,s.visibility,false))
$$;
DROP POLICY version_read ON source_versions;
CREATE POLICY version_read ON source_versions FOR SELECT TO advisory_app
 USING(public.rag_intake_source(source_id) OR public.rag_visible_version(id));
CREATE OR REPLACE FUNCTION rag_conversation(cid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.conversations c WHERE c.id=cid
 AND public.can_student(c.student_membership_id) AND public.rag_job_member(c.student_membership_id))
$$;
CREATE OR REPLACE FUNCTION rag_advisor(cid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.rag_conversation(cid) AND EXISTS(SELECT 1 FROM public.conversations c
 WHERE c.id=cid AND public.profile_reviewer(c.student_membership_id))
$$;
CREATE OR REPLACE FUNCTION rag_owner(cid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.rag_conversation(cid) AND EXISTS(SELECT 1 FROM public.conversations c
 WHERE c.id=cid AND public.profile_owner(c.student_membership_id))
$$;
CREATE FUNCTION rag_governance_read(gid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.governance_versions g WHERE g.id=gid AND
 (public.rag_cap(CASE WHEN g.kind='prompt' THEN 'prompt.manage' ELSE 'rules.manage' END,g.org_unit_id)
 OR (g.id=(SELECT a.governance_id FROM public.governance_activations a
 WHERE a.institution_id=g.institution_id AND a.kind=g.kind
 AND a.org_unit_id IS NOT DISTINCT FROM g.org_unit_id ORDER BY a.version DESC,a.created_at DESC LIMIT 1)
 AND EXISTS(SELECT 1 FROM public.student_memberships m WHERE m.institution_id=g.institution_id
 AND (g.org_unit_id IS NULL OR m.org_unit_id=g.org_unit_id)
 AND public.can_student(m.id) AND public.rag_job_member(m.id)))))
$$;
DROP POLICY governance ON governance_versions;
CREATE POLICY governance_read ON governance_versions FOR SELECT TO advisory_app,advisory_rag
 USING(rag_live() AND rag_governance_read(id));
CREATE POLICY governance_insert ON governance_versions FOR INSERT TO advisory_app WITH CHECK(
 rag_live() AND actor_id=public.actor_id() AND
 rag_cap(CASE WHEN kind='prompt' THEN 'prompt.manage' ELSE 'rules.manage' END,org_unit_id)
 AND (org_unit_id IS NULL OR EXISTS(SELECT 1 FROM org_units o WHERE o.id=governance_versions.org_unit_id
 AND o.institution_id=governance_versions.institution_id)));
DROP POLICY activations ON governance_activations;
CREATE POLICY activations_read ON governance_activations FOR SELECT TO advisory_app,advisory_rag
 USING(rag_live() AND rag_governance_read(governance_id));
CREATE POLICY activations_insert ON governance_activations FOR INSERT TO advisory_app WITH CHECK(
 rag_live() AND actor_id=public.actor_id() AND rag_cap(CASE WHEN kind='prompt' THEN 'prompt.manage' ELSE 'rules.manage' END,org_unit_id));
DROP POLICY configs ON embedding_configs;
CREATE POLICY configs_read ON embedding_configs FOR SELECT TO advisory_app,advisory_rag USING(rag_live());
CREATE POLICY configs_insert ON embedding_configs FOR INSERT TO advisory_app WITH CHECK(rag_live() AND
 (rag_cap('prompt.manage',NULL) OR EXISTS(SELECT 1 FROM role_grants g WHERE g.user_id=actor_id() AND rag_cap('source.publish',g.org_unit_id))));
DROP POLICY publications ON source_publications;
CREATE POLICY publications_read ON source_publications FOR SELECT TO advisory_app,advisory_rag USING(rag_live() AND
 (rag_publish_source(id) OR rag_intake_source(id) OR EXISTS(SELECT 1 FROM index_builds b WHERE b.id=build_id AND
 (rag_visible_version(b.source_version_id) OR (session_user='advisory_rag' AND EXISTS(
 SELECT 1 FROM advising_jobs j WHERE j.id=nullif(current_setting('app.rag_job',true),'')::uuid
 AND rag_published(b.source_version_id,j.student_membership_id,true)))))));
CREATE POLICY publications_insert ON source_publications FOR INSERT TO advisory_app WITH CHECK(rag_live() AND rag_publish_source(id));
CREATE POLICY publications_update ON source_publications FOR UPDATE TO advisory_app USING(rag_live() AND rag_publish_source(id))
 WITH CHECK(rag_live() AND rag_publish_source(id));
CREATE FUNCTION rag_binding_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 IF TG_TABLE_NAME='source_publications' THEN
  IF NOT EXISTS(SELECT 1 FROM public.index_builds b JOIN public.source_versions v ON v.id=b.source_version_id
   WHERE b.id=NEW.build_id AND v.source_id=NEW.id AND b.state='ready') THEN
   RAISE EXCEPTION 'Invalid publication binding' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='governance_activations' THEN
  IF NOT EXISTS(SELECT 1 FROM public.governance_versions g WHERE g.id=NEW.governance_id
   AND g.institution_id=NEW.institution_id AND g.org_unit_id IS NOT DISTINCT FROM NEW.org_unit_id AND g.kind=NEW.kind) THEN
   RAISE EXCEPTION 'Invalid governance binding' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='advising_jobs' AND NEW.kind IN ('answer','draft') THEN
  IF NOT EXISTS(SELECT 1 FROM public.conversations c JOIN public.student_messages m ON m.conversation_id=c.id
   WHERE c.id=NEW.conversation_id AND c.student_membership_id=NEW.student_membership_id
   AND m.id=NEW.message_id AND m.id=NEW.target_id) THEN
   RAISE EXCEPTION 'Invalid advising job binding' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER publication_binding BEFORE INSERT OR UPDATE ON source_publications FOR EACH ROW EXECUTE FUNCTION rag_binding_guard();
CREATE TRIGGER activation_binding BEFORE INSERT ON governance_activations FOR EACH ROW EXECUTE FUNCTION rag_binding_guard();
CREATE TRIGGER job_binding BEFORE INSERT ON advising_jobs FOR EACH ROW EXECUTE FUNCTION rag_binding_guard();
DO $$ DECLARE f text; BEGIN
 FOREACH f IN ARRAY ARRAY['rag_intake_source(uuid)','rag_governance_read(uuid)','rag_binding_guard()'] LOOP
 EXECUTE 'ALTER FUNCTION '||f||' OWNER TO advisory_policy';
 EXECUTE 'REVOKE ALL ON FUNCTION '||f||' FROM PUBLIC';
 EXECUTE 'GRANT EXECUTE ON FUNCTION '||f||' TO advisory_app,advisory_rag';
 END LOOP;
END $$;
