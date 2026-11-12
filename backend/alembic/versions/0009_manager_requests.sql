CREATE OR REPLACE FUNCTION can_action(action text, scope uuid) RETURNS boolean
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
