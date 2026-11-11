"""Keep grant epochs and account-wide session revocation transactional."""

from alembic import op

revision = "0002_access_epochs"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION grant_epoch_changed() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP IN ('UPDATE', 'DELETE') THEN
        UPDATE users SET grant_epoch = grant_epoch + 1 WHERE id=OLD.user_id;
      END IF;
      IF TG_OP='INSERT' OR (TG_OP='UPDATE' AND NEW.user_id <> OLD.user_id) THEN
        UPDATE users SET grant_epoch = grant_epoch + 1 WHERE id=NEW.user_id;
      END IF;
      RETURN NULL;
    END $$;
    CREATE TRIGGER grant_epoch AFTER INSERT OR UPDATE OR DELETE ON role_grants
      FOR EACH ROW EXECUTE FUNCTION grant_epoch_changed();
    CREATE FUNCTION identity_epoch_changed() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.status IS DISTINCT FROM OLD.status OR NEW.verified IS DISTINCT FROM OLD.verified THEN
        NEW.grant_epoch = OLD.grant_epoch + 1;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER identity_epoch BEFORE UPDATE ON users
      FOR EACH ROW EXECUTE FUNCTION identity_epoch_changed();
    CREATE FUNCTION revoke_account_sessions() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.status <> 'active' AND NEW.status IS DISTINCT FROM OLD.status THEN
        UPDATE sessions SET revoked=true WHERE user_id=NEW.id;
      END IF;
      RETURN NULL;
    END $$;
    CREATE TRIGGER account_revocation AFTER UPDATE ON users
      FOR EACH ROW EXECUTE FUNCTION revoke_account_sessions();
    """)


def downgrade() -> None:
    raise RuntimeError("No destructive downgrade; use compatible forward migrations")
