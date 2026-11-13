DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='advisory_ingest') THEN
 CREATE ROLE advisory_ingest LOGIN PASSWORD 'local-ingest-only' NOSUPERUSER NOBYPASSRLS;
 END IF;
END $$;
GRANT USAGE ON SCHEMA public TO advisory_ingest;

CREATE FUNCTION intake_cap(action text, scope uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT public.actor_live() AND current_setting('app.mfa',true)='true'
 AND (scope IS NULL OR EXISTS(SELECT 1 FROM public.org_units o WHERE o.id=scope
 AND o.status='active' AND (o.kind='college' OR public.org_active(o.id))))
 AND ((public.platform_admin() AND nullif(current_setting('app.purpose',true),'') IS NOT NULL)
 OR EXISTS(SELECT 1 FROM public.role_grants g WHERE g.user_id=public.actor_id()
 AND g.org_unit_id=scope AND public.effective_grant(g.id) AND
 (g.role='manager' OR (g.role='platform_admin' AND action=ANY(g.capabilities)))))
 AND action IN ('profile.configure','source.manage','source.read')
$$;
CREATE FUNCTION profile_owner(mid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.can_student(mid) AND EXISTS(SELECT 1 FROM public.student_memberships
 WHERE id=mid AND user_id=public.actor_id())
$$;
CREATE FUNCTION profile_reviewer(mid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.can_student(mid) AND current_setting('app.mfa',true)='true' AND EXISTS(
 SELECT 1 FROM public.advisor_assignments a JOIN public.role_grants g ON g.id=a.advisor_grant_id
 WHERE a.student_membership_id=mid AND a.ended_at IS NULL AND g.user_id=public.actor_id()
 AND public.effective_grant(g.id))
$$;
CREATE FUNCTION schema_read(scope uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.intake_cap('profile.configure',scope) OR EXISTS(
 SELECT 1 FROM public.student_memberships m WHERE m.org_unit_id=scope AND public.can_student(m.id))
$$;
CREATE FUNCTION source_permission(iid uuid,scope uuid,mid uuid,visibility text,writing boolean)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT public.actor_live() AND
 ((visibility='student' AND mid IS NOT NULL AND EXISTS(SELECT 1 FROM public.student_memberships m
 WHERE m.id=mid AND m.institution_id=iid AND m.org_unit_id=scope AND public.can_student(mid))
 AND (NOT writing OR public.profile_reviewer(mid) OR
 public.intake_cap('source.manage',scope))) OR
 (visibility IN ('department','college','institution') AND mid IS NULL
 AND ((visibility='institution' AND scope IS NULL) OR EXISTS(SELECT 1 FROM public.org_units o
 WHERE o.id=scope AND o.institution_id=iid AND o.kind=visibility))
 AND EXISTS(SELECT 1 FROM public.institutions WHERE id=iid)
 AND public.intake_cap(CASE WHEN writing THEN 'source.manage' ELSE 'source.read' END,scope)))
$$;
CREATE FUNCTION source_allowed(sid uuid,writing boolean) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.sources s WHERE s.id=sid AND
 public.source_permission(s.institution_id,s.org_unit_id,s.student_membership_id,s.visibility,writing)
 AND (NOT writing OR NOT s.archived))
$$;
CREATE FUNCTION version_allowed(vid uuid,writing boolean) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.source_versions v WHERE v.id=vid
 AND public.source_allowed(v.source_id,writing))
$$;
CREATE FUNCTION ingest_job_current(jid uuid) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE j public.ingestion_jobs; s public.sources; old_user text; old_mfa text; old_purpose text;
 allowed boolean;
BEGIN
 SELECT * INTO j FROM public.ingestion_jobs WHERE id=jid;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT s0.* INTO s FROM public.sources s0 JOIN public.source_versions v ON v.source_id=s0.id
 WHERE v.id=j.source_version_id AND v.version=s0.version;
 IF NOT FOUND OR s.archived OR NOT EXISTS(SELECT 1 FROM public.users u WHERE u.id=j.actor_id
 AND u.grant_epoch=j.grant_epoch AND u.status='active' AND u.verified) THEN RETURN false; END IF;
 IF s.student_membership_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.student_memberships m
 WHERE m.id=s.student_membership_id AND m.relationship_epoch=j.relationship_epoch) THEN
 RETURN false; END IF;
 old_user:=current_setting('app.user_id',true); old_mfa:=current_setting('app.mfa',true);
 old_purpose:=current_setting('app.purpose',true);
 PERFORM set_config('app.user_id',j.actor_id::text,true);
 PERFORM set_config('app.mfa','true',true); PERFORM set_config('app.purpose',j.purpose,true);
 allowed:=public.source_allowed(s.id,true);
 PERFORM set_config('app.user_id',coalesce(old_user,''),true);
 PERFORM set_config('app.mfa',coalesce(old_mfa,''),true);
 PERFORM set_config('app.purpose',coalesce(old_purpose,''),true);
 RETURN allowed;
END $$;
CREATE FUNCTION ingest_version(vid uuid) RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.ingestion_jobs j WHERE j.source_version_id=vid
 AND j.id=nullif(current_setting('app.job_id',true),'')::uuid
 AND j.lease_token=nullif(current_setting('app.lease_token',true),'')::uuid
 AND j.lease_until>now() AND j.state IN ('scanning','extracting') AND public.ingest_job_current(j.id))
