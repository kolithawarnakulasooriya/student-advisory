# Backend API collection

Import [Student-Advisory.postman_collection.json](Student-Advisory.postman_collection.json) and [Local.postman_environment.json](Local.postman_environment.json) into Postman, then select **Student Advisory — Local synthetic**. The collection includes all 51 operations in the committed Release 0.2 OpenAPI contract. Requests are grouped by identity, enrollment, invitations, memberships, assignments, administrators and audit.

Start the local database, migrate/seed and run FastAPI using the [project setup](../README.md). The default `base_url` is `http://localhost:8000` (direct API); use `http://localhost:3000` to exercise the frontend proxy. Keep `web_origin=http://localhost:3000` for both: the backend checks Origin on mutations. Keep Postman's cookie jar enabled and use the same hostname throughout a session. No bearer token, database credential or signing key is needed.

## Quick check

Run only the **00 Smoke** folder with the default `login_email=manager@advisory.test`. It checks liveness/readiness, signs in, simulates staff MFA, reads the account, verifies wrong-department denial, signs out and checks session revocation. It creates/revokes a synthetic session without changing memberships.

Alternatively, run from the project root:

```bash
npx --yes newman@6.2.3 run postman/Student-Advisory.postman_collection.json \
  -e postman/Local.postman_environment.json --folder '00 Smoke' \
  --reporters cli --reporter-cli-no-console
```

The other folders are an API reference for individual requests. They require different identities and resource states, so running the entire collection in order is not an end-to-end scenario. Their mutation examples perform real changes in the disposable synthetic database when sent. The smoke folder's wrong-scope expectation assumes the default manager in Department A.

## Sessions and request headers

Send **POST /auth/sign-in** with `login_email` set to a seeded or previously registered address. Staff must then send **POST /auth/simulator/step-up**. Send that step-up again if recent authentication expires. Use **GET /me** to inspect the server-derived scope, capabilities and account state. Enable its optional `scope_id` query parameter to select an explicit department.

