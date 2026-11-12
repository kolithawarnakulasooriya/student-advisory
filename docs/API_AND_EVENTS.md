# API payloads events and state handling

The route inventory is in PRD section 13. These examples are design contracts to implement and validate in generated OpenAPI. UUID-like labels below are synthetic placeholders. All writes require authenticated access, CSRF defense for cookie sessions, and an idempotency key where they create an external effect or durable workflow transition.

## Membership request
```json
{"requested_role":"student","org_unit_id":"department-a","program_id":"program-x","justification":"New student"}
```
The server resolves the user from the session, verifies available scope, and routes approval. Approval payload contains an optional eligible advisor and decision reason, never arbitrary capabilities supplied by a requester. Return 201 for creation, the existing request for an idempotent duplicate, 403 for an unauthorized action, and 409 for a stale transition.

## Advisor guidance
```json
{"type":"student_visible_guidance","text":"Limit the proposed term to three courses.","scope":"conversation","effective_until":"2027-01-31T23:59:59Z","supersedes_guidance_id":null}
```
The authenticated assigned advisor is the author. Insert guidance and guidance_added outbox event in one transaction. The event may notify the student, but it must not create a generation_requested event. Staff-only notes use a distinct schema and endpoint or discriminated action; they cannot be included by generic message concatenation.

## Form signing
Headers: If-Match containing the form revision ETag and Idempotency-Key containing a fresh client operation ID.
```json
{"revision_id":"revision-3","step":"student","method":"initials","display_value":"KW","consent_version":"consent-1","intent_confirmed":true}
```
The server verifies identity, recent authentication, current revision/content hash, permitted step, signer relationship, prior signatures, and affirmative intent. It ignores any client-supplied author or timestamp fields. Store signature, advance form, and insert outbox event in one transaction. Persist the idempotency result keyed by actor, route, and key; reject reuse with a different payload hash. A stale ETag returns 409 with a refresh action and no signature.

## Event envelope
```json
{"event_id":"event-uuid","schema_version":1,"type":"case.created","aggregate_id":"case-uuid","aggregate_version":1,"institution_id":"institution-uuid","org_unit_id":"department-a","occurred_at":"2026-11-05T18:00:00Z","correlation_id":"request-uuid","payload_ref":"case-uuid"}
```
Do not embed transcript, grades, signature payloads, or private source text in Pub/Sub messages. The consumer loads authorized current data using its narrowly scoped service role. Events carry routing metadata, not permission. Deduplicate by consumer/event_id; acknowledge only after the durable outcome is recorded. Retry transient errors with backoff; send permanent malformed events to a dead-letter queue and alert. Outbox publishing can duplicate an event after a crash, so exactly-once side effects require application idempotency.

Events to implement: membership.requested, membership.decided, assignment.changed, source.uploaded, source.extracted, source.indexed, source.published, source.withdrawn, student.message.created, generation.requested, generation.completed, advisor.guidance.added, case.created, case.updated, form.submitted, form.signed, form.returned, form.held, form.completed, and notification.requested. Schema changes must be versioned and backward compatible while consumers roll forward.

## Audit and errors
Record successful and denied privileged actions. Use stable reason codes such as WRONG_SCOPE, RELATIONSHIP_REVOKED, STALE_REVISION, SOURCE_NOT_APPLICABLE, NO_SUPPORTING_EVIDENCE, and SIGNATURE_STEP_NOT_ALLOWED. Return a generic inaccessible-record response where exposing object existence is inappropriate. Never echo database errors, source text, credentials, or model stack traces to users.


## Release 0.3 intake APIs

Implemented profile/schema/source routes are represented in the generated OpenAPI contract. `mid` always denotes a student membership ID. Profile/schema GETs expose ETags; transitions require If-Match and idempotency keys. Multipart uploads use a `target` JSON part matching SourceTarget and a `file` part. A new source uses If-Match `"0"`; replacements supply source_id and its current version. Metadata edits append versions without changing scope. File downloads require successful clean processing and current access. `/profile/context?context=...` compares a captured token without returning academic facts. See [the intake contract](decisions/intake-contract.md) for the metadata-only profile.changed event and future consumer obligations.


## Release 0.4 implemented local surfaces

See [advising contract](decisions/advising-contract.md) and generated backend OpenAPI for publication/index/withdrawal/index rebuild, published-source/citation, governance/evaluation/activation, conversation/message/job/retry, guidance/supersession/note/private-draft, and case/history/lifecycle routes. These preserve cookie/CSRF/recent-authentication, revision/idempotency, current authority and cursor contracts. Metadata-only events include source.indexed, source.published/withdrawn, student.message.created, generation.requested/completed, advisor.guidance.added, advisor.draft.completed, governance.evaluated and case.created/updated. Private note content never appears in events. These recorded events do not implement general notification delivery; guidance creates no generation event/job. Future consumers must reauthorize, deduplicate by event identity and compare captured context before consuming artifacts.
