"""Foundation schema and enforced local identity/application boundaries."""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Immutable baseline: never import live ORM metadata into a released migration.
    op.execute(SCHEMA_SQL)
    op.execute("""
    CREATE FUNCTION validate_org() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name = NEW.timezone) THEN
        RAISE EXCEPTION 'Invalid timezone' USING ERRCODE='23514';
      END IF;
      IF NEW.kind = 'college' AND NEW.parent_id IS NOT NULL THEN
        RAISE EXCEPTION 'College must be a root' USING ERRCODE='23514';
      END IF;
      IF NEW.kind = 'department' AND (NEW.parent_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM org_units p WHERE p.id=NEW.parent_id
        AND p.institution_id=NEW.institution_id AND p.kind='college')) THEN
        RAISE EXCEPTION 'Department requires a college in its institution' USING ERRCODE='23514';
      END IF;
      IF TG_OP = 'UPDATE' AND (NEW.kind <> OLD.kind OR NEW.institution_id <> OLD.institution_id)
        AND EXISTS (SELECT 1 FROM org_units WHERE parent_id=OLD.id) THEN
        RAISE EXCEPTION 'Parent type and institution are immutable while children exist'
          USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER org_hierarchy BEFORE INSERT OR UPDATE ON org_units
      FOR EACH ROW EXECUTE FUNCTION validate_org();
    GRANT USAGE ON SCHEMA public TO advisory_app, advisory_auth;
    GRANT SELECT ON users, role_grants, institutions, org_units TO advisory_app;
    GRANT SELECT, INSERT, UPDATE ON users, sessions, verifications TO advisory_auth;
    """)
    for table in ("institutions", "org_units", "users", "role_grants", "sessions", "verifications"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("""
    CREATE POLICY own_user ON users TO advisory_app
      USING (id::text = current_setting('app.user_id', true));
    CREATE POLICY identity_user ON users TO advisory_auth
      USING (id::text = current_setting('app.user_id', true)
        OR email = current_setting('app.login_email', true))
      WITH CHECK (id::text = current_setting('app.user_id', true)
        AND email LIKE '%%.test');
    CREATE POLICY own_grants ON role_grants TO advisory_app
      USING (user_id::text = current_setting('app.user_id', true));
    CREATE POLICY identity_sessions ON sessions TO advisory_auth
      USING (token_hash = current_setting('app.session_hash', true)
        OR user_id::text = current_setting('app.user_id', true))
      WITH CHECK (token_hash = current_setting('app.session_hash', true)
        AND (user_id IS NULL OR user_id::text = current_setting('app.user_id', true)));
    CREATE POLICY identity_verifications ON verifications TO advisory_auth
      USING (user_id::text = current_setting('app.user_id', true))
      WITH CHECK (user_id::text = current_setting('app.user_id', true));
    CREATE POLICY authorized_orgs ON org_units TO advisory_app USING (
      EXISTS (SELECT 1 FROM role_grants g JOIN users u ON u.id=g.user_id
        WHERE g.org_unit_id=org_units.id AND g.institution_id=org_units.institution_id
        AND g.user_id::text=current_setting('app.user_id', true)
        AND g.status='active' AND (g.valid_until IS NULL OR g.valid_until > now())
        AND u.verified AND u.status='active')
      AND (current_setting('app.mfa', true) = 'true' OR NOT EXISTS (
        SELECT 1 FROM role_grants g WHERE g.user_id::text=current_setting('app.user_id',true)
        AND g.status='active' AND (g.valid_until IS NULL OR g.valid_until > now())
        AND g.role <> 'student')));
    CREATE POLICY authorized_institutions ON institutions TO advisory_app USING (
      EXISTS (SELECT 1 FROM org_units o WHERE o.institution_id=institutions.id));
    """)


def downgrade() -> None:
    raise RuntimeError("Use the guarded disposable reset; no destructive downgrade is provided")


SCHEMA_SQL = """
CREATE TABLE institutions (
	id UUID NOT NULL,
	code VARCHAR(80) NOT NULL,
	name VARCHAR NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (code)
);
CREATE TABLE users (
	id UUID NOT NULL,
	issuer VARCHAR NOT NULL,
	subject VARCHAR NOT NULL,
	email VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	verified BOOLEAN NOT NULL,
	status VARCHAR NOT NULL,
	grant_epoch INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (issuer, subject),
	CHECK (status IN ('active','suspended','revoked')),
	UNIQUE (email)
);
CREATE TABLE org_units (
	id UUID NOT NULL,
	institution_id UUID NOT NULL,
	parent_id UUID,
	code VARCHAR(80) NOT NULL,
	name VARCHAR NOT NULL,
	kind VARCHAR NOT NULL,
	timezone VARCHAR NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (institution_id, code),
	UNIQUE (institution_id, id),
	FOREIGN KEY(institution_id, parent_id) REFERENCES org_units (institution_id, id),
	CHECK (kind IN ('college', 'department')),
	CHECK (parent_id IS NULL OR parent_id <> id),
	FOREIGN KEY(institution_id) REFERENCES institutions (id)
);
CREATE TABLE sessions (
	id UUID NOT NULL,
	user_id UUID,
	token_hash VARCHAR(64) NOT NULL,
	csrf_hash VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	last_seen TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	auth_time TIMESTAMP WITH TIME ZONE,
	mfa BOOLEAN NOT NULL,
	revoked BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id),
	UNIQUE (token_hash)
);
CREATE TABLE verifications (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	used BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id),
	UNIQUE (token_hash)
);
CREATE TABLE role_grants (
	id UUID NOT NULL,
	user_id UUID NOT NULL,
	institution_id UUID NOT NULL,
	org_unit_id UUID NOT NULL,
	role VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	valid_until TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	FOREIGN KEY(institution_id, org_unit_id) REFERENCES org_units (institution_id, id),
	UNIQUE (user_id, org_unit_id, role),
	CHECK (role IN ('student','advisor','secretary','manager','platform_admin','super_admin')),
	CHECK (status IN ('invited','pending','active','suspended','rejected','revoked')),
	FOREIGN KEY(user_id) REFERENCES users (id)
);
"""
