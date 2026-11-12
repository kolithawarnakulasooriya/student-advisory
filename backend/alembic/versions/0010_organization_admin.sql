ALTER TABLE institutions ADD COLUMN organization_epoch integer NOT NULL DEFAULT 1;
ALTER TABLE org_units ADD COLUMN status varchar NOT NULL DEFAULT 'active';
ALTER TABLE org_units ADD COLUMN version integer NOT NULL DEFAULT 1;
ALTER TABLE org_units ADD CHECK(status IN ('active','archived'));
CREATE TABLE organization_admin_grants (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id),
 institution_id uuid NOT NULL REFERENCES institutions(id), scope_kind varchar NOT NULL,
 root_org_unit_id uuid, status varchar NOT NULL DEFAULT 'active', valid_until timestamptz,
 version integer NOT NULL DEFAULT 1,
 FOREIGN KEY(institution_id,root_org_unit_id) REFERENCES org_units(institution_id,id),
 CHECK(status IN ('active','suspended','revoked')),
 CHECK((scope_kind='institution' AND root_org_unit_id IS NULL) OR
       (scope_kind='college' AND root_org_unit_id IS NOT NULL))
);
CREATE UNIQUE INDEX one_organization_delegation ON organization_admin_grants
 (user_id,institution_id,scope_kind,root_org_unit_id) NULLS NOT DISTINCT
 WHERE status IN ('active','suspended');
ALTER TABLE organization_admin_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE organization_admin_grants FORCE ROW LEVEL SECURITY;
GRANT SELECT,INSERT ON organization_admin_grants TO advisory_app;
GRANT UPDATE(status,version) ON organization_admin_grants TO advisory_app;
GRANT SELECT,UPDATE ON organization_admin_grants TO advisory_policy;
CREATE POLICY policy_reader ON organization_admin_grants TO advisory_policy USING(true) WITH CHECK(true);
GRANT INSERT ON org_units,enrollment_options TO advisory_app;
GRANT UPDATE(name,code,timezone,status,version) ON org_units TO advisory_app;
GRANT UPDATE(enabled,label) ON enrollment_options TO advisory_app;
GRANT UPDATE ON institutions,org_units,enrollment_options,invitations,outbox_events TO advisory_policy;

CREATE FUNCTION org_active(oid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.org_units o JOIN public.org_units p ON p.id=o.parent_id
 WHERE o.id=oid AND o.kind='department' AND o.status='active' AND p.status='active')
