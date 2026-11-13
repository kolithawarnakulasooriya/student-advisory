DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='advisory_rag') THEN
 CREATE ROLE advisory_rag LOGIN PASSWORD 'local-rag-only' NOSUPERUSER NOBYPASSRLS;
 END IF;
END $$;
GRANT USAGE ON SCHEMA public TO advisory_rag;
CREATE FUNCTION rag_cap(action text,scope uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.actor_live() AND current_setting('app.mfa',true)='true' AND
 (scope IS NULL OR EXISTS(SELECT 1 FROM public.org_units o WHERE o.id=scope AND o.status='active'
 AND (o.kind='college' OR public.org_active(scope)))) AND
 ((public.platform_admin() AND nullif(current_setting('app.purpose',true),'') IS NOT NULL) OR
 (scope IS NOT NULL AND action<>'prompt.manage' AND EXISTS(
 SELECT 1 FROM public.role_grants g WHERE g.user_id=public.actor_id() AND g.org_unit_id=scope
 AND public.effective_grant(g.id) AND (g.role='manager' OR
 (g.role='platform_admin' AND action=ANY(g.capabilities))))))
 AND action IN ('source.publish','rules.manage','prompt.manage')
$$;
CREATE FUNCTION rag_staff(mid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.can_student(mid) AND (public.profile_reviewer(mid) OR EXISTS(
 SELECT 1 FROM public.student_memberships m WHERE m.id=mid AND public.can_action('student.read',m.org_unit_id)))
$$;
CREATE FUNCTION rag_conversation(cid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.conversations c WHERE c.id=cid AND public.can_student(c.student_membership_id))
$$;
CREATE FUNCTION rag_advisor(cid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.conversations c WHERE c.id=cid AND public.profile_reviewer(c.student_membership_id))
$$;
CREATE FUNCTION rag_owner(cid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.conversations c WHERE c.id=cid AND public.profile_owner(c.student_membership_id))
$$;
CREATE FUNCTION rag_worker_live() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.advising_jobs j JOIN public.users u ON u.id=j.actor_id
 WHERE j.id=nullif(current_setting('app.rag_job',true),'')::uuid AND j.actor_id=public.actor_id()
 AND j.lease_token=nullif(current_setting('app.rag_token',true),'')::uuid
 AND j.lease_until>now() AND j.state='running' AND u.status='active' AND u.verified
 AND u.grant_epoch=j.grant_epoch)
$$;
CREATE FUNCTION rag_live() RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT CASE WHEN session_user='advisory_rag' THEN public.rag_worker_live()
 ELSE public.actor_live() AND public.current_session_live() END
$$;
CREATE FUNCTION rag_job_member(mid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT session_user<>'advisory_rag' OR EXISTS(SELECT 1 FROM public.advising_jobs j
 WHERE j.id=nullif(current_setting('app.rag_job',true),'')::uuid AND j.student_membership_id=mid)
$$;
CREATE FUNCTION rag_publish_source(sid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.sources s WHERE s.id=sid AND NOT s.archived
 AND public.source_permission(s.institution_id,s.org_unit_id,s.student_membership_id,s.visibility,false)
 AND public.rag_cap('source.publish',s.org_unit_id))
$$;
CREATE FUNCTION rag_published(vid uuid,mid uuid,applicability boolean DEFAULT true) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT public.can_student(mid) AND EXISTS(
 SELECT 1 FROM public.sources s JOIN public.source_versions v ON v.source_id=s.id
 JOIN public.source_publications p ON p.id=s.id JOIN public.index_builds b ON b.id=p.build_id
 JOIN public.knowledge_states k ON k.id=s.institution_id
 JOIN public.student_memberships m ON m.id=mid
 JOIN public.org_units d ON d.id=m.org_unit_id
 LEFT JOIN LATERAL (SELECT f.facts FROM public.profile_versions f WHERE f.student_membership_id=mid
 ORDER BY f.version DESC LIMIT 1) f ON true
 WHERE v.id=vid AND b.source_version_id=v.id AND p.status='published' AND b.state='ready'
 AND b.config_id=k.config_id AND NOT s.archived AND s.institution_id=m.institution_id
 AND ((s.visibility='student' AND s.student_membership_id=mid AND s.org_unit_id=m.org_unit_id)
 OR (s.visibility='department' AND s.org_unit_id=m.org_unit_id AND s.student_membership_id IS NULL)
 OR (s.visibility='college' AND s.org_unit_id=d.parent_id AND s.student_membership_id IS NULL)
 OR (s.visibility='institution' AND s.org_unit_id IS NULL AND s.student_membership_id IS NULL))
 AND (NOT applicability OR (
 (v.metadata_fields->>'program' IS NULL OR v.metadata_fields->>'program'=f.facts->'program'->>'value')
 AND (v.metadata_fields->>'track' IS NULL OR v.metadata_fields->>'track'=f.facts->'track'->>'value')
 AND (v.metadata_fields->>'catalog_start' IS NULL OR
 (CASE WHEN f.facts->'catalog_year'->>'value' ~ '^[0-9]{4}$'
 THEN (f.facts->'catalog_year'->>'value')::int END)>=(v.metadata_fields->>'catalog_start')::int)
 AND (v.metadata_fields->>'catalog_end' IS NULL OR
 (CASE WHEN f.facts->'catalog_year'->>'value' ~ '^[0-9]{4}$'
 THEN (f.facts->'catalog_year'->>'value')::int END)<=(v.metadata_fields->>'catalog_end')::int)
 AND (v.metadata_fields->>'effective_from' IS NULL OR (v.metadata_fields->>'effective_from')::date<=CURRENT_DATE)
 AND (v.metadata_fields->>'effective_until' IS NULL OR (v.metadata_fields->>'effective_until')::date>=CURRENT_DATE))))
$$;
CREATE FUNCTION rag_visible_version(vid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.student_memberships m WHERE
 public.profile_owner(m.id) AND public.rag_published(vid,m.id,true))
$$;
CREATE OR REPLACE FUNCTION source_allowed(sid uuid,writing boolean) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.sources s WHERE s.id=sid AND
 ((public.source_permission(s.institution_id,s.org_unit_id,s.student_membership_id,s.visibility,writing)
 AND (NOT writing OR NOT s.archived)) OR (NOT writing AND EXISTS(
 SELECT 1 FROM public.source_versions v WHERE v.source_id=sid AND public.rag_visible_version(v.id)))))
$$;
CREATE OR REPLACE FUNCTION version_allowed(vid uuid,writing boolean) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.source_versions v JOIN public.sources s ON s.id=v.source_id WHERE v.id=vid
 AND ((public.source_permission(s.institution_id,s.org_unit_id,s.student_membership_id,s.visibility,writing)
 AND (NOT writing OR NOT s.archived)) OR (NOT writing AND public.rag_visible_version(vid))))
