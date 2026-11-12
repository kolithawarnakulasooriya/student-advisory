"""Constrain intake states and schema department bindings."""

from alembic import op

revision = "0014_intake_guards"
down_revision = "0013_intake_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION intake_binding_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog,public AS $$
    BEGIN
     IF TG_TABLE_NAME='onboarding_configs' AND NEW.active_schema_id IS NOT NULL THEN
      IF NOT EXISTS(SELECT 1 FROM public.onboarding_schemas s
       WHERE s.id=NEW.active_schema_id AND s.org_unit_id=NEW.id) THEN
       RAISE EXCEPTION 'Invalid schema binding' USING ERRCODE='23514'; END IF;
     END IF;
     RETURN NEW;
    END $$;
    ALTER FUNCTION intake_binding_guard() OWNER TO advisory_policy;
    REVOKE ALL ON FUNCTION intake_binding_guard() FROM PUBLIC;
    CREATE TRIGGER schema_binding BEFORE INSERT OR UPDATE ON onboarding_configs
     FOR EACH ROW EXECUTE FUNCTION intake_binding_guard();
    ALTER TABLE profile_versions ADD CHECK(status IN ('draft','complete'));
    ALTER TABLE sources ADD CHECK(visibility IN ('student','department','college','institution'));
    ALTER TABLE ingestion_jobs ADD CHECK(state IN
     ('uploaded','scanning','extracting','needs_review','failed','cancelled'));
    ALTER TABLE ingestion_jobs ADD CHECK(attempt BETWEEN 1 AND 3);
    ALTER TABLE source_versions ADD CHECK(version > 0);
    ALTER TABLE profile_versions ADD CHECK(version > 0);
    """)


def downgrade() -> None:
    raise RuntimeError("Preserve intake history; use forward migrations")
