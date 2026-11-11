# Release 0.1 — Foundation and safe auth

Implementation and local verification record, November 11, 2026. Development is synthetic-only. This is not a production deployment or independent institutional approval.

## Requirements and changes

T005–T010 implement the PRD section 11–13 foundation and ID-01/ID-05 identity/session boundary. T001/T004 record default role ceilings and pilot dependencies. T002/T003/T011/T012 have explicitly completed foundation subsets; workflow contracts, academic fixtures, student relationships, and future-resource RLS remain outstanding.

| Area | Main files and behavior |
| --- | --- |
| API/configuration | `backend/app/main.py`, `config.py`, `schemas.py`: health/readiness, generic structured errors, server-generated correlation IDs, fail-closed local configuration |
| Identity/session | `backend/app/identity.py`, `security.py`: signed synthetic assertions, immutable issuer/subject, hashed cookie sessions/challenges, CSRF/Origin checks, expiry, logout, revocation, simulated staff MFA and recent-auth hooks |
| Database | `backend/app/models.py`, `db.py`, `alembic/versions/`: foundation schema, hierarchy/timezone constraints, non-owner roles, forced RLS, transaction-local context, grant epochs and account revocation |
| Fixtures/local runtime | `backend/app/seed.py`, `compose.yaml`, `infra/local/init.sql`, `.env.example`, `scripts/dev_env.py`: guarded disposable PostgreSQL/pgvector, deterministic fixtures, private untracked configuration |
| Browser | `frontend/app/`, `frontend/lib/`: typed same-origin account requests, verification and account recovery, capability-driven landing states, scope switching and cache/state invalidation |
| Contracts/tooling | `backend/contracts/openapi.json`, generated `frontend/lib/api-types.ts`, locked dependencies, tests, `.github/workflows/ci.yml`: reproducible checks and drift detection |
| Documentation | README, decisions, task/backlog/release tracking, nested instructions, package validator dependency/build-directory exclusions |

## Migration and contract compatibility

The three ordered migrations create the foundation tables/vector extension and forced RLS, then transactional epochs/revocation, then immutable identity binding. Migrations contain a frozen baseline; they do not import future ORM metadata. Destructive downgrades are intentionally unavailable. The guarded local reset truncates only the known synthetic tables and retains migration history.

The identity database role cannot access grants or organization tables. The application role can only read authorized foundation data. Readiness rejects superuser/BYPASSRLS/table-owner runtime roles and checks the protected schema. No source, student-record, event, job, export, form, or signature endpoint is implemented. Future releases must add authorization and RLS before exposing each new resource.

## Verification

All fixtures are synthetic. PostgreSQL tests used a separately recreated `advisory_test` database, and browser tests used `advisory_dev`.

| Actual command/check | Observed result |
| --- | --- |
| `uv sync --frozen` | Locked environment installed/verified |
| `uv run ruff check .` and `uv run mypy app` | Passed; 10 application modules checked |
| `uv run alembic upgrade head` and `uv run alembic check` | Fresh PostgreSQL migrations passed; no model/schema drift |
| `uv run python -m app.seed seed --confirm-database advisory_dev` | 14 predefined synthetic identities; repeatable seed verified in tests |
| `uv run pytest -q` | 54 passed; real PostgreSQL authorization, hierarchy, session, revocation, identity, CSRF, config, and pool-isolation scenarios |
| `uv run python -m app.contracts --check` | OpenAPI snapshot matches application |
| `npm ci` and `npm run check-client` | Locked frontend install and generated-client drift check passed |
| `npm run lint` and `npm run typecheck` | Passed; clean route type generation included |
| `npm run test` | 8 component behavior tests passed |
| `npm run build` | Optimized production build passed |
| `npm run test:e2e` | 14 Chromium journeys passed: six roles, new registration/verification, pending/unverified, scope switching, expiry, backend failure, keyboard/layout at 360/768/1280 px |
| `npm audit --audit-level=moderate` | Zero reported vulnerabilities |
| Generated local signing-key scan | Key absent from source and built browser assets; `.env` excluded and untracked |
| Package validator and Git whitespace checks | Passed; current package check count is recorded in docs/VALIDATION.md |

The initial browser run exposed a test selector collision with Next.js's route announcer and a development-server restart caused by source formatting. Those checks were corrected and the complete stable 14-test run passed. An initial backend RLS/autoflush ordering failure was fixed before the final database run. No failed check has been represented as passing without rerunning it.

## Limitations

- Live identity/OIDC integration, real email verification, and real MFA are not implemented. Every production configuration is rejected. Registration and step-up are visibly labeled local simulations.
- Membership requests, invitations, approval/administration UIs, advisor assignment relationships, administrative audit, and complete capability policy remain Release 0.2 work. No grants are created by registration or verification.
- Student onboarding, documents, retrieval, chat, advisor guidance, forms, signatures, inference, and cloud deployment remain later-release work.
- Browser checks cover Chromium keyboard/recovery/layout journeys; a screen-reader audit, other browser engines, and full WCAG conformance assessment have not been performed.
- GitHub Actions is defined but has not run on GitHub in this session. Local equivalents were executed; no cloud performance, recovery, or deployment claims are made.
- The pinned Starlette test client emits an HTTPX deprecation notice; current tests pass. ESLint's pinned major emits a support deprecation notice; lint passes. The development dependency override for minimatch is covered by lint and the zero-vulnerability npm audit.

Setup, reset, shutdown, generated-client updates, and runnable checks are in [README](../README.md). Institutional blockers are tracked in [pilot inputs](decisions/pilot-inputs.md).
