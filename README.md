# Student Advisory

Release 0.1 provides a local Next.js/FastAPI application with synthetic registration and verification, revocable cookie sessions, role landing pages, and server-enforced organization scope. PostgreSQL with pgvector is the source of truth. No real student records, live identity provider, advising answers, or cloud resources are used.

## Run locally

Prerequisites: Docker with Compose, Node 22.19+ (see `.nvmrc`), Python 3.14, and uv 0.13.7. Start Docker before the database command. The database binds only to loopback.

From the repository root:

```bash
python3 scripts/dev_env.py
docker compose up -d --wait
uv sync --project backend --frozen
```

In the backend terminal:

```bash
cd backend
uv run alembic upgrade head
uv run python -m app.seed seed --confirm-database advisory_dev
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000` (use localhost, not 127.0.0.1, to match the configured Origin). The frontend proxies `/api` to FastAPI. Health endpoints are `/api/v1/health/live` and `/api/v1/health/ready`. Configuration creation never overwrites an existing `.env`, and generates a local random signing key without printing it. Never commit `.env` or real credentials. The committed database passwords are disposable local fixtures only.

Choose a predefined account in the UI. Students A/B belong to separate departments. Staff accounts require an explicit **Simulate staff MFA** action. The multi-role account advises in A and manages B. Pending, unverified, suspended, and revoked identities exercise denial/recovery states. All fixture addresses end in `@advisory.test`.

New synthetic accounts use a `.test` email and display name. The local simulator displays an expiring verification challenge instead of sending email. Verification grants no membership; new accounts remain awaiting membership until approval workflows arrive in Release 0.2. No password or real MFA factor is collected. Production configurations fail closed because live identity integration is not implemented.

## Checks

Backend:

```bash
cd backend
uv run ruff check .
uv run mypy app
uv run alembic check
uv run pytest
uv run python -m app.contracts --check
```

Database tests create/migrate/reset only the loopback `advisory_test` database, using the Compose migration identity. Runtime roles are separate non-owner identities without BYPASSRLS. Tests exercise real PostgreSQL policies and pool reuse; SQLite is not used.

Frontend:

```bash
cd frontend
npm ci
npm run check-client
npm run lint
npm run typecheck
npm run test
npm run build
npx playwright install chromium
npm run test:e2e
```

E2E tests start/reuse the loopback API and frontend and use the seeded `advisory_dev` database. They add clearly synthetic registration fixtures. Do not edit application files during a browser run: development-server restarts interrupt journeys. Run build/type generation before E2E, not concurrently with it.

Package integrity, from the repository root:

```bash
uv run --project backend python scripts/validate_package.py
```

After changing API schemas, run `uv run python -m app.contracts` from backend and `npm run generate-client` from frontend. Commit both generated snapshots. CI checks reproducibility and generated-contract drift. Next.js manages `next-env.d.ts`; typecheck runs `next typegen` before TypeScript.

## Disposable data and shutdown

```bash
# From backend; refuses non-loopback/non-disposable database targets.
uv run python -m app.seed reset --confirm-database advisory_dev
```

This resets only the known local synthetic tables and reseeds fixtures; it preserves migrations. Stop app terminals with Ctrl-C. Run `docker compose stop` from the root to stop PostgreSQL while retaining its disposable volume. No cloud resources or GPU workloads are started.

## Requirements and delivery

- [Release plan](docs/RELEASE_PLAN.md), [detailed tasks](docs/TASKS.md), and [implementation backlog](docs/IMPLEMENTATION_BACKLOG.md)
- [Release 0.1 validation and handoff](docs/RELEASE_0_1.md)
- [Product requirements](docs/PRD.md), [access control](docs/ACCESS_CONTROL.md), and [API/event contracts](docs/API_AND_EVENTS.md)
- [Foundation contract](docs/decisions/foundation-contract.md), [role decisions](docs/decisions/roles.md), [test data](docs/decisions/test-data.md), and [pilot dependencies](docs/decisions/pilot-inputs.md)
- [RAG design](docs/RAG_DESIGN.md), [cloud guide](docs/GOOGLE_CLOUD_DEVELOPMENT.md), and [source register](docs/SOURCES.md)

Release 0.2 owns invitations, membership approvals, assignment/relationship authorization, administrative audit, and complete role workflows. Student records, retrieval, chat, forms, and signatures remain later-release work. Institutional identity, privacy, retention, signatures, and cloud/model decisions must be resolved before real data. Synthetic verification and tests do not establish institutional approval, academic correctness, legal sufficiency, or production performance.
