# Access control implementation specification

## Authorization inputs
AuthContext contains identity subject, institution, selected operational scope, active role grants, explicit capabilities, session age, grant epoch, and correlation ID. Load current grants server-side; do not rely exclusively on long-lived identity-provider claims. A scope is a set of explicit org units resolved through the org tree. College managers cover only the departments included by their active grant.

A decision evaluates actor status, requested action, resource institution/scope, active student membership, current relationship, visibility class, resource state, and recent-auth requirements. Reject if any required input is missing. A student's possession of an ID, a forwarded email link, or an old chat membership cannot establish permission.

## Relationship rules
A student reads their own profile, student-visible messages, applicable knowledge citations, cases, and forms. An advisor reads student records only while assigned and active. A manager reads records in their granted org units. A secretary receives enrollment and assignment capabilities only; no transcript, source-content, or signature powers by default. Platform admins require explicit operational/record grants. Super admins retain requested global oversight but every sensitive read is logged with an access reason.

Multiple roles do not create global powers by union across unrelated scopes. An advisor in A and manager in B can manage B and advise assigned A students. When acting on a B form as manager, the A advisor relationship cannot satisfy a B advisor signature step. Delegated grants cannot exceed the delegator's role ceiling or scope.

## Data and query enforcement
Use query builders that accept AuthContext and return only authorized rows. Source access combines shared institutional/department visibility and student-specific visibility. Department A shared documents are not visible to Department B unless separately published with appropriate authority. Program, track, catalog, and effective-date filters further constrain relevance; authorization does not imply applicability.

Configure row-level security on sensitive tables. Run API sessions under a non-owner role without BYPASSRLS and use FORCE ROW LEVEL SECURITY where needed. Apply SET LOCAL context within each transaction; fail closed if context is absent. Connection pool checkout/return cannot carry another user's settings. A DB owner migration account is never used for normal requests. Test any privileged worker role independently.

List, count, autocomplete, search, downloads, citation snippets, job status, exports, websocket/event streams, and error messages are all data surfaces. Scope them consistently. Do not expose the existence or title of inaccessible records. Storage signatures require authorization at issue time, short TTLs, private object keys, and logging. MVP TTL should be at most 60 seconds; use proxy downloads if immediate revocation is required beyond that bounded expiry.

## Revocation and races
Maintain grant_epoch and relationship_epoch. Increment them transactionally for suspension, assignment, transfer, and grant changes. Revoke active sessions where supported. Jobs capture an epoch but re-resolve permissions when they start and before persisting or delivering output. A changed epoch causes cancellation or recomputation. Durable notifications recheck recipient access at delivery. Event streams periodically and before sensitive events reauthorize subscribers.

A download URL already issued cannot be made instantly invalid without an object proxy or key rotation; do not claim stronger revocation than configured. New API requests must deny immediately after transaction commit.

## Required negative tests
Test every sensitive route as an anonymous user, pending user, suspended user, wrong-department manager, unassigned advisor, former advisor, secretary without records grant, and unrelated student. Include guessed UUIDs, pagination cursors, bulk requests, malicious scope IDs, forwarded citation links, expired invitation tokens, multi-role users, pooled DB connections, generation in progress during reassignment, and queued email after revocation.

## Audit
Record actor, action, object ID/type, scope, allow/deny result, reason, timestamp, and correlation ID. Do not record full prompts or transcripts in audit events. Restrict audit writing to append operations, restrict reads separately, and send durable copies to an institution-approved retention target. Hashing records alone does not create a tamper-proof audit system. Alert on repeated denied access and high-volume exports.
