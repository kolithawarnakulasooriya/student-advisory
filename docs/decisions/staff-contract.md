# Staff workflow contract — Release 0.2 subset of T002

The generated OpenAPI snapshot and frontend client are authoritative wire shapes. All routes use `/api/v1`; actor identity, timestamps, grants, effective scopes, and capabilities come from current server state. Input models reject extra fields. Only `.test` identities and loopback development services are supported.

| Interface group | Contract |
| --- | --- |
| `/me` | Retains foundation fields; adds explicit platform grants and own student membership/relationship epochs. Capabilities reflect the selected scope. Relationship changes also invalidate affected users' permission epochs. |
| `GET /membership-options` | Verified identity only; explicit enrollment options, not the unrestricted organization directory. |
| `/membership-requests` and `/{id}/approve`, `/{id}/reject` | Create/list own or authorized requests; a duplicate pending request returns the existing record. Student/advisor decisions use scoped authorized staff. Manager self-service requests require a platform super admin, even when a platform admin has a manager appointment ceiling. No self-approval. |
| `/invitations`, `/{id}/resend`, `/{id}/revoke`, `/accept` | Hash-only application tokens; verified immutable recipient identity; current issuer authority; expiry and single-use checks. Resend rotates nonce/token. Token-bearing links use fragments consumed into memory and removed. Student acceptance requires an eligible advisor in the same department. |
| `/memberships` and `/{grant_id}` | Authorized enrollment projections; student membership ID is separate from identity/user ID and included where applicable. Lifecycle requires If-Match and a reason. Student reactivation requires assignment authority as well as student membership management. |
| `/students`, `/students/{membership_id}` | Protected active student summaries. Own student, current assigned advisor, scoped manager, explicit records grant, or purposeful global oversight. Secretary enrollment capability does not permit this interface. |
| `/eligible-advisors`, `/assignment-state/{membership_id}`, `PUT /students/{membership_id}/advisor` | Eligible scoped advisor metadata and capacity; enrollment-only assignment revision read; assignment mutation returns status/ID, not protected student content. |
| `/role-grants` and `/{id}` | Explicit scoped appointments/delegation and capacities. No self-grant or mutable grant identity. Secretary capabilities are whitelisted; platform-admin capabilities are bounded by their explicit ceiling. Manager-request approval is not delegable. |
| `/users`, `/users/{id}/state`, `/platform-grants` | Scoped/global user directory; whole-account changes only by platform super admins. Account suspension revokes all effective grants and sessions. Reactivation approves selected staff grants explicitly or leaves all suspended; student memberships need a separate advisor-aware reactivation. Platform grants have a separate explicit lifecycle. |
| `/audit-events`, `/users/{id}/history` | Scoped history and staff own-action metadata. Global sensitive reads require an operational purpose. Inaccessible underlying references are filtered/redacted. Operational rationale is separately protected and referenced from append-only audit events. |

State mutations require a session-bound CSRF token, exact configured Origin, recent auth, and an Idempotency-Key. Existing-state changes require `If-Match: "<version>"`; whole-account state uses the user's current grant epoch. Stale state returns 409. The same key/body returns its recorded result only while the actor's permission epoch still matches; a changed body or epoch returns 409.

List responses contain items, total, and next_cursor. Limits are 1–100, default 25. Signatures bind cursor to actor, route, scope, purpose, filter, page size and permission epoch; all counts use authorized queries. Standard errors retain code, message, field_errors and correlation_id without submitted values or database details.

Successful mutations, operational-reason references and relevant outbox metadata commit together. Denials persist after rollback through a separate append-only transaction. Only invitation.send has an active consumer. Other outbox types are recorded metadata, not claimed notification delivery or cloud publishing. SMTP crash retries may repeat email while acceptance stays single-use.

The first platform super admin uses an audited one-time operator bootstrap. Normal application requests never use the migration credential. A local coarse write lock serializes authorization-sensitive transitions and capacity; it is not a production performance claim. Full event publishing, future resource contracts, and cloud policies remain in later tasks.
