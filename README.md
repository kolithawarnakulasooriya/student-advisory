# Student Advisory

Release 0.3 provides a local Next.js/FastAPI application with synthetic registration and verification, revocable cookie sessions, scoped staff workflows, versioned student onboarding and private document intake. PostgreSQL with pgvector is the source of truth. No real student records, live identity provider, advising answers, or cloud resources are used.

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

New synthetic accounts use a `.test` email and display name. The local simulator displays an expiring verification challenge instead of sending email. Verification grants no membership; new accounts remain awaiting membership until authorized staff approve or an authorized invitation is accepted. No password or real MFA factor is collected. Production configurations fail closed because live identity integration is not implemented.

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

## Postman API collection

Import the [backend collection](postman/Student-Advisory.postman_collection.json) and [local environment](postman/Local.postman_environment.json). See the [Postman guide](postman/README.md) for the runnable smoke folder, CSRF/session automation and staff workflow examples.

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

Release 0.2 implements invitations, membership approvals, assignment authorization, scoped administrative audit, and staff workflows for the current resource surfaces. Student records, retrieval, chat, forms, and signatures remain later-release work. Institutional identity, privacy, retention, signatures, and cloud/model decisions must be resolved before real data. Synthetic verification and tests do not establish institutional approval, academic correctness, legal sufficiency, or production performance.

## Release 0.2 staff workflows

The local app now includes scoped invitations, requests/approvals, secretary delegation, membership lifecycle, advisor assignments, student summaries, and append-only administrative audit. Live identity and real email remain unavailable.

After upgrading an existing checkout, run `uv sync --project backend --frozen`, `docker compose up -d --wait`, then the documented Alembic upgrade and synthetic seed commands. Existing records are retained. Seed setup never silently creates platform-level authority.

Bootstrap the first platform super admin explicitly, once, from backend:

```bash
uv run python -m app.bootstrap --email super-admin@advisory.test --confirm-database advisory_dev
```

This requires an existing verified active synthetic identity, writes an operator bootstrap audit event, and permanently disables normal bootstrap afterward. Repeating it fails intentionally. The disposable full reset creates a new synthetic environment and resets the bootstrap latch; it is not a production recovery mechanism.

Run the invitation delivery worker in a third app terminal, from backend:

```bash
uv run python -m app.mail_worker
# Or process one eligible delivery and exit:
uv run python -m app.mail_worker --once
```

Mailpit captures local email at `http://localhost:8025`; SMTP listens only on loopback port 1025. No SMTP relay is configured. Invitation links put their one-use token in a URL fragment, which the app consumes into memory and removes. Do not paste tokens into logs. Resend invalidates the previous token. The application stores hashes, not plaintext invitation tokens; the local email inbox necessarily contains the delivered link.

Staff walkthrough:

1. Register and verify a new synthetic student. Open **Request a membership**, choose a department and role, and submit a justification.
2. Sign in as manager and simulate staff MFA. Choose an eligible advisor and enter a reason before approving a student. The student grant, membership, and primary assignment commit together.
3. Use **Invitations** to issue a local email, then open the captured link as its target identity and accept after verification.
4. **Memberships** shows enrollment metadata, delegation, lifecycle controls, capacity, and assignments. Secretary capabilities are explicit and never include student summaries. Student reactivation requires both membership-management and assignment permission, plus an eligible advisor.
5. Advisors see only assigned students under **Students**. Reassignment removes former-advisor access immediately on subsequent API requests; open tabs clear affected state on their next focus/30-second authorization refresh.
6. Bootstrapped super admins use **Users** and an explicit oversight purpose for global search, account state, and administrator appointments. Account reactivation alone restores no grants; approve suspended staff grants explicitly or reactivate individual student memberships with an advisor. Platform grants require their own explicit restoration.
7. **Audit** and user/advisor timelines show authorized metadata and separately protected operational reasons. Historical participation never grants current student-record access.

