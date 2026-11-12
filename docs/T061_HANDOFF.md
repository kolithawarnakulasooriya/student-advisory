# T061 — College and department administration

Implemented after Release 0.2, before Release 0.3 onboarding. Requirements: T061, PRD sections 2–3/11–13 and the [organization contract](decisions/organization-contract.md). Only synthetic local identity/MFA and data are supported.

## Behavior and boundaries

Super admins create colleges/departments inside existing institutions and delegate metadata administration at an explicit institution or college root. Separate organization-administration grants work without a department membership. They never grant student records, manager appointment, invitations, or general audit. Delegates cannot redelegate. Existing department or platform-admin labels are never promoted.

New departments start closed to self-service requests. Closing requests leaves existing requests reviewable while the department is active. Archival rejects units with any active role membership or active descendant; retains identifiers, codes and history; closes enrollment; revokes outstanding invitations and cancels their delivery. Pending requests remain stored and cannot activate under archived units. Restore requires an active parent and leaves enrollment closed. Hard deletion, parent changes, institution creation and transfers remain unavailable.

Changes use non-owner roles, forced RLS, current transaction authority, simulated MFA/recent auth, CSRF, idempotency and revisions. The existing write lock serializes organization state with enrollment/activation and mail delivery. Database guards also enforce scope integrity, active organization state and archive prerequisites. Successful audits commit with business state; denial logs survive rollback. Organization history exposes only authorized organization metadata/reasons. Administrative delegation history remains restricted separately.

Account suspension suspends organization grants and revokes sessions transactionally. Account reactivation restores no organization authority; a super admin must explicitly reactivate the grant. Expired and revoked delegations fail subsequent requests. /me returns independent administration capabilities, own grants and visible institution metadata epochs; metadata/permission changes invalidate affected browser state and signed cursors.

## Files and migrations

| Surface | Files |
| --- | --- |
| Schema/RLS | backend/app/models.py; additive migrations 0010_organization_admin and 0011_organization_history, frozen SQL |
| API/services | backend/app/organizations.py, organization_schemas.py; main.py, schemas.py, security.py, staff_services.py, staff_routes.py, memberships.py |
| UI | frontend/app/organization-workspace.tsx; account shell/globals.css and generated API types |
| Tests | backend/tests/test_organizations.py; frontend/tests/organizations.test.tsx and account/staff fixture types; frontend/e2e/organizations.spec.ts and persistent-fixture recovery checks |
| Contracts/docs | OpenAPI, Postman generator/collection/environment, README, PRD, ACCESS_CONTROL, role decisions, release plan, TASKS and validation record |

Migrations preserve existing identities, accounts, operational grants, enrollment flags and history. Existing organizations backfill active with revisions; no organization-administration grants are backfilled. Repeated seeds do not restore ended assignments or changed delegations. Organization names stay synchronized with enrollment labels. Archived codes remain reserved.

## Local walkthrough

1. Follow the README migration/seed/start instructions. Bootstrap a super admin once if the environment has none.
2. Sign in as the bootstrapped super admin, simulate MFA, then open **College and department administration**. Select an institution and enter a reason.
3. Create a college; create a department under its active college. Open membership requests explicitly if desired.
4. Register/verify a synthetic target account. Find its exact email in the appointment panel. Appoint a department manager separately; organization creation itself appoints nobody.
5. To delegate metadata management, choose an explicit institution or college scope, verified target, optional expiry and reason. Sign in as the target and simulate MFA; its organization workspace works without a department grant. Verify that student summaries and manager appointments are denied.
6. Use a separate empty department to exercise close/archive/restore. Active memberships or active children block archival. Read organization history, then revoke delegation and refresh the affected session to observe removal.

Existing membership and invitation flows retain their advisor and role-ceiling checks. Creating a manager does not create an advisor; student activation still requires one. The local SMTP worker reauthorizes invitation authority and organization state at delivery.

## Observed checks

Observed local checks on November 11, 2026:

| Check | Result |
| --- | --- |
| Fresh disposable PostgreSQL migration through 0011, then backend suite | 107 tests passed (85 prior regressions plus 22 organization cases) |
| Backend Ruff/type checks and development schema drift | Passed; 21 application modules; no new upgrade operations |
| Frontend lint/type/component tests | Passed; 19 tests |
| Full Chromium E2E suite | 29 journeys passed, including six organization scenarios/layout checks |
| Final navigation/style and stale-history verification | Three organization keyboard/layout checks passed again at 360/768/1280 px; component checks also discard late history responses after an institution switch |
| Production build and OpenAPI/generated frontend drift | Passed |
| Generated Postman drift and official collection 2.1 schema | Passed; 51 operations and 24 Pydantic-validated body examples |
| Newman smoke | 25 assertions passed across 11 HTTP requests, including CSRF setup |
| Package integrity and whitespace | Passed; final package count recorded in VALIDATION.md |
| Generated signing-key scan | Absent from 153 project/browser assets; key value never printed |

Backend tests exercise organization-only users, explicit college/institution boundaries, wrong roles/institutions/parents, missing MFA/CSRF/recent authentication, append-only denial evidence, stale revisions, idempotency, duplicate creation contention, archival versus approval, pending invitation cancellation and delivery exclusion, account suspension, explicit grant restoration/expiry, empty institutions, direct RLS and pooled connection reuse. Fresh migrations used only disposable advisory_test; the existing advisory_dev environment retained its records/history and upgraded additively.

The full E2E run verifies UI creation, explicit enrollment, a separate manager appointment, organization-only delegation and revocation, archive/restore, existing staff/invitation workflows, and responsive keyboard navigation. A previously approved persistent pending fixture is checked against its current server state rather than resetting its history; isolated backend/component pending-state tests remain deterministic. Desktop/mobile administration screenshots were inspected. Local liveness/readiness returned HTTP 200. The FastAPI test client emits a deprecation warning. Hosted GitHub Actions, screen readers and other browser engines were not exercised.

## Limitations

Synthetic local deployment only; live identity, production MFA/email/cloud, new institutions, transfers/reparenting, academic records and downstream generation/stream cancellation remain outside T061. Scope grants cover organization metadata only. Existing rendered content clears on authorization refresh (focus/30-second polling); subsequent server requests enforce revocation immediately. The local coarse lock is a correctness choice, with no production throughput claim. Institutional naming, ownership and retention policies remain unresolved. Full screen-reader/WCAG and non-Chromium assessment are not claimed.
