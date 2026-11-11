"""Prevent mutation of an established identity binding."""

from alembic import op

revision = "0003_identity_binding"
down_revision = "0002_access_epochs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION immutable_identity() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.id <> OLD.id OR NEW.issuer <> OLD.issuer OR NEW.subject <> OLD.subject THEN
        RAISE EXCEPTION 'Identity binding is immutable' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER immutable_identity_binding BEFORE UPDATE ON users
      FOR EACH ROW EXECUTE FUNCTION immutable_identity();
    """)


def downgrade() -> None:
    raise RuntimeError("Identity binding cannot be weakened by rollback")
