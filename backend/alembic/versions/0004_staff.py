"""Additive staff workflow schema, permissions and append-only audit."""

from pathlib import Path

from alembic import op

revision = "0004_staff"
down_revision = "0003_identity_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    directory = Path(__file__).parent
    op.execute("""
    DO $$ BEGIN
     IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='advisory_policy') THEN
      CREATE ROLE advisory_policy NOLOGIN NOSUPERUSER NOBYPASSRLS;
     END IF;
     IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='advisory_mail') THEN
      CREATE ROLE advisory_mail LOGIN PASSWORD 'local-mail-only' NOSUPERUSER NOBYPASSRLS;
     END IF;
    END $$;
    GRANT USAGE ON SCHEMA public TO advisory_policy,advisory_mail;
    """)
    op.execute((directory / "0004_staff_schema.sql").read_text())
    for table in [
        "audit_events",
        "idempotency_records",
        "outbox_events",
        "platform_control",
        "platform_grants",
        "enrollment_options",
        "membership_requests",
        "invitations",
        "student_memberships",
        "advisor_assignments",
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("""
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO advisory_policy;
    GRANT INSERT ON role_grants TO advisory_policy;
    GRANT UPDATE ON users,sessions,student_memberships,advisor_assignments TO advisory_policy;
    GRANT SELECT,INSERT,UPDATE ON role_grants,student_memberships,advisor_assignments,
      membership_requests,invitations,platform_grants,idempotency_records,outbox_events
      TO advisory_app;
    GRANT SELECT ON enrollment_options TO advisory_app;
    GRANT SELECT,INSERT ON audit_events TO advisory_app;
    GRANT USAGE ON SEQUENCE audit_events_id_seq TO advisory_app;
    GRANT SELECT,UPDATE ON invitations,outbox_events TO advisory_mail;
    """)
    op.execute((directory / "0004_staff_policy.sql").read_text())
    # Functions have a fixed search_path and only narrowly specified entry points are callable.
    functions = [
        "actor_id()",
        "actor_live()",
        "platform_admin()",
        "effective_grant(uuid)",
        "can_action(text,uuid)",
        "can_student(uuid)",
        "can_user(uuid)",
        "can_grant(text,uuid,uuid)",
        "grant_parameters_ok(text,text[],text)",
        "related_student_grant(uuid)",
        "grant_epoch_changed()",
        "platform_epoch_changed()",
        "assignment_epoch_changed()",
        "assignment_valid()",
        "current_session_live()",
        "update_account(uuid,text)",
        "revoke_actor_sessions(uuid)",
        "inviter_allowed(uuid)",
        "accepting_scope(uuid)",
        "accept_invited_grant(uuid)",
        "advisor_load(uuid)",
        "reconcile_grant_relations()",
        "own_advisor_grant(uuid)",
    ]
    for function in functions:
        op.execute(f"ALTER FUNCTION {function} OWNER TO advisory_policy")
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {function} TO advisory_app")
    op.execute("GRANT EXECUTE ON FUNCTION inviter_allowed(uuid) TO advisory_mail")


def downgrade() -> None:
    raise RuntimeError("Preserve staff history; use forward migrations")
