-- Local-only disposable credentials. Runtime roles cannot own tables or bypass RLS.
CREATE ROLE advisory_app LOGIN PASSWORD 'local-app-only' NOSUPERUSER NOBYPASSRLS;
CREATE ROLE advisory_auth LOGIN PASSWORD 'local-auth-only' NOSUPERUSER NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