The collection fetches a fresh CSRF token before every mutation, adds Origin and X-CSRF-Token, and uses Postman's cookie jar for rotated HttpOnly sessions. CSRF tokens and automatically fetched verification challenges are request-local, never exported into the supplied environment. The script mechanism follows [Postman's pm.sendRequest documentation](https://learning.postman.com/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-send-request/).

Workflow mutations receive a fresh Idempotency-Key on every send. To retry one logical operation, set a fixed `idempotency_key` before its first send and retain the identical payload. Clear it before a different operation. Changing permission epochs or reusing a key with a different payload returns 409.

If-Match values are quoted automatically. Existing-state mutations are skipped if their revision variable is empty; first read the relevant resource. Revision sources:

| Variable | Read before writing |
| --- | --- |
| `request_version` | Matching request in GET /membership-requests, or its create/decision response |
| `invitation_version` | Matching invitation in GET /invitations, or its create/resend/revoke response |
| `membership_version` | GET /memberships/{gid}; its response is captured automatically |
| `assignment_version` | GET /assignment-state/{mid}, or protected GET /students/{mid}; captured automatically |
| `role_grant_version` | Read GET /memberships/{gid} using the role_grant_id, then copy its version; create/delegation responses also capture it |
| `platform_grant_version` | Matching row in GET /platform-grants, or its appointment/state response |
| `grant_epoch` | GET /users filtered by target_email; the matching user's ID and epoch are captured automatically |

After changing any target ID, clear its old version and read that resource again. Student membership IDs and role-grant IDs are distinct identifiers even where legacy fixture values happen to coincide. Actor ID from /me is saved as `actor_user_id`, separately from the workflow target `user_id`.

For paginated reads, `limit` defaults to 25. Enable the disabled `cursor` query parameter and set `cursor` to that response's next_cursor to advance. Retain the same identity, limit, filter, purpose and scope. Optional scope filters start disabled so a new verified account can discover membership options and its own requests. Enable `scope_id` to filter staff lists, queues and histories; required scope parameters are already enabled. For global user searches, leave scope disabled. Clear cursor when switching queries.

## Common workflows

1. **Registration:** Set `registration_email` to a new `.test` address, or leave it empty for a unique generated address. Send POST /auth/register. The successful address is saved as `registered_email`. Send POST /auth/verify: it obtains and uses a fresh simulator challenge automatically when `verification_challenge` is blank. If testing expiry/reuse, supply your own local challenge instead. Verification grants no role.
2. **Student request → approval:** As the verified student, GET /membership-options and POST /membership-requests. Creation captures `request_id` and `request_version`. Sign in as manager and step up, select an eligible `advisor_grant_id`, and send POST /membership-requests/{rid}/approve. Rejection uses the corresponding reject request. Manager membership requests require a bootstrapped platform super admin.
3. **Invitation → acceptance:** As authorized staff, set invitation_email/role, scope and advisor, then POST /invitations. Creation captures invitation ID/version. Run the local mail worker and open Mailpit at `http://localhost:8025`. Copy only the value after `#invitation=` from the delivered link into the local secret `invitation_token`. Register/verify or sign in as that exact invited email, then POST /invitations/accept. Success clears invitation_token. Resend rotates it; the API never returns it. Do not export or share populated secret variables, cookies, inbox links or response histories.
4. **Membership lifecycle:** Read the target membership, then set lifecycle_status to suspended, active or revoked. Reactivating a student needs assignment authority and an eligible advisor. Revoked memberships require a new explicit appointment; a stale revision returns 409.
5. **Advisor change:** GET /eligible-advisors, choose advisor_grant_id, read GET /assignment-state/{mid}, then PUT /students/{mid}/advisor. The assignment version is cleared after success so another change requires a fresh read. Secretary enrollment projections remain separate from protected student summaries.
6. **Delegation and accounts:** Use role-grant requests to appoint permitted staff and individually delegate secretary capabilities. For platform-admin appointments, edit the body to select explicit capabilities/ceiling. Only a platform super admin can appoint another super admin or suspend an entire account. Account reactivation with approved_grant_ids=[] restores no grants. Bootstrap is the operator CLI documented in the project README; there is no HTTP bootstrap endpoint.

The default fixtures select Department A, student-a, advisor-a and secretary. Update target IDs before appointments or lifecycle changes. For advisor reassignment you can select the separately seeded advisor-a2 from GET /eligible-advisors. Request/invitation/platform IDs and revisions start blank until obtained from the server. Platform administration requires the explicit operator bootstrap; legacy super-admin labels do not grant global access. Global sensitive reads carry the configured `purpose` and are audited.

## Regeneration and checks

```bash
python3 scripts/generate_postman.py
python3 scripts/generate_postman.py --check
python3 scripts/validate_package.py
```

The generator reads the committed OpenAPI snapshot; update that first with `uv run python -m app.contracts` from backend when API schemas change. The collection uses the [official Postman 2.1 format](https://schema.postman.com/json/collection/v2.1.0/docs/index.html). Source scripts are [prerequest.js](prerequest.js) and [postresponse.js](postresponse.js); regenerate after changing them. CI checks generated drift. This collection covers the currently implemented APIs; academic profiles, documents, RAG/chat, signatures and cloud endpoints remain deferred.

## Observed validation

On November 11, 2026: official collection 2.1 JSON-schema validation passed; all 39 OpenAPI operations and their query/template variables were covered; all 17 body examples validated against backend Pydantic models. Newman 6.2.3 smoke passed 25 assertions across 11 HTTP requests including CSRF setup. An additional temporary scenario using the generated requests passed 34 assertions across 21 HTTP requests: registration, automatic verification, enrollment request, manager MFA/approval, same-key retry, activated-student sign-in and logout. Only synthetic disposable fixtures were added. JavaScript syntax, regeneration drift, package integrity and whitespace checks passed. Postman desktop UI import was not exercised; API authorization tests remain in the backend suite.

## Organization administration

Folders **12 Organization administration** and **13 Organization administration grants** cover T061. Sign in as a bootstrapped super admin and step up. Set institution_id and use the create body for a college; for a department change kind to department and parent_id to an active college UUID. Creation captures organization_id/version. Detail reads refresh organization_version for edit, enrollment, archive and restore. Grant creation/state responses capture organization_grant_id/version. Scoped metadata delegation never appoints a manager; use the separate role-grant request for that action. See the [organization walkthrough](../docs/T061_HANDOFF.md).


Release 0.3 folders cover onboarding schemas, profiles and document intake. Read the profile/config/source first to capture its revision; creation of a source/profile uses version 0. Multipart upload has a JSON target part and a file selector. Set schema_id from the active department configuration. Source downloads return bytes rather than JSON. Processing requires the local worker and real scanner setup documented in the root README. The reference folders are not a sequential runner and do not imply publishing authority.