The `secretary` synthetic fixture has four explicit student-operations delegations. `secretary-no-delegation` has none. The legacy department-level `super-admin` fixture has no global authority until bootstrap. Existing platform-admin fixtures likewise require explicit capability delegation; role labels are insufficient.

All mutation handlers require CSRF, recent authentication, idempotency keys, and revision checks where applicable. The UI handles these through the generated OpenAPI client. SMTP delivery retries reuse the same one-use invitation, but a crash after SMTP acceptance can repeat an email. The local workflow write lock deliberately serializes approvals, authority changes, capacity, and delivery; no production throughput claim is made.

Browser tests explicitly bootstrap the disposable platform fixture through the operator path and process invitation mail locally. PostgreSQL tests remain isolated in `advisory_test`. See [Release 0.2 evidence and limitations](docs/RELEASE_0_2.md).

## College and department administration (T061)

After upgrading, run `uv run alembic upgrade head` from backend. Bootstrapped super admins receive the **College and department administration** workspace after simulated MFA. Create colleges/departments, explicitly open request enrollment, and separately appoint a manager. Organization creation grants no memberships or records access.

Super admins can delegate organization metadata management to a verified synthetic account at an explicit institution or college root, even when it has no department membership. Delegates cannot appoint managers, view student records, or redelegate by virtue of that grant. Existing platform-admin labels confer no organization-management authority.

Archive only empty units with no active memberships or active children. Archival closes enrollment, cancels invitations/delivery and retains history; restore leaves requests closed. Account suspension also suspends organization grants; restoring the account alone does not restore those grants. See the [T061 walkthrough and acceptance record](docs/T061_HANDOFF.md) and [organization contract](docs/decisions/organization-contract.md).


## Release 0.3 onboarding and document intake

After the normal setup, run `uv run alembic upgrade head` and the existing seed command from backend. Migrations preserve current records; seeding adds synthetic onboarding schemas without overwriting configured schemas or student profiles. Restart the API and frontend to load the new release.

Managers use **Onboarding configuration** to configure questions, valid programs/tracks, catalogs and terms. Students use **Academic profile** to save a draft, resume, review, confirm their catalog and complete setup. Advisors review facts through append-only confirmations/disputes. Required choices are synthetic examples, not institutional requirements.

Staff use **Documents** to upload PDF/DOCX/text/Markdown or paste text. Students can read their own clean documents; they cannot upload. Staff see scoped progress, failure explanations, metadata revisions, replacement, retry and archive actions. Extracted content ends at **needs review**; publishing and advising answers remain Release 0.4 work.

Build the actual scanner/parser image and initialize its signatures from the repository root:

```bash
docker compose build scanner-update
python3 scripts/update_scanner.py
```

Repeat the signature update periodically (at most hourly, respecting the upstream CDN). All three signature databases must be verified; unsuccessful updates retain the prior freshness marker. Processing fails closed if signatures are missing or older than 48 hours. The initial download needs internet access and can be rate limited; document containers have no network access. Docker must have enough memory for a 2 GiB scanner container.

Run the trusted host worker in another terminal:

```bash
cd backend
uv run python -m app.ingest_worker
# Or claim/process one eligible job:
uv run python -m app.ingest_worker --once
```

Private objects default to `local-data/intake`; signatures default to `local-data/clamav`. They are untracked and must stay outside frontend/public. Do not give the API Docker credentials/socket access. See [intake decisions and limits](docs/decisions/intake-contract.md).

Run real scanner/extraction/OCR tests after building and updating:

```bash
cd backend
RUN_PARSER_TESTS=1 uv run pytest tests/test_parser.py -q
```

Ordinary pytest explicitly skips these three external-tool tests; CI enables them separately. Mocked worker tests are additional database/authorization coverage, not extraction evidence. To preserve existing development servers during browser checks, use separate ports:

```bash
cd frontend
ADVISORY_E2E_API_PORT=8100 ADVISORY_E2E_WEB_PORT=3100 npm run test:e2e
```

See [Release 0.3 acceptance evidence](docs/RELEASE_0_3.md) for delivered requirements and limitations.