$$;
CREATE FUNCTION can_manage_org(iid uuid,oid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.actor_live() AND current_setting('app.mfa',true)='true'
 AND EXISTS(SELECT 1 FROM public.institutions WHERE id=iid)
 AND (oid IS NULL OR EXISTS(SELECT 1 FROM public.org_units WHERE id=oid AND institution_id=iid))
 AND (public.platform_admin() OR EXISTS(SELECT 1 FROM public.organization_admin_grants g
 WHERE g.user_id=public.actor_id() AND g.institution_id=iid AND g.status='active'
 AND (g.valid_until IS NULL OR g.valid_until>now()) AND (g.scope_kind='institution' OR
 (oid IS NOT NULL AND (g.root_org_unit_id=oid OR EXISTS(SELECT 1 FROM public.org_units o
 WHERE o.id=oid AND o.parent_id=g.root_org_unit_id))))))
$$;
CREATE FUNCTION can_admin_institution(iid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.actor_live() AND current_setting('app.mfa',true)='true' AND
 (public.platform_admin() OR EXISTS(SELECT 1 FROM public.organization_admin_grants g
 WHERE g.user_id=public.actor_id() AND g.institution_id=iid AND g.status='active'
 AND (g.valid_until IS NULL OR g.valid_until>now())))
$$;
CREATE FUNCTION organization_catalog_epoch() RETURNS bigint LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT coalesce(sum(organization_epoch),0)::bigint FROM public.institutions
$$;
CREATE POLICY organization_grant_read ON organization_admin_grants FOR SELECT TO advisory_app
 USING(user_id=public.actor_id() OR public.platform_admin());
CREATE POLICY organization_grant_insert ON organization_admin_grants FOR INSERT TO advisory_app
 WITH CHECK(public.platform_admin() AND public.current_session_live() AND user_id<>public.actor_id());
CREATE POLICY organization_grant_update ON organization_admin_grants FOR UPDATE TO advisory_app
 USING(public.platform_admin() AND public.current_session_live() AND user_id<>public.actor_id())
 WITH CHECK(public.platform_admin() AND public.current_session_live() AND user_id<>public.actor_id());
CREATE POLICY organization_admin_read ON org_units FOR SELECT TO advisory_app
 USING(public.can_manage_org(institution_id,id));
CREATE POLICY organization_admin_insert ON org_units FOR INSERT TO advisory_app
 WITH CHECK(public.current_session_live() AND public.can_manage_org(institution_id,parent_id));
CREATE POLICY organization_admin_update ON org_units FOR UPDATE TO advisory_app
 USING(public.current_session_live() AND public.can_manage_org(institution_id,id))
 WITH CHECK(public.current_session_live() AND public.can_manage_org(institution_id,id));
CREATE POLICY organization_institution ON institutions FOR SELECT TO advisory_app
 USING(public.can_admin_institution(id));
DROP POLICY option_read ON enrollment_options;
CREATE POLICY option_read ON enrollment_options FOR SELECT TO advisory_app
 USING((public.actor_live() AND enabled AND public.org_active(id)) OR public.can_manage_org(institution_id,id));
CREATE POLICY option_insert ON enrollment_options FOR INSERT TO advisory_app
 WITH CHECK(public.current_session_live() AND public.can_manage_org(institution_id,id));
CREATE POLICY option_update ON enrollment_options FOR UPDATE TO advisory_app
 USING(public.current_session_live() AND public.can_manage_org(institution_id,id))
 WITH CHECK(public.current_session_live() AND public.can_manage_org(institution_id,id));
CREATE POLICY organization_audit_read ON audit_events FOR SELECT TO advisory_app
 USING(action LIKE 'organization.%' AND public.can_manage_org(institution_id,org_unit_id));
CREATE POLICY organization_reason_read ON operational_reasons FOR SELECT TO advisory_app
 USING(EXISTS(SELECT 1 FROM public.audit_events a WHERE a.reason_id=operational_reasons.id
 AND a.action LIKE 'organization.%' AND public.can_manage_org(a.institution_id,a.org_unit_id)));

CREATE FUNCTION organization_grant_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(2026111102);
 IF TG_OP='UPDATE' AND (NEW.id<>OLD.id OR NEW.user_id<>OLD.user_id OR
 NEW.institution_id<>OLD.institution_id OR NEW.scope_kind<>OLD.scope_kind OR
 NEW.root_org_unit_id IS DISTINCT FROM OLD.root_org_unit_id OR NEW.valid_until IS DISTINCT FROM OLD.valid_until) THEN
 RAISE EXCEPTION 'Immutable organization grant binding' USING ERRCODE='23514'; END IF;
 IF NEW.scope_kind='college' AND NOT EXISTS(SELECT 1 FROM public.org_units o WHERE
 o.id=NEW.root_org_unit_id AND o.institution_id=NEW.institution_id AND o.kind='college') THEN
 RAISE EXCEPTION 'Invalid organization grant root' USING ERRCODE='23514'; END IF;
 IF NEW.status='active' AND NOT EXISTS(SELECT 1 FROM public.users u WHERE u.id=NEW.user_id
 AND u.verified AND u.status='active') THEN RAISE EXCEPTION 'Inactive identity' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER organization_grant_guard BEFORE INSERT OR UPDATE ON organization_admin_grants
 FOR EACH ROW EXECUTE FUNCTION organization_grant_guard();
CREATE FUNCTION organization_grant_epoch() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN UPDATE public.users SET grant_epoch=grant_epoch+1 WHERE id=NEW.user_id; RETURN NEW; END $$;
CREATE TRIGGER organization_grant_epoch AFTER INSERT OR UPDATE ON organization_admin_grants
 FOR EACH ROW EXECUTE FUNCTION organization_grant_epoch();
CREATE FUNCTION organization_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(2026111102);
 IF length(trim(NEW.name)) NOT BETWEEN 1 AND 200 OR length(trim(NEW.code)) NOT BETWEEN 1 AND 80 THEN
 RAISE EXCEPTION 'Invalid organization metadata' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' AND NEW.parent_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM public.org_units WHERE id=NEW.parent_id AND status='active') THEN
 RAISE EXCEPTION 'Inactive parent' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' THEN
 IF NEW.id<>OLD.id OR NEW.institution_id<>OLD.institution_id OR NEW.kind<>OLD.kind OR
 NEW.parent_id IS DISTINCT FROM OLD.parent_id THEN
 RAISE EXCEPTION 'Organization binding is immutable' USING ERRCODE='23514'; END IF;
 IF NEW.status='archived' AND OLD.status='active' AND (
 EXISTS(SELECT 1 FROM public.role_grants WHERE org_unit_id=OLD.id AND status='active') OR
 EXISTS(SELECT 1 FROM public.org_units WHERE parent_id=OLD.id AND status='active')) THEN
 RAISE EXCEPTION 'Organization is still in use' USING ERRCODE='23514'; END IF;
 IF NEW.status='active' AND OLD.status='archived' AND NEW.parent_id IS NOT NULL AND NOT EXISTS(
 SELECT 1 FROM public.org_units WHERE id=NEW.parent_id AND status='active') THEN
 RAISE EXCEPTION 'Inactive parent' USING ERRCODE='23514'; END IF;
 NEW.version:=OLD.version+1;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER organization_guard BEFORE INSERT OR UPDATE ON org_units
 FOR EACH ROW EXECUTE FUNCTION organization_guard();
CREATE FUNCTION organization_changed() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 UPDATE public.institutions SET organization_epoch=organization_epoch+1 WHERE id=NEW.institution_id;
 UPDATE public.users SET grant_epoch=grant_epoch+1 WHERE id IN (
 SELECT user_id FROM public.role_grants WHERE institution_id=NEW.institution_id
 UNION SELECT user_id FROM public.organization_admin_grants WHERE institution_id=NEW.institution_id
 UNION SELECT user_id FROM public.platform_grants WHERE status='active');
 IF TG_OP='UPDATE' AND NEW.name<>OLD.name THEN
 UPDATE public.enrollment_options SET label=NEW.name WHERE id=NEW.id; END IF;
 IF NEW.status='archived' THEN
 UPDATE public.enrollment_options SET enabled=false WHERE id=NEW.id AND enabled;
 UPDATE public.invitations SET status='revoked',version=version+1
 WHERE org_unit_id=NEW.id AND status='pending';
 UPDATE public.outbox_events SET state='cancelled' WHERE org_unit_id=NEW.id
 AND event_type='invitation.send' AND state='pending';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER organization_changed AFTER INSERT OR UPDATE ON org_units
 FOR EACH ROW EXECUTE FUNCTION organization_changed();
CREATE FUNCTION enrollment_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE o public.org_units; BEGIN
 PERFORM pg_advisory_xact_lock(2026111102);
 SELECT * INTO o FROM public.org_units WHERE id=NEW.id;
 IF NOT FOUND OR o.kind<>'department' OR o.institution_id<>NEW.institution_id OR
 (NEW.enabled AND NOT public.org_active(NEW.id)) THEN
 RAISE EXCEPTION 'Invalid enrollment scope' USING ERRCODE='23514'; END IF;
 NEW.label:=o.name; RETURN NEW;
END $$;
CREATE TRIGGER enrollment_guard BEFORE INSERT OR UPDATE ON enrollment_options
 FOR EACH ROW EXECUTE FUNCTION enrollment_guard();
CREATE FUNCTION enrollment_changed() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 IF TG_OP='INSERT' THEN UPDATE public.org_units SET version=version WHERE id=NEW.id;
 ELSIF NEW.enabled<>OLD.enabled THEN UPDATE public.org_units SET version=version WHERE id=NEW.id;
 END IF; RETURN NEW;
END $$;
CREATE TRIGGER enrollment_changed AFTER INSERT OR UPDATE ON enrollment_options
 FOR EACH ROW EXECUTE FUNCTION enrollment_changed();
CREATE FUNCTION organization_activation_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(2026111102);
 IF TG_TABLE_NAME='role_grants' THEN
 IF NEW.status IN ('active','pending','invited') AND NOT public.org_active(NEW.org_unit_id) THEN
 RAISE EXCEPTION 'Inactive organization' USING ERRCODE='23514'; END IF;
 ELSIF TG_TABLE_NAME='invitations' THEN
 IF NEW.status='pending' AND NOT public.org_active(NEW.org_unit_id) THEN
 RAISE EXCEPTION 'Inactive organization' USING ERRCODE='23514'; END IF;
 ELSE
 IF NEW.status='approved' AND NOT public.org_active(NEW.org_unit_id) THEN
 RAISE EXCEPTION 'Inactive organization' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' AND (NOT public.org_active(NEW.org_unit_id) OR NOT EXISTS(
 SELECT 1 FROM public.enrollment_options WHERE id=NEW.org_unit_id AND enabled)) THEN
 RAISE EXCEPTION 'Requests closed' USING ERRCODE='23514'; END IF;
 END IF; RETURN NEW;
