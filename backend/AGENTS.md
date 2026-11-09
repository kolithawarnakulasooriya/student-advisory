# Backend instructions

Read ../AGENTS.md, ../docs/ACCESS_CONTROL.md, ../docs/RAG_DESIGN.md, and ../docs/API_AND_EVENTS.md. Use FastAPI, Pydantic validation, SQLAlchemy transactions, Alembic migrations, and PostgreSQL. Implement explicit service modules for memberships, profiles, sources, retrieval, chat, cases, forms, and outbox.

Authenticate issuer/audience/expiry and immutable identity subject. Build AuthContext from verified identity plus active grants in the database. Never trust requested student ID, department, model endpoint, role, or source scope without checking the actor. Use consistent not-found responses for inaccessible objects where appropriate. Bulk operations and search counts need the same scope restrictions as detail views.

Implement a central authorize(actor, action, resource) interface plus query scopes; check permissions in service handlers and worker consumers. Configure RLS under a non-owner DB role, transaction-local scope, and explicit privileged-job roles. Test pooled-connection reuse. Inference has no authority to approve, assign, email, or sign.

RAG retrieval must constrain institution, department/college grants, student ID for private sources, publication, catalog, and validity before top-k and reranking. Include ACL/version epochs in context and revalidate before output commit. A model adapter uses a configured internal URL and alias; redact prompts from telemetry. Bound token counts, queues, retries, and timeouts. Handle vLLM unavailable without fabricating an answer.

Use discriminated message types. Student question → generation job. Student-visible advisor guidance → persist guidance and notification only. Staff-only note → staff storage only. Explicit advisor draft → staff-only inference result. Use active guidance to resolve planning preferences, while validated policy constraints remain binding.

Store immutable source versions, profile versions, plan versions, and form revisions. Use a DB transaction for form state plus signature plus outbox. Enforce signer eligibility, current revision, recent auth, consent, sequence, idempotency, and database uniqueness. Material changes create a new revision and signature sequence. Never mutate a signed payload.

Workers use idempotent events and reauthorize current scope; use an outbox for all outbound notifications. File processors run with resource/time limits, no arbitrary network, no shell evaluation of filenames, and private storage. Withdrawal stops retrieval before physical deletion.

Implement unit and database integration tests for access policies, retrieval filters, race conditions, stale signatures, outbox retries, and assignment changes. Use a real pgvector Postgres test container when checking SQL isolation. SQLite is not a substitute for RLS or concurrency tests.

Planned commands after scaffolding: uv sync --frozen; uv run ruff check .; uv run mypy app; uv run pytest; uv run alembic upgrade head against a disposable test database. Create pinned project config and tests first. No backend app or dependency lockfile exists in this specification package.