$$;
DROP POLICY version_read ON source_versions;
CREATE POLICY version_read ON source_versions FOR SELECT TO advisory_app USING(public.version_allowed(id,false));

CREATE FUNCTION rag_build(bid uuid,writing boolean) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.index_builds b JOIN public.source_versions v ON v.id=b.source_version_id
 WHERE b.id=bid AND (public.rag_publish_source(v.source_id) OR (NOT writing AND
 ((session_user='advisory_rag' AND EXISTS(SELECT 1 FROM public.advising_jobs j
 WHERE j.id=nullif(current_setting('app.rag_job',true),'')::uuid
 AND public.rag_published(v.id,j.student_membership_id,true))) OR public.rag_visible_version(v.id)))))
$$;
CREATE FUNCTION rag_citation(eid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.evidence_chunks e WHERE e.id=eid AND (public.rag_build(e.build_id,false)
 OR EXISTS(SELECT 1 FROM public.validated_answers a WHERE public.rag_conversation(a.conversation_id)
 AND a.payload->'citations' @> jsonb_build_array(jsonb_build_object('id',eid::text)))))
$$;
CREATE FUNCTION rag_job_target(kind text,target uuid,cid uuid,writing boolean) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT CASE WHEN kind='index' THEN EXISTS(SELECT 1 FROM public.index_builds b
 JOIN public.source_versions v ON v.id=b.source_version_id WHERE b.id=target AND public.rag_publish_source(v.source_id))
 WHEN kind='evaluation' THEN EXISTS(SELECT 1 FROM public.governance_versions g WHERE g.id=target
 AND public.rag_cap(CASE WHEN g.kind='prompt' THEN 'prompt.manage' ELSE 'rules.manage' END,g.org_unit_id))
 WHEN kind IN ('answer','draft') THEN EXISTS(SELECT 1 FROM public.student_messages m WHERE m.id=target
 AND m.conversation_id=cid AND CASE WHEN kind='draft' THEN public.rag_advisor(cid)
 WHEN writing THEN public.rag_owner(cid) ELSE public.rag_conversation(cid) END)
 ELSE false END