$$;

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['onboarding_configs','onboarding_schemas','academic_profiles',
 'profile_versions','sources','source_versions','ingestion_jobs','extraction_artifacts'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('GRANT SELECT ON %I TO advisory_policy,advisory_app',t);
 EXECUTE format('CREATE POLICY policy_reader ON %I TO advisory_policy USING(true)',t);
 END LOOP;
END $$;
GRANT INSERT ON onboarding_configs,onboarding_schemas,academic_profiles,profile_versions,
 sources,source_versions,ingestion_jobs TO advisory_app;
GRANT UPDATE(version,active_schema_id) ON onboarding_configs TO advisory_app;
GRANT UPDATE(version) ON academic_profiles TO advisory_app;
GRANT UPDATE(version,archived) ON sources TO advisory_app;
GRANT SELECT ON ingestion_jobs,source_versions,sources,extraction_artifacts TO advisory_ingest;
GRANT INSERT ON extraction_artifacts,outbox_events TO advisory_ingest;
GRANT UPDATE(state,error_code,lease_token,lease_until) ON ingestion_jobs TO advisory_ingest;

CREATE POLICY config_read ON onboarding_configs FOR SELECT TO advisory_app USING(schema_read(id));
CREATE POLICY config_insert ON onboarding_configs FOR INSERT TO advisory_app WITH CHECK(intake_cap('profile.configure',id));
CREATE POLICY config_update ON onboarding_configs FOR UPDATE TO advisory_app USING(intake_cap('profile.configure',id)) WITH CHECK(intake_cap('profile.configure',id));
CREATE POLICY schema_read ON onboarding_schemas FOR SELECT TO advisory_app USING(schema_read(org_unit_id));
CREATE POLICY schema_insert ON onboarding_schemas FOR INSERT TO advisory_app WITH CHECK(
 intake_cap('profile.configure',org_unit_id) AND author_id=actor_id() AND EXISTS(
 SELECT 1 FROM org_units o WHERE o.id=org_unit_id AND o.institution_id=institution_id AND o.kind='department'));
CREATE POLICY profile_read ON academic_profiles FOR SELECT TO advisory_app USING(can_student(id));
CREATE POLICY profile_insert ON academic_profiles FOR INSERT TO advisory_app WITH CHECK(profile_owner(id));
CREATE POLICY profile_update ON academic_profiles FOR UPDATE TO advisory_app USING(profile_owner(id) OR profile_reviewer(id)) WITH CHECK(profile_owner(id) OR profile_reviewer(id));
CREATE POLICY profile_version_read ON profile_versions FOR SELECT TO advisory_app USING(can_student(student_membership_id));
CREATE POLICY profile_version_insert ON profile_versions FOR INSERT TO advisory_app WITH CHECK(
 author_id=actor_id() AND (profile_owner(student_membership_id) OR profile_reviewer(student_membership_id))
 AND EXISTS(SELECT 1 FROM student_memberships m WHERE m.id=student_membership_id
 AND m.institution_id=profile_versions.institution_id AND m.org_unit_id=profile_versions.org_unit_id)
 AND EXISTS(SELECT 1 FROM onboarding_schemas c WHERE c.id=profile_versions.schema_id AND c.org_unit_id=profile_versions.org_unit_id));
CREATE POLICY source_read ON sources FOR SELECT TO advisory_app USING(source_allowed(id,false));
CREATE POLICY source_insert ON sources FOR INSERT TO advisory_app WITH CHECK(owner_id=actor_id()
 AND source_permission(institution_id,org_unit_id,student_membership_id,visibility,true));
CREATE POLICY source_update ON sources FOR UPDATE TO advisory_app USING(source_allowed(id,true)) WITH CHECK(
 source_permission(institution_id,org_unit_id,student_membership_id,visibility,true));
CREATE POLICY version_read ON source_versions FOR SELECT TO advisory_app USING(source_allowed(source_id,false));
CREATE POLICY version_insert ON source_versions FOR INSERT TO advisory_app WITH CHECK(source_allowed(source_id,true) AND author_id=actor_id());
CREATE POLICY job_read ON ingestion_jobs FOR SELECT TO advisory_app USING(version_allowed(source_version_id,false));
CREATE POLICY job_insert ON ingestion_jobs FOR INSERT TO advisory_app WITH CHECK(version_allowed(source_version_id,true) AND actor_id=public.actor_id());
CREATE POLICY artifact_read ON extraction_artifacts FOR SELECT TO advisory_app USING(version_allowed(source_version_id,false));
CREATE POLICY worker_jobs ON ingestion_jobs TO advisory_ingest USING(true);
CREATE POLICY worker_versions ON source_versions FOR SELECT TO advisory_ingest USING(ingest_version(id));
CREATE POLICY worker_sources ON sources FOR SELECT TO advisory_ingest USING(EXISTS(
 SELECT 1 FROM source_versions v WHERE v.source_id=sources.id AND ingest_version(v.id)));
CREATE POLICY worker_artifacts ON extraction_artifacts TO advisory_ingest USING(ingest_version(source_version_id)) WITH CHECK(
 ingest_version(source_version_id) AND job_id=nullif(current_setting('app.job_id',true),'')::uuid);
CREATE POLICY worker_outbox ON outbox_events FOR INSERT TO advisory_ingest WITH CHECK(
 event_type='source.extracted' AND EXISTS(SELECT 1 FROM source_versions v JOIN sources s ON s.id=v.source_id
 JOIN ingestion_jobs j ON j.source_version_id=v.id WHERE j.id=nullif(current_setting('app.job_id',true),'')::uuid
 AND ingest_version(v.id) AND outbox_events.aggregate_id=s.id AND outbox_events.aggregate_version=v.version
 AND outbox_events.actor_id=j.actor_id AND outbox_events.institution_id=s.institution_id
 AND outbox_events.org_unit_id IS NOT DISTINCT FROM s.org_unit_id));
ALTER TABLE outbox_events ALTER COLUMN org_unit_id DROP NOT NULL;

CREATE FUNCTION immutable_intake() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Immutable snapshot' USING ERRCODE='23514'; END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['onboarding_schemas','profile_versions','source_versions','extraction_artifacts'] LOOP
 EXECUTE format('CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION immutable_intake()',t);
 END LOOP;
END $$;

ALTER FUNCTION grant_parameters_ok(text,text[],text) RENAME TO legacy_grant_parameters_ok;
CREATE FUNCTION grant_parameters_ok(role text,caps text[],ceiling text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
 SELECT CASE WHEN role='platform_admin' THEN
 public.legacy_grant_parameters_ok(role,array_remove(array_remove(array_remove(caps,
 'profile.configure'),'source.manage'),'source.read'),ceiling)
 ELSE public.legacy_grant_parameters_ok(role,caps,ceiling) END
$$;
DO $$ DECLARE f text; BEGIN
 FOREACH f IN ARRAY ARRAY['intake_cap(text,uuid)','profile_owner(uuid)','profile_reviewer(uuid)',
 'schema_read(uuid)','source_permission(uuid,uuid,uuid,text,boolean)','source_allowed(uuid,boolean)',
 'version_allowed(uuid,boolean)','ingest_job_current(uuid)','ingest_version(uuid)',
 'grant_parameters_ok(text,text[],text)'] LOOP
 EXECUTE 'ALTER FUNCTION '||f||' OWNER TO advisory_policy';
 EXECUTE 'REVOKE ALL ON FUNCTION '||f||' FROM PUBLIC';
 EXECUTE 'GRANT EXECUTE ON FUNCTION '||f||' TO advisory_app,advisory_ingest';
 END LOOP;
END $$;