END $$;
CREATE TRIGGER organization_activation_guard BEFORE INSERT OR UPDATE ON role_grants
 FOR EACH ROW EXECUTE FUNCTION organization_activation_guard();
CREATE TRIGGER organization_activation_guard BEFORE INSERT OR UPDATE ON invitations
 FOR EACH ROW EXECUTE FUNCTION organization_activation_guard();
CREATE TRIGGER organization_activation_guard BEFORE INSERT OR UPDATE ON membership_requests
 FOR EACH ROW EXECUTE FUNCTION organization_activation_guard();
CREATE OR REPLACE FUNCTION update_account(uid uuid,new_status text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF NOT public.platform_admin() OR NOT public.current_session_live() OR new_status NOT IN ('active','suspended')
 THEN RAISE insufficient_privilege; END IF;
 UPDATE public.users SET status=new_status WHERE id=uid;
 IF new_status='suspended' THEN
 UPDATE public.role_grants SET status='suspended',version=version+1 WHERE user_id=uid AND status='active';
 UPDATE public.platform_grants SET status='suspended',version=version+1 WHERE user_id=uid AND status='active';
 UPDATE public.organization_admin_grants SET status='suspended',version=version+1 WHERE user_id=uid AND status='active';
 UPDATE public.sessions SET revoked=true WHERE user_id=uid;
 END IF;
END $$;

CREATE OR REPLACE FUNCTION can_action(action text, scope uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE g public.role_grants; BEGIN
 IF NOT public.actor_live() THEN RETURN false; END IF;
 IF scope IS NOT NULL AND action NOT IN ('org.read','audit.read','history.read')
 AND NOT public.org_active(scope) THEN RETURN false; END IF;
 IF public.platform_admin() THEN
 IF action=ANY(ARRAY['membership.read','student.read','staff.read','audit.read','history.read'])
 AND nullif(current_setting('app.purpose',true),'') IS NULL THEN RETURN false; END IF;
 RETURN action=ANY(ARRAY[
 'org.read','student.invite','student.approve','student.manage','advisor.invite','advisor.approve',
 'advisor.manage','manager.invite','manager.approve','manager.manage','secretary.manage',
 'assignment.manage','membership.read','student.read','staff.read','audit.read','history.read',
 'platform.manage','account.manage']); END IF;
 IF action='manager.approve' THEN RETURN false; END IF;
 FOR g IN SELECT * FROM public.role_grants WHERE user_id=public.actor_id()
 AND org_unit_id=scope AND public.effective_grant(id) LOOP
  IF action='org.read' AND (g.role='student' OR current_setting('app.mfa',true)='true')
    THEN RETURN true; END IF;
  IF current_setting('app.mfa',true) IS DISTINCT FROM 'true' THEN CONTINUE; END IF;
  IF g.role='manager' AND action=ANY(ARRAY['student.invite','student.approve','student.manage',
    'advisor.invite','advisor.approve','advisor.manage','secretary.manage','assignment.manage',
    'membership.read','student.read','staff.read','audit.read','history.read']) THEN RETURN true; END IF;
  IF g.role='secretary' THEN
    IF action=ANY(g.capabilities) AND action=ANY(ARRAY['student.invite','student.approve',
      'student.manage','assignment.manage']) THEN RETURN true; END IF;
    IF action='membership.read' AND cardinality(g.capabilities)>0 THEN RETURN true; END IF;
  END IF;
  IF g.role='platform_admin' AND (action=ANY(g.capabilities))
    AND (action NOT LIKE 'manager.%' OR g.ceiling='manager')
    AND (action NOT LIKE 'advisor.%' OR g.ceiling IN ('advisor','manager'))
    AND (action<>'secretary.manage' OR g.ceiling IN ('advisor','manager')) THEN RETURN true; END IF;
 END LOOP;
 RETURN false;
END $$;

CREATE OR REPLACE FUNCTION inviter_allowed(iid uuid) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE inv public.invitations; previous_actor text; previous_mfa text; allowed boolean;
BEGIN
 SELECT * INTO inv FROM public.invitations WHERE id=iid;
 IF NOT FOUND OR NOT public.org_active(inv.org_unit_id) THEN RETURN false; END IF;
 previous_actor:=current_setting('app.user_id',true);
 previous_mfa:=current_setting('app.mfa',true);
 PERFORM set_config('app.user_id',inv.inviter_id::text,true);
 PERFORM set_config('app.mfa','true',true);
 allowed:=public.can_action(CASE WHEN inv.role='secretary' THEN 'secretary.manage'
   ELSE inv.role||'.invite' END, inv.org_unit_id);
 PERFORM set_config('app.user_id',coalesce(previous_actor,''),true);
 PERFORM set_config('app.mfa',coalesce(previous_mfa,''),true);
 RETURN allowed;
END $$;
ALTER FUNCTION org_active(uuid) OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION org_active(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION org_active(uuid) TO advisory_app;
ALTER FUNCTION can_manage_org(uuid,uuid) OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION can_manage_org(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION can_manage_org(uuid,uuid) TO advisory_app;
ALTER FUNCTION can_admin_institution(uuid) OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION can_admin_institution(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION can_admin_institution(uuid) TO advisory_app;
ALTER FUNCTION organization_catalog_epoch() OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION organization_catalog_epoch() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION organization_catalog_epoch() TO advisory_app;
ALTER FUNCTION organization_grant_guard() OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION organization_grant_guard() FROM PUBLIC;
ALTER FUNCTION organization_grant_epoch() OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION organization_grant_epoch() FROM PUBLIC;
ALTER FUNCTION organization_guard() OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION organization_guard() FROM PUBLIC;
ALTER FUNCTION organization_changed() OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION organization_changed() FROM PUBLIC;
ALTER FUNCTION enrollment_guard() OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION enrollment_guard() FROM PUBLIC;
ALTER FUNCTION enrollment_changed() OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION enrollment_changed() FROM PUBLIC;
ALTER FUNCTION organization_activation_guard() OWNER TO advisory_policy;
REVOKE ALL ON FUNCTION organization_activation_guard() FROM PUBLIC;