$$;
CREATE FUNCTION rag_job_read(jid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.advising_jobs j WHERE j.id=jid AND (
 (j.kind='index' AND EXISTS(SELECT 1 FROM public.index_builds b JOIN public.source_versions v ON v.id=b.source_version_id
 WHERE b.id=j.target_id AND public.rag_publish_source(v.source_id))) OR
 (j.kind='evaluation' AND EXISTS(SELECT 1 FROM public.governance_versions g WHERE g.id=j.target_id
 AND public.rag_cap(CASE WHEN g.kind='prompt' THEN 'prompt.manage' ELSE 'rules.manage' END,g.org_unit_id))) OR
 (j.kind IN ('answer','draft') AND public.rag_conversation(j.conversation_id)
 AND (j.kind='answer' OR public.rag_advisor(j.conversation_id)))))
$$;

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['embedding_configs','knowledge_states','index_builds','evidence_chunks',
 'source_publications','publication_events','index_releases','governance_versions','governance_activations',
 'governance_evaluations','conversations','student_messages','advisor_guidance','staff_notes',
 'advising_jobs','validated_answers','advisor_drafts','retrieval_traces','advising_cases','case_events'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('GRANT SELECT ON %I TO advisory_app,advisory_policy',t);
 EXECUTE format('CREATE POLICY policy_reader ON %I TO advisory_policy USING(true) WITH CHECK(true)',t);
 END LOOP;
END $$;
GRANT SELECT ON embedding_configs,knowledge_states,index_builds,evidence_chunks,source_publications,
 governance_versions,governance_activations,governance_evaluations,conversations,student_messages,
 advisor_guidance,advising_jobs,validated_answers,advisor_drafts,retrieval_traces TO advisory_rag;
GRANT INSERT ON embedding_configs,knowledge_states,index_builds,source_publications,publication_events,
 index_releases,governance_versions,governance_activations,conversations,student_messages,advisor_guidance,
 staff_notes,advising_jobs,advising_cases,case_events TO advisory_app;
GRANT INSERT ON evidence_chunks,validated_answers,advisor_drafts,retrieval_traces,governance_evaluations TO advisory_rag;
GRANT UPDATE(version,config_id) ON knowledge_states TO advisory_app;
GRANT UPDATE(state,error_code,chunk_count) ON index_builds TO advisory_rag;
GRANT UPDATE(build_id,version,status,publisher_id,reason,published_at) ON source_publications TO advisory_app;
GRANT UPDATE(version,guidance_epoch) ON conversations TO advisory_app;
GRANT UPDATE(status,version) ON advising_cases TO advisory_app;
GRANT UPDATE(state,version,error_code,lease_token,lease_until,context_snapshot) ON advising_jobs TO advisory_rag;
GRANT INSERT ON outbox_events TO advisory_rag;
GRANT SELECT ON sources,source_versions,extraction_artifacts,student_memberships,profile_versions,
 academic_profiles,users,institutions,org_units TO advisory_rag;
GRANT UPDATE(version) ON knowledge_states TO advisory_policy;
CREATE POLICY configs ON embedding_configs TO advisory_app,advisory_rag USING(rag_live()) WITH CHECK(rag_live());
CREATE POLICY knowledge ON knowledge_states TO advisory_app,advisory_rag USING(rag_live() AND
 (public.can_action('org.read',NULL) OR EXISTS(SELECT 1 FROM public.student_memberships m
 WHERE m.institution_id=knowledge_states.id AND public.can_student(m.id)) OR EXISTS(
 SELECT 1 FROM public.role_grants g WHERE g.user_id=public.actor_id() AND g.institution_id=knowledge_states.id
 AND public.effective_grant(g.id)))) WITH CHECK(rag_live() AND (EXISTS(
 SELECT 1 FROM public.role_grants g WHERE g.institution_id=knowledge_states.id AND g.user_id=public.actor_id()
 AND public.rag_cap('source.publish',g.org_unit_id)) OR public.platform_admin()));
CREATE POLICY builds ON index_builds TO advisory_app,advisory_rag USING(rag_live() AND rag_build(id,false))
 WITH CHECK(rag_live() AND EXISTS(SELECT 1 FROM source_versions v WHERE v.id=source_version_id AND rag_publish_source(v.source_id)));
CREATE POLICY chunks_read ON evidence_chunks FOR SELECT TO advisory_app,advisory_rag USING(rag_live() AND
 CASE WHEN session_user='advisory_rag' THEN rag_build(build_id,false) ELSE rag_citation(id) END);
CREATE POLICY chunks_write ON evidence_chunks FOR INSERT TO advisory_rag WITH CHECK(rag_worker_live() AND rag_build(build_id,true)
 AND EXISTS(SELECT 1 FROM index_builds b WHERE b.id=build_id AND b.source_version_id=evidence_chunks.source_version_id AND b.state='building'));
CREATE POLICY publications ON source_publications TO advisory_app,advisory_rag USING(rag_live() AND
 (rag_publish_source(id) OR EXISTS(SELECT 1 FROM index_builds b WHERE b.id=build_id AND rag_visible_version(b.source_version_id))))
 WITH CHECK(rag_live() AND rag_publish_source(id));
CREATE POLICY pub_events ON publication_events TO advisory_app USING(rag_live() AND rag_publish_source(source_id))
 WITH CHECK(rag_live() AND rag_publish_source(source_id) AND actor_id=public.actor_id());
CREATE POLICY releases ON index_releases TO advisory_app USING(rag_live() AND rag_cap('prompt.manage',NULL))
 WITH CHECK(rag_live() AND rag_cap('prompt.manage',NULL) AND actor_id=public.actor_id());
CREATE POLICY governance ON governance_versions TO advisory_app,advisory_rag USING(rag_live() AND
 (rag_cap(CASE WHEN kind='prompt' THEN 'prompt.manage' ELSE 'rules.manage' END,org_unit_id)
 OR EXISTS(SELECT 1 FROM public.student_memberships m WHERE m.institution_id=governance_versions.institution_id
 AND (governance_versions.org_unit_id IS NULL OR m.org_unit_id=governance_versions.org_unit_id)
 AND public.can_student(m.id)))) WITH CHECK(rag_live() AND actor_id=public.actor_id()
 AND rag_cap(CASE WHEN kind='prompt' THEN 'prompt.manage' ELSE 'rules.manage' END,org_unit_id)
 AND (org_unit_id IS NULL OR EXISTS(SELECT 1 FROM org_units o WHERE o.id=governance_versions.org_unit_id
 AND o.institution_id=governance_versions.institution_id)));
CREATE POLICY activations ON governance_activations TO advisory_app,advisory_rag USING(rag_live()) WITH CHECK(
 rag_live() AND actor_id=public.actor_id() AND rag_cap(CASE WHEN kind='prompt' THEN 'prompt.manage' ELSE 'rules.manage' END,org_unit_id));
CREATE POLICY evaluations ON governance_evaluations TO advisory_app,advisory_rag USING(rag_live() AND EXISTS(
 SELECT 1 FROM governance_versions g WHERE g.id=governance_id)) WITH CHECK(rag_worker_live() AND EXISTS(
 SELECT 1 FROM advising_jobs j WHERE j.id=nullif(current_setting('app.rag_job',true),'')::uuid
 AND j.kind='evaluation' AND j.target_id=governance_evaluations.governance_id));
CREATE POLICY chats ON conversations TO advisory_app,advisory_rag USING(rag_live() AND can_student(student_membership_id)
 AND rag_job_member(student_membership_id)) WITH CHECK(rag_live() AND profile_owner(student_membership_id)
 AND EXISTS(SELECT 1 FROM student_memberships m WHERE m.id=student_membership_id
 AND m.institution_id=conversations.institution_id AND m.org_unit_id=conversations.org_unit_id));
CREATE POLICY chat_update ON conversations FOR UPDATE TO advisory_app USING(rag_live() AND
 (rag_owner(id) OR rag_advisor(id))) WITH CHECK(rag_live() AND (rag_owner(id) OR rag_advisor(id)));
CREATE POLICY messages ON student_messages TO advisory_app,advisory_rag USING(rag_live() AND rag_conversation(conversation_id))
 WITH CHECK(rag_live() AND rag_owner(conversation_id) AND author_id=public.actor_id());
CREATE POLICY guidance ON advisor_guidance TO advisory_app,advisory_rag USING(rag_live() AND rag_conversation(conversation_id))
 WITH CHECK(rag_live() AND rag_advisor(conversation_id) AND author_id=public.actor_id());
CREATE POLICY notes ON staff_notes TO advisory_app USING(rag_live() AND EXISTS(SELECT 1 FROM conversations c
 WHERE c.id=conversation_id AND rag_staff(c.student_membership_id))) WITH CHECK(rag_live() AND
 rag_advisor(conversation_id) AND author_id=public.actor_id());
CREATE POLICY app_jobs ON advising_jobs TO advisory_app USING(rag_live() AND rag_job_target(kind,target_id,conversation_id,false)) WITH CHECK(
 rag_live() AND actor_id=public.actor_id() AND rag_job_target(kind,target_id,conversation_id,true));
CREATE POLICY worker_jobs ON advising_jobs TO advisory_rag USING(true);
CREATE POLICY answers ON validated_answers TO advisory_app,advisory_rag USING(rag_live() AND rag_conversation(conversation_id))
 WITH CHECK(rag_worker_live() AND EXISTS(SELECT 1 FROM advising_jobs j WHERE j.id=job_id AND j.kind='answer'
 AND j.conversation_id=validated_answers.conversation_id AND j.message_id=validated_answers.message_id));
CREATE POLICY drafts ON advisor_drafts TO advisory_app,advisory_rag USING(rag_live() AND rag_advisor(conversation_id))
 WITH CHECK(rag_worker_live() AND actor_id=public.actor_id() AND rag_advisor(conversation_id));
CREATE POLICY traces ON retrieval_traces TO advisory_app,advisory_rag USING(rag_live() AND rag_job_read(job_id))
 WITH CHECK(rag_worker_live() AND job_id=nullif(current_setting('app.rag_job',true),'')::uuid);
CREATE POLICY cases ON advising_cases TO advisory_app USING(rag_live() AND can_student(student_membership_id))
 WITH CHECK(rag_live() AND can_student(student_membership_id) AND EXISTS(SELECT 1 FROM student_memberships m
 WHERE m.id=student_membership_id AND m.institution_id=advising_cases.institution_id AND m.org_unit_id=advising_cases.org_unit_id));
CREATE POLICY case_events ON case_events TO advisory_app USING(rag_live() AND EXISTS(
 SELECT 1 FROM advising_cases c WHERE c.id=case_id)) WITH CHECK(rag_live() AND actor_id=public.actor_id()
 AND EXISTS(SELECT 1 FROM advising_cases c WHERE c.id=case_id AND can_student(c.student_membership_id)));

CREATE POLICY rag_sources ON sources FOR SELECT TO advisory_rag USING(rag_worker_live() AND
 (rag_publish_source(id) OR EXISTS(SELECT 1 FROM source_versions v JOIN advising_jobs j
 ON j.id=nullif(current_setting('app.rag_job',true),'')::uuid
 WHERE v.source_id=sources.id AND rag_published(v.id,j.student_membership_id,true))));
CREATE POLICY rag_versions ON source_versions FOR SELECT TO advisory_rag USING(rag_worker_live() AND
 (EXISTS(SELECT 1 FROM index_builds b JOIN advising_jobs j ON j.target_id=b.id
 WHERE j.id=nullif(current_setting('app.rag_job',true),'')::uuid AND j.kind='index'
 AND b.source_version_id=source_versions.id AND rag_publish_source(source_id)) OR EXISTS(
 SELECT 1 FROM advising_jobs j WHERE j.id=nullif(current_setting('app.rag_job',true),'')::uuid
 AND rag_published(source_versions.id,j.student_membership_id,true))));
CREATE POLICY rag_artifacts ON extraction_artifacts FOR SELECT TO advisory_rag USING(rag_worker_live() AND EXISTS(
 SELECT 1 FROM source_versions v WHERE v.id=source_version_id));
CREATE POLICY rag_members ON student_memberships FOR SELECT TO advisory_rag USING(rag_worker_live() AND rag_job_member(id) AND can_student(id));
CREATE POLICY rag_profiles ON profile_versions FOR SELECT TO advisory_rag USING(rag_worker_live() AND rag_job_member(student_membership_id) AND can_student(student_membership_id));
CREATE POLICY rag_profile_heads ON academic_profiles FOR SELECT TO advisory_rag USING(rag_worker_live() AND rag_job_member(id) AND can_student(id));
CREATE POLICY rag_user ON users FOR SELECT TO advisory_rag USING(rag_worker_live() AND id=public.actor_id());
CREATE POLICY rag_institution ON institutions FOR SELECT TO advisory_rag USING(rag_worker_live());
CREATE POLICY rag_org ON org_units FOR SELECT TO advisory_rag USING(rag_worker_live() AND (id IN
 (SELECT org_unit_id FROM student_memberships) OR rag_cap('source.publish',id)));
CREATE POLICY rag_events ON outbox_events FOR INSERT TO advisory_rag WITH CHECK(rag_worker_live()
 AND actor_id=public.actor_id() AND event_type IN ('source.indexed','generation.completed','governance.evaluated'));

CREATE FUNCTION rag_knowledge_changed() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE iid uuid; BEGIN
 IF TG_TABLE_NAME='source_publications' THEN SELECT institution_id INTO iid FROM public.sources WHERE id=NEW.id;
 ELSE iid:=NEW.institution_id; END IF;
 UPDATE public.knowledge_states SET version=version+1 WHERE id=iid;
 RETURN NEW;
END $$;
CREATE TRIGGER publication_epoch AFTER INSERT OR UPDATE ON source_publications FOR EACH ROW EXECUTE FUNCTION rag_knowledge_changed();
CREATE TRIGGER governance_epoch AFTER INSERT ON governance_activations FOR EACH ROW EXECUTE FUNCTION rag_knowledge_changed();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['embedding_configs','evidence_chunks','publication_events','index_releases',
 'governance_versions','governance_activations','governance_evaluations','student_messages','advisor_guidance',
 'staff_notes','validated_answers','advisor_drafts','retrieval_traces','case_events'] LOOP
 EXECUTE format('CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION immutable_intake()',t);
 END LOOP;
END $$;
ALTER TABLE index_builds ADD CHECK(state IN ('queued','building','ready','failed'));
ALTER TABLE source_publications ADD CHECK(status IN ('published','withdrawn'));
ALTER TABLE advising_jobs ADD CHECK(kind IN ('index','answer','draft','evaluation'));
ALTER TABLE advising_jobs ADD CHECK(state IN ('queued','running','completed','blocked','failed','cancelled'));
ALTER TABLE advising_jobs ADD CHECK(attempt BETWEEN 1 AND 3);
ALTER TABLE advising_cases ADD CHECK(status IN ('open','assigned','in_progress','waiting_for_student','resolved','cancelled'));
ALTER TABLE advisor_guidance ADD CHECK(effective_until IS NULL OR effective_until>effective_from);
CREATE UNIQUE INDEX one_guidance_successor ON advisor_guidance(supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE INDEX chunks_text_search ON evidence_chunks USING gin(to_tsvector('english',text));
ALTER FUNCTION grant_parameters_ok(text,text[],text) RENAME TO intake_grant_parameters_ok;
CREATE FUNCTION grant_parameters_ok(role text,caps text[],ceiling text) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
 SELECT public.intake_grant_parameters_ok(role,array_remove(array_remove(caps,'source.publish'),'rules.manage'),ceiling)
 AND (role='platform_admin' OR NOT (caps && ARRAY['source.publish','rules.manage']))
$$;
DO $$ DECLARE f text; BEGIN
 FOREACH f IN ARRAY ARRAY['rag_cap(text,uuid)','rag_staff(uuid)','rag_conversation(uuid)','rag_advisor(uuid)',
 'rag_owner(uuid)','rag_worker_live()','rag_live()','rag_job_member(uuid)','rag_publish_source(uuid)',
 'rag_published(uuid,uuid,boolean)','rag_visible_version(uuid)','rag_build(uuid,boolean)','rag_citation(uuid)',
 'rag_job_read(uuid)','rag_job_target(text,uuid,uuid,boolean)','rag_knowledge_changed()','grant_parameters_ok(text,text[],text)'] LOOP
 EXECUTE 'ALTER FUNCTION '||f||' OWNER TO advisory_policy';
 EXECUTE 'REVOKE ALL ON FUNCTION '||f||' FROM PUBLIC';
 EXECUTE 'GRANT EXECUTE ON FUNCTION '||f||' TO advisory_app,advisory_rag';
 END LOOP;
END $$;
GRANT EXECUTE ON FUNCTION actor_id(),actor_live(),current_session_live(),can_student(uuid),profile_owner(uuid),
 profile_reviewer(uuid),platform_admin(),can_action(text,uuid),effective_grant(uuid),source_permission(uuid,uuid,uuid,text,boolean)
 TO advisory_rag;
