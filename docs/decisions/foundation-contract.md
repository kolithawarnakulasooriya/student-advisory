# Foundation contracts — T002 subset

The versioned contract is the generated backend OpenAPI snapshot, with a generated TypeScript client type layer. Account/profile/role identity is always resolved server-side. All input models forbid extra fields.

| Interface | Behavior |
| --- | --- |
| GET /api/v1/health/live | Process health; no dependency or configuration disclosure |
| GET /api/v1/health/ready | Verify database availability, runtime roles, vector extension, and foundation schema |
| GET /api/v1/auth/csrf | Create/recover a pre-auth session if necessary; return a session-bound CSRF token |
| POST /api/v1/auth/sign-in | Synthetic email lookup, server-only signed assertion validation, session rotation |
| POST /api/v1/auth/register | Synthetic address and display name; new immutable subject, unverified session, hashed verification challenge; no grants |
| POST /api/v1/auth/simulator/challenge | Current unverified identity only; display a local-only expiring challenge |
| POST /api/v1/auth/verify | Current identity, single-use challenge, session rotation; no membership approval |
| POST /api/v1/auth/simulator/step-up | Explicit mock MFA; rotate session and reset recent-auth time |
| POST /api/v1/auth/logout | Revoke current session and delete cookie |
| GET /api/v1/me | Own identity/state, current active grants, own membership statuses, permitted scope options, capabilities, grant epoch; optional validated scope_id |
| GET /api/v1/org-units | Only authorized organization metadata; optional validated scope_id |
| GET /api/v1/org-units/{id} | Current grant and matching institution; inaccessible/missing IDs both return 404 |

Writes require exact configured Origin and X-CSRF-Token; sign-in/registration require a pre-auth session. Session IDs are opaque, HttpOnly, SameSite=Lax; database stores hashes. Local HTTP explicitly uses Secure=false; this release rejects every production configuration. Default idle/absolute/recent-auth/challenge windows: 30 min / 8 h / 10 min / 10 min. Sign-in/verification/step-up rotate sessions. Logout replay returns 401; it cannot restore a session.

Errors contain code, message, field_errors, and server-generated correlation_id, without submitted values. Organization reads are bounded by the current user's explicit grants; pagination, mutation idempotency/ETags, and event envelopes are reserved for the relevant later workflow tasks. No workflow/event producer is implemented in 0.1. The organization list is a bounded foundation scope selector, not a public directory.

Current identity/session resolution uses the advisory_auth DB role; its transaction-local login/session/actor context protects identity, session, and challenge rows. It cannot read or write grants or organizations. Application reads use advisory_app, explicit query scopes and enforced RLS. Both roles are non-owner and have no BYPASSRLS. Only operator migration/seed credentials can grant roles. These service credentials are server authority; a database credential compromise is not contained by user-facing authorization alone.

Full contracts for invitations, approvals, records, assignments, audit, jobs, and signatures remain in T002/T011/T012 and later tasks. No live OIDC authorization-code exchange or institution provider adapter exists yet.
