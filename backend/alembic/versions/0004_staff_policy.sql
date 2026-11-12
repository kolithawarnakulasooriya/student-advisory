-- Policy helpers run under a NOLOGIN role with explicit table privileges, never BYPASSRLS.
CREATE FUNCTION actor_id() RETURNS uuid LANGUAGE sql STABLE AS $$
 SELECT nullif(current_setting('app.user_id',true),'')::uuid
$$;
CREATE FUNCTION actor_live() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.users u WHERE u.id=public.actor_id()
 AND u.status='active' AND u.verified)
$$;
CREATE FUNCTION platform_admin() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.actor_live() AND current_setting('app.mfa',true)='true'
 AND EXISTS(SELECT 1 FROM public.platform_grants p WHERE p.user_id=public.actor_id()
 AND p.status='active')
$$;
CREATE FUNCTION effective_grant(gid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.role_grants g JOIN public.users u ON u.id=g.user_id
 WHERE g.id=gid AND g.status='active' AND (g.valid_until IS NULL OR g.valid_until>now())
 AND u.status='active' AND u.verified)
$$;
CREATE FUNCTION can_action(action text, scope uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE g public.role_grants; BEGIN
 IF NOT public.actor_live() THEN RETURN false; END IF;
 IF public.platform_admin() THEN
 IF action=ANY(ARRAY['membership.read','student.read','staff.read','audit.read','history.read'])
 AND nullif(current_setting('app.purpose',true),'') IS NULL THEN RETURN false; END IF;
 RETURN action=ANY(ARRAY[
 'org.read','student.invite','student.approve','student.manage','advisor.invite','advisor.approve',
 'advisor.manage','manager.invite','manager.approve','manager.manage','secretary.manage',
 'assignment.manage','membership.read','student.read','staff.read','audit.read','history.read',
 'platform.manage','account.manage']); END IF;
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
    AND (action NOT LIKE 'manager.%' OR g.ceiling='manager') THEN RETURN true; END IF;
 END LOOP;
 RETURN false;
END $$;
CREATE FUNCTION can_student(mid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.actor_live() AND EXISTS(SELECT 1 FROM public.student_memberships m
 WHERE m.id=mid AND public.effective_grant(m.grant_id) AND (
 m.user_id=public.actor_id() OR
 (public.platform_admin() AND nullif(current_setting('app.purpose',true),'') IS NOT NULL) OR
 (NOT public.platform_admin() AND public.can_action('student.read',m.org_unit_id)) OR
 (current_setting('app.mfa',true)='true' AND EXISTS(
  SELECT 1 FROM public.advisor_assignments a JOIN public.role_grants g ON g.id=a.advisor_grant_id
  WHERE a.student_membership_id=m.id AND a.ended_at IS NULL AND g.user_id=public.actor_id()
  AND g.org_unit_id=m.org_unit_id AND g.institution_id=m.institution_id
  AND g.role='advisor' AND public.effective_grant(g.id)))))
$$;
CREATE FUNCTION can_user(uid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT uid=public.actor_id() OR (public.actor_live() AND (
 (public.platform_admin() AND nullif(current_setting('app.purpose',true),'') IS NOT NULL) OR
 EXISTS(SELECT 1 FROM public.role_grants g WHERE g.user_id=uid AND (
  public.can_action('membership.read',g.org_unit_id) OR public.can_action('staff.read',g.org_unit_id)
  OR (g.role='advisor' AND (public.can_action('assignment.manage',g.org_unit_id)
   OR public.can_action('student.approve',g.org_unit_id) OR public.can_action('student.invite',g.org_unit_id)))))
 OR EXISTS(SELECT 1 FROM public.student_memberships m WHERE m.user_id=uid AND public.can_student(m.id))
 OR EXISTS(SELECT 1 FROM public.membership_requests r WHERE r.user_id=uid
    AND public.can_action(r.requested_role||'.approve',r.org_unit_id))))
$$;
CREATE FUNCTION can_grant(role text, scope uuid, uid uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT uid<>public.actor_id() AND CASE
 WHEN role='platform_admin' THEN public.platform_admin()
 WHEN role='secretary' THEN public.can_action('secretary.manage',scope)
 WHEN role IN ('student','advisor','manager') THEN public.can_action(role||'.manage',scope)
   OR public.can_action(role||'.approve',scope) OR public.can_action(role||'.invite',scope)
 ELSE false END
$$;
CREATE FUNCTION grant_parameters_ok(role text, caps text[], ceiling text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
 SELECT ceiling IN ('student','advisor','manager') AND CASE
 WHEN role='secretary' THEN caps <@ ARRAY['student.invite','student.approve','student.manage','assignment.manage']
 WHEN role='platform_admin' THEN caps <@ ARRAY['org.read','student.invite','student.approve','student.manage',
 'advisor.invite','advisor.approve','advisor.manage','manager.invite','manager.approve','manager.manage',
 'secretary.manage','assignment.manage','membership.read','student.read','staff.read','audit.read','history.read']
 ELSE cardinality(caps)=0 END
$$;
CREATE FUNCTION related_student_grant(gid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.student_memberships m WHERE m.grant_id=gid AND public.can_student(m.id))
$$;

-- Roles, privileges and policies are applied before any application writes are enabled.
CREATE POLICY policy_reader ON platform_grants TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON platform_control TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON enrollment_options TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON student_memberships TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON advisor_assignments TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON membership_requests TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON invitations TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON audit_events TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON idempotency_records TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON outbox_events TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON users TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON sessions TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON role_grants TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON org_units TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON institutions TO advisory_policy USING(true) WITH CHECK(true);
CREATE POLICY policy_reader ON verifications TO advisory_policy USING(true) WITH CHECK(true);

CREATE POLICY platform_read ON platform_grants FOR SELECT TO advisory_app
 USING(user_id=public.actor_id() OR public.platform_admin());
CREATE POLICY platform_write ON platform_grants FOR ALL TO advisory_app
 USING(public.platform_admin()) WITH CHECK(public.platform_admin());
CREATE POLICY option_read ON enrollment_options FOR SELECT TO advisory_app
 USING(public.actor_live() AND enabled);
CREATE POLICY staff_user ON users FOR SELECT TO advisory_app USING(public.can_user(id));
DROP POLICY authorized_orgs ON org_units;
CREATE POLICY authorized_orgs ON org_units FOR SELECT TO advisory_app USING(public.can_action('org.read',id));
CREATE POLICY staff_grants ON role_grants FOR SELECT TO advisory_app USING(
 public.can_action('membership.read',org_unit_id) OR public.can_action('staff.read',org_unit_id)
 OR (role='advisor' AND (public.can_action('assignment.manage',org_unit_id)
 OR public.can_action('student.invite',org_unit_id) OR public.can_action('student.approve',org_unit_id)))
 OR public.related_student_grant(id));
CREATE POLICY grant_insert ON role_grants FOR INSERT TO advisory_app
 WITH CHECK(public.can_grant(role,org_unit_id,user_id) AND public.grant_parameters_ok(role,capabilities,ceiling)
 AND EXISTS(SELECT 1 FROM public.org_units o WHERE o.id=org_unit_id AND o.institution_id=institution_id));
CREATE POLICY grant_update ON role_grants FOR UPDATE TO advisory_app
 USING(public.can_grant(role,org_unit_id,user_id))
 WITH CHECK(public.can_grant(role,org_unit_id,user_id) AND public.grant_parameters_ok(role,capabilities,ceiling));
CREATE POLICY student_read ON student_memberships FOR SELECT TO advisory_app USING(
 user_id=public.actor_id() OR public.can_student(id) OR public.can_action('membership.read',org_unit_id));
CREATE POLICY student_insert ON student_memberships FOR INSERT TO advisory_app WITH CHECK(
 public.can_action('student.approve',org_unit_id) OR public.can_action('student.invite',org_unit_id)
 OR (user_id=public.actor_id() AND current_setting('app.accepting',true)=grant_id::text));
CREATE POLICY student_update ON student_memberships FOR UPDATE TO advisory_app
 USING(public.can_action('assignment.manage',org_unit_id) OR public.can_action('student.manage',org_unit_id))
 WITH CHECK(public.can_action('assignment.manage',org_unit_id) OR public.can_action('student.manage',org_unit_id));
CREATE POLICY request_read ON membership_requests FOR SELECT TO advisory_app USING(
 user_id=public.actor_id() OR public.can_action(requested_role||'.approve',org_unit_id));
CREATE POLICY request_insert ON membership_requests FOR INSERT TO advisory_app WITH CHECK(
 public.actor_live() AND user_id=public.actor_id() AND status='pending' AND EXISTS(
 SELECT 1 FROM public.enrollment_options e WHERE e.id=org_unit_id AND e.enabled
 AND e.institution_id=institution_id));
CREATE POLICY request_update ON membership_requests FOR UPDATE TO advisory_app
 USING(public.can_action(requested_role||'.approve',org_unit_id) AND user_id<>public.actor_id())
 WITH CHECK(public.can_action(requested_role||'.approve',org_unit_id) AND user_id<>public.actor_id());
CREATE POLICY invite_read ON invitations FOR SELECT TO advisory_app USING(
 public.can_action(role||'.invite',org_unit_id) OR (role='secretary' AND public.can_action('secretary.manage',org_unit_id))
 OR (public.actor_live() AND email=(SELECT email FROM public.users WHERE id=public.actor_id())));
CREATE POLICY invite_insert ON invitations FOR INSERT TO advisory_app WITH CHECK(
 inviter_id=public.actor_id() AND (public.can_action(role||'.invite',org_unit_id)
 OR (role='secretary' AND public.can_action('secretary.manage',org_unit_id))));
CREATE POLICY invite_update ON invitations FOR UPDATE TO advisory_app USING(
 public.can_action(role||'.invite',org_unit_id) OR (role='secretary' AND public.can_action('secretary.manage',org_unit_id))
 OR (public.actor_live() AND email=(SELECT email FROM public.users WHERE id=public.actor_id())))
 WITH CHECK(true);
CREATE POLICY assignment_read ON advisor_assignments FOR SELECT TO advisory_app USING(
 public.can_student(student_membership_id) OR EXISTS(SELECT 1 FROM public.student_memberships m
 WHERE m.id=student_membership_id AND public.can_action('membership.read',m.org_unit_id)));
CREATE POLICY assignment_insert ON advisor_assignments FOR INSERT TO advisory_app WITH CHECK(
 EXISTS(SELECT 1 FROM public.student_memberships m WHERE m.id=student_membership_id AND (
 public.can_action('assignment.manage',m.org_unit_id) OR public.can_action('student.approve',m.org_unit_id)
 OR public.can_action('student.invite',m.org_unit_id) OR current_setting('app.accepting',true)=m.grant_id::text)));
CREATE POLICY assignment_update ON advisor_assignments FOR UPDATE TO advisory_app USING(
 EXISTS(SELECT 1 FROM public.student_memberships m WHERE m.id=student_membership_id AND (
 public.can_action('assignment.manage',m.org_unit_id) OR public.can_action('student.manage',m.org_unit_id)
 OR public.can_action('advisor.manage',m.org_unit_id)))) WITH CHECK(true);
CREATE POLICY audit_read ON audit_events FOR SELECT TO advisory_app USING(
 actor_id=public.actor_id() OR public.can_action('audit.read',org_unit_id));
CREATE POLICY audit_append ON audit_events FOR INSERT TO advisory_app WITH CHECK(actor_id=public.actor_id());
CREATE POLICY own_idempotency ON idempotency_records TO advisory_app
 USING(actor_id=public.actor_id()) WITH CHECK(actor_id=public.actor_id());
CREATE POLICY outbox_read ON outbox_events FOR SELECT TO advisory_app USING(actor_id=public.actor_id()
 OR public.can_action('membership.read',org_unit_id));
CREATE POLICY outbox_insert ON outbox_events FOR INSERT TO advisory_app WITH CHECK(actor_id=public.actor_id());
CREATE POLICY mail_invitations ON invitations FOR SELECT TO advisory_mail USING(true);
CREATE POLICY mail_outbox ON outbox_events TO advisory_mail USING(event_type='invitation.send')
 WITH CHECK(event_type='invitation.send');
CREATE POLICY mail_invite_update ON invitations FOR UPDATE TO advisory_mail USING(true) WITH CHECK(true);

-- Narrow helpers retain trigger authority without granting general identity/session writes to the API.
CREATE OR REPLACE FUNCTION grant_epoch_changed() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 IF TG_OP IN ('UPDATE','DELETE') THEN
  UPDATE public.users SET grant_epoch=grant_epoch+1 WHERE id=OLD.user_id;
 END IF;
 IF TG_OP='INSERT' OR (TG_OP='UPDATE' AND NEW.user_id<>OLD.user_id) THEN
  UPDATE public.users SET grant_epoch=grant_epoch+1 WHERE id=NEW.user_id;
 END IF;
 RETURN NULL;
END $$;
CREATE FUNCTION platform_epoch_changed() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 UPDATE public.users SET grant_epoch=grant_epoch+1 WHERE id=NEW.user_id;
 RETURN NULL;
END $$;
CREATE TRIGGER platform_epoch AFTER INSERT OR UPDATE ON platform_grants
 FOR EACH ROW EXECUTE FUNCTION platform_epoch_changed();
CREATE FUNCTION assignment_epoch_changed() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 UPDATE public.student_memberships SET relationship_epoch=relationship_epoch+1, version=version+1
 WHERE id=NEW.student_membership_id;
 RETURN NULL;
END $$;
CREATE TRIGGER assignment_epoch AFTER INSERT OR UPDATE ON advisor_assignments
 FOR EACH ROW EXECUTE FUNCTION assignment_epoch_changed();
CREATE FUNCTION assignment_valid() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 IF NEW.ended_at IS NULL AND NOT EXISTS(SELECT 1 FROM public.student_memberships m
 JOIN public.role_grants g ON g.id=NEW.advisor_grant_id WHERE m.id=NEW.student_membership_id
 AND g.role='advisor' AND g.org_unit_id=m.org_unit_id AND g.institution_id=m.institution_id
 AND public.effective_grant(g.id)) THEN
  RAISE EXCEPTION 'Invalid advisor scope' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER assignment_valid BEFORE INSERT OR UPDATE ON advisor_assignments
 FOR EACH ROW EXECUTE FUNCTION assignment_valid();
CREATE FUNCTION current_session_live() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.sessions s JOIN public.users u ON u.id=s.user_id
 WHERE s.token_hash=current_setting('app.session_hash',true) AND s.user_id=public.actor_id()
 AND NOT s.revoked AND s.expires_at>now() AND u.status='active')
$$;
CREATE FUNCTION update_account(uid uuid, new_status text) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 IF NOT public.platform_admin() OR NOT public.current_session_live()
 OR new_status NOT IN ('active','suspended') THEN RAISE insufficient_privilege; END IF;
 UPDATE public.users SET status=new_status WHERE id=uid;
END $$;
CREATE FUNCTION revoke_actor_sessions(uid uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 IF NOT public.platform_admin() OR NOT public.current_session_live() THEN RAISE insufficient_privilege; END IF;
 UPDATE public.sessions SET revoked=true WHERE user_id=uid;
END $$;
CREATE FUNCTION inviter_allowed(iid uuid) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE inv public.invitations; previous_actor text; previous_mfa text; allowed boolean;
BEGIN
 SELECT * INTO inv FROM public.invitations WHERE id=iid;
 IF NOT FOUND THEN RETURN false; END IF;
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
CREATE FUNCTION accepting_scope(scope uuid) RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT public.actor_live() AND EXISTS(SELECT 1 FROM public.invitations i
 JOIN public.users u ON u.id=public.actor_id() WHERE i.org_unit_id=scope AND i.email=u.email
 AND i.inviter_id<>u.id AND i.status='pending' AND i.expires_at>now()
 AND i.token_hash=current_setting('app.invite_hash',true) AND public.inviter_allowed(i.id))
$$;
CREATE FUNCTION accept_invited_grant(iid uuid) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE inv public.invitations; gid uuid:=gen_random_uuid();
BEGIN
 SELECT * INTO inv FROM public.invitations WHERE id=iid;
 IF NOT FOUND OR NOT public.accepting_scope(inv.org_unit_id)
 OR inv.token_hash IS DISTINCT FROM current_setting('app.invite_hash',true) THEN
  RAISE insufficient_privilege;
 END IF;
 INSERT INTO public.role_grants(id,user_id,institution_id,org_unit_id,role,status,capabilities,
 ceiling,version) VALUES(gid,public.actor_id(),inv.institution_id,inv.org_unit_id,inv.role,'active',
 inv.capabilities,'advisor',1);
 PERFORM set_config('app.accepting',gid::text,true);
 RETURN gid;
END $$;
CREATE POLICY accepting_advisors ON role_grants FOR SELECT TO advisory_app
 USING(role='advisor' AND public.accepting_scope(org_unit_id));
CREATE POLICY accepting_users ON users FOR SELECT TO advisory_app USING(EXISTS(
 SELECT 1 FROM public.role_grants g WHERE g.user_id=users.id AND g.role='advisor'
 AND public.accepting_scope(g.org_unit_id)));
CREATE POLICY own_advisor_identity ON users FOR SELECT TO advisory_app USING(EXISTS(
 SELECT 1 FROM public.advisor_assignments a JOIN public.student_memberships m
 ON m.id=a.student_membership_id JOIN public.role_grants g ON g.id=a.advisor_grant_id
 WHERE g.user_id=users.id AND m.user_id=public.actor_id() AND a.ended_at IS NULL
 AND public.can_student(m.id)));
CREATE FUNCTION advisor_load(gid uuid) RETURNS integer LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE result integer; BEGIN
 SELECT count(*) INTO result FROM public.advisor_assignments a
 JOIN public.student_memberships m ON m.id=a.student_membership_id
 WHERE a.advisor_grant_id=gid AND a.ended_at IS NULL AND public.effective_grant(m.grant_id);
 RETURN result;
END $$;
-- An account remains capable of self-service after membership changes, never after suspension.
CREATE FUNCTION reconcile_grant_relations() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
 IF NEW.status<>'active' AND OLD.status='active' THEN
  UPDATE public.advisor_assignments SET ended_at=now() WHERE ended_at IS NULL AND (
   advisor_grant_id=NEW.id OR student_membership_id IN (
    SELECT id FROM public.student_memberships WHERE grant_id=NEW.id));
 END IF;
 RETURN NULL;
END $$;
CREATE TRIGGER reconcile_grants AFTER UPDATE ON role_grants
 FOR EACH ROW EXECUTE FUNCTION reconcile_grant_relations();
CREATE FUNCTION own_advisor_grant(gid uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
 SELECT EXISTS(SELECT 1 FROM public.advisor_assignments a JOIN public.student_memberships m
 ON m.id=a.student_membership_id WHERE a.advisor_grant_id=gid AND a.ended_at IS NULL
 AND m.user_id=public.actor_id() AND public.can_student(m.id))
$$;
CREATE POLICY own_advisor ON role_grants FOR SELECT TO advisory_app USING(public.own_advisor_grant(id));
