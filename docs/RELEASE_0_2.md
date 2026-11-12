# Release 0.2 — Role permissions and staff workflows

Local synthetic implementation record, November 11, 2026. No real institutional identity, student records, or external email provider is used.

## Requirements and implementation

T011–T017 implement the current release surfaces for PRD ID-01–ID-07 and sections 3, 11–13, and 16. T018 includes relationship/permission epochs and browser invalidation; T036 includes transactional invitation delivery. Their later generation, streaming, cloud-publishing, and general-notification work remains open. T002/T003 retain later-release contract and academic-fixture work.

| Area | Implementation |
| --- | --- |
| Authorization and state | `backend/app/security.py`, `memberships.py`, `assignments.py`, `staff_security.py`, `staff_services.py`, `staff_routes.py`: current grants, role ceilings, explicit delegation, protected student summaries, scoped projections, recent auth, immutable grant binding, idempotency and revision checks |
| Data and policies | `backend/app/models.py`, additive migrations 0004–0009 and frozen SQL assets: membership/request/invitation/assignment/audit/outbox/platform tables, forced RLS, non-owner roles, cross-scope foreign keys, append-only audit, protected operational reasons |
| Lifecycle and bootstrap | `backend/app/bootstrap.py`: explicit audited operator bootstrap; subsequent appointments require a super admin. Serialized workflows protect the last active admin and advisor capacity. Whole-account suspension revokes sessions and effective grants together |
| Local mail | `backend/app/mail_worker.py`, Compose, local settings: digest-pinned Mailpit, no external relay, hash-only application token storage, current issuer reauthorization, bounded SMTP retry, column-limited mail role |
| UI and contract | `frontend/app/staff-workspace.tsx`, account shell, `frontend/lib/staff-api.ts`, OpenAPI/generated types: requests, invitations/acceptance, enrollment/assignment controls, delegation/capacity, student summaries, global oversight and audit/history |
| Validation and setup | PostgreSQL integration/concurrency/permission tests, component/browser scenarios, locked dependencies, CI Mailpit service, README and task/decision updates |

## Important boundaries

- Organization metadata remains grant-scoped. Verified accounts can discover only explicitly enabled enrollment options through a separate interface.
- Students are identified by student membership IDs. Secretary projections contain enrollment metadata; protected summary routes independently reject secretaries and unassigned/former advisors.
- Authentication bookkeeping commits before business transactions acquire locks. Workflow transactions recheck current session/account/grant state. This avoids retaining an auth-session lock during cross-connection session revocation.
- Application and identity roles own no tables and have no BYPASSRLS. A NOLOGIN policy role owns fixed-search-path permission helpers and narrow trigger/lifecycle routines. The invitation worker cannot read user/student tables, modify invitation authority, or change role grants.
- Mutations require CSRF, recent authentication, an idempotency key, and If-Match where state can become stale. Business state, successful audit, operational-reason references, and relevant outbox records commit together. Denials persist in a separate append-only transaction after rollback.
- Cursor signatures bind actor, route, scope, purpose, page size, filter and permission epoch. Counts use the same authorized query as rows.
- The local write lock serializes current workflows, capacity checks, last-admin checks and bounded SMTP delivery. This is a correctness-first local default, not a load/performance result.
- Audit rows contain structured metadata and protected rationale references, not copied request bodies, invitation tokens, prompts, or transcripts. Runtime append-only permissions do not make the store tamper-proof against its database owner.

## Migration compatibility

Existing identities, grants, sessions and synthetic records are retained. Student grants are backfilled into matching membership rows without invented historical approvals. Existing per-department super-admin labels are never converted into global authority. Explicit synthetic setup adds initial fixture assignments; subsequent seeds preserve existing assignment history and changed delegations.

New outbox event types include invitation.send, invitation.accepted, membership.requested, membership.decided, membership.activated, membership.changed, and assignment.changed. Only invitation.send is delivered in 0.2; other events are durable metadata for future publisher work, not claimed notifications. No event contains record content or permission-bearing payloads.

## Verification

Observed local results:

| Check | Result |
| --- | --- |
| Backend `uv run ruff check .`, `uv run mypy app` | Passed; 19 application modules type checked |
| Backend `uv run pytest -q` | 85 passed against real PostgreSQL/pgvector, including foundation regressions |
| Fresh disposable database migration through 0009 and runtime-role/extension smoke | Passed; existing development database also upgraded additively |
| `uv run alembic check`, `uv run python -m app.contracts --check` | Passed; no schema or OpenAPI drift |
| Frontend lint/typecheck and `npm run test` | Passed; 14 component tests |
| `npm run test:e2e` | 23 Chromium journeys passed |
| `npm run check-client`, `npm run build` | Passed; generated client matches and production build succeeds |
| `npm audit --audit-level=moderate` | Zero vulnerabilities reported |
| `uvx pip-audit -r /tmp/advisory-release02-requirements.txt --disable-pip --no-deps` against the fully pinned `uv export --frozen` dependency graph | No known vulnerabilities reported |
| `python3 scripts/validate_package.py` | 235 checks passed; five workflows, 24 synthetic seed cases, six rule examples |
| `git diff --check` and generated-secret scan | Passed; no generated local signing key in project source or built browser assets |

Backend scenarios exercise role/scope/state matrices; no-context RLS and non-owner permissions; atomic activation, simultaneous duplicate approval/acceptance with exactly one effect, and advisor capacity races; simultaneous last-admin removal; rollback-safe denial history and append restrictions; single-use invitation tokens, rotation, expiry and issuer revocation; Mailpit inbox delivery and SMTP retries; delegation ceilings; student membership foreign keys; and relationship-cache epochs. Anonymous route tests also verify that denial logging needs no anonymous audit-read privilege.

Browser evidence covers student request → advisor-backed activation, invitation → registration/verification → acceptance, manager request → super-admin approval, secretary enrollment-only controls, former-advisor revocation, account suspension across an open session, explicit reactivation without restored grants, session recovery, sign-out, backend failure, empty browser storage and token removal, and keyboard/layout checks at 360/768/1280 px. Logout tests wait for its confirmed response before navigating. Reference selectors and platform grants also use bounded signed cursor pages. Manual manager screenshots at 1280/360 px were inspected, with populated workflow rows and no horizontal overflow. Local liveness, readiness and Mailpit UI returned HTTP 200.

All fixture identities, operational justifications and email are synthetic. Backend tests use a separate disposable PostgreSQL database; E2E uses the documented local development environment and an explicit operator bootstrap fixture step. Seed repetition preserves ended assignment history and intentionally changed delegations. A FastAPI test-client deprecation warning remains; it does not fail the locked checks.

## Remaining limitations

Live identity, real email/MFA, cloud deployment and real student records remain unavailable; production configuration is rejected. Full academic profiles, uploads, retrieval, chat, guidance, forms, signatures, general notifications, job cancellation and streaming authorization remain later releases. Existing viewed content cannot be unread; server revocation applies immediately to subsequent requests, while browser state clears on its next authorization refresh.

Invitations default to 48 hours. SMTP retries may repeat a message after a crash, but the link remains one-use. Mailpit necessarily holds the synthetic delivered email/link. Capacity defaults to unconfigured for synthetic fixtures; institutional capacity policy is unresolved. Full screen-reader/WCAG and non-Chromium browser assessment are not claimed. GitHub Actions is defined; hosted execution is not claimed without observed evidence.

See [setup and staff walkthrough](../README.md) and [institutional dependencies](decisions/pilot-inputs.md).
