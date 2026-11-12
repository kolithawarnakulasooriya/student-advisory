# Release 0.4 local advising contract

All examples and measured fixtures are synthetic. This release adds T025–T035 and the durable case portion of T037–T038 to Release 0.3. General notifications, email, business calendars, comprehensive plan validation, saved plans and signatures remain pending.

## Authority and evidence

Every conversation and case binds one student membership. Existing institution, organization, active-grant and current-assignment checks apply on every read, list, count, revision, citation and worker operation. Secretary and organization-metadata grants convey no document or chat authority. Scoped managers can review/index/publish; platform administrators need explicit source access plus source.publish/rules.manage grants. Global prompt controls require an active platform super-admin grant, MFA and recorded purpose. A role label alone grants nothing.

Every new table has forced PostgreSQL RLS. The application and advisory_rag worker are non-owner, non-BYPASSRLS roles. The worker has no SELECT grant on staff_notes. Artifacts and worker events bind the current leased job. The worker captures the actor grant epoch, membership relationship epoch, profile version, active guidance IDs/epoch, applicability date, knowledge epoch and embedding configuration. The knowledge epoch changes with publication and prompt/rule activation. Leases expire after ten minutes; expired attempts fail with WORKER_INTERRUPTED. Explicit retries preserve the question/source version, increment attempt, and stop after three attempts. Unique artifact/job and build/ordinal constraints prevent duplicates.

A shared publication points to one complete build of an immutable source version. Intake replacement is independent. Student source projections select only RLS-visible versions; published-source views expose only the published version's title, identity and publication date. Draft filenames, history and counts remain staff-only. Downloads continue through the Release 0.3 authorization and clean-scan proxy. Withdrawal and archive exclude evidence immediately; answer commits recheck current publication/applicability. Historical citations keep identity and mark withdrawn/superseded status, with withdrawn excerpts redacted.

## Retrieval and rendering

The SQL MATERIALIZED eligible relation applies institution, organization, student membership, active publication/build/configuration, program, track, catalog range and effective date before either LIMIT. Exact pgvector cosine search and PostgreSQL English full-text each return at most 20 candidates. Reciprocal-rank fusion uses 1/(60+rank), retains at most 30, and sends only authorized text to the ONNX reranker. Ten ranked results are retained; at most four admitted excerpts enter chat. The local admission floor is -8 reranker logits, calibrated only against the frozen tiny synthetic fixture; it is not a production accuracy threshold.

Chunks preserve exact character spans, page/heading/paragraph locators, source and excerpt hashes, extractor and chunker versions, and embedding token counts. The chunker uses at most 300 embedding tokens with bounded overlap. Query/reranker pairs and the 4,096-token chat context are checked without silent truncation. Nomic uses search_document/search_query prefixes, truncate=false and finite 768-dimensional vectors. No ANN over-fetch or post-filter authorization shortcut is used.

The chat model returns only disposition, evidence identifiers and a bounded reason code. The server permits supplied identifiers, renders the original exact excerpts, and attaches source/version/locator/publication provenance. Model-written academic prose, HTML and tool calls are never rendered or executed. One invalid-selection repair is permitted, then an explicit safe human-help disposition is stored. Model downtime fails the attempt without substituting a mock. Missing/disputed applicability facts request clarification. Exception/waiver/bypass requests and potential same-rank catalog conflicts require human review. Advisor preferences cannot create waivers.

Typed prerequisite checks use explicitly reported completion=true; absence stays unknown. Course-limit checks explain only the published, reviewed rule. These point checks do not establish SIS verification, comprehensive eligibility, offerings or a validated plan. Department terminology/clarification settings are bounded typed values. Global prompt releases change display style only. Rule references must bind published catalog/policy evidence; activation or rollback needs a passing recorded evaluation for the current knowledge epoch and model fingerprint. Policy owners remain responsible for the semantic accuracy of entered rules.

## Typed conversations and cases

Student questions create immutable messages and generation jobs. Guidance has immutable authorship, validity and supersession identity; conversation guidance epochs provide versioning. Only active guidance enters later student turns. Staff notes use separate tables, APIs and UI and never enter prompts, traces, events or summaries. Posting guidance creates zero generation jobs, assistant acknowledgments or typing indicators.

Explicit advisor draft requests create staff-only jobs and projections. Notes are excluded from draft prompts too. The currently assigned advisor must review, edit and explicitly publish a draft as advisor-authored guidance; stale context requires a fresh draft. The worker emits advisor.draft.completed separately from generation.completed.

Human-help requests are idempotent durable cases with receipt ID, status and append-only lifecycle events. They follow the current eligible primary advisor, or the manager queue when none exists. Reassigning the primary advisor changes routing and removes former-advisor access. Human lifecycle transitions are audited and revision checked. Model recovery never resolves a case. No email, SLA/business-calendar timing or delivery notification is promised.

## API and UI conventions

OpenAPI, frontend types and Postman are generated together. Mutations use session cookies, CSRF, recent authentication, idempotency keys and the applicable If-Match revision. Version-bearing JSON responses return ETags; stale edits return 409. Cursor pagination binds the current actor/scope/purpose. Replayed idempotent operations reauthorize before returning data.

The UI keeps student questions, visible guidance, private notes and reviewed drafts separate. It polls authenticated endpoints only while visible, clears scoped state on identity/permission changes, uses restricted Markdown, and resolves evidence through the authorized citation endpoint. Staff have a current-authority case queue and scoped source/governance controls. Hidden controls never authorize an action.

## Local model provenance and changes

See [models.lock.json](../../infra/inference/models.lock.json) for exact Ollama digests, tokenizer/ONNX revisions, artifact hashes and model-card/license references. [runtime.lock.json](../../infra/inference/runtime.lock.json) records tested local container identity and hashed build inputs; requirements.lock pins package versions and wheel hashes. Prepare downloads separately. Startup verifies inputs and records an explicitly built image; subsequent starts reject image drift. Model hashes and dimensions are verified by the authenticated gateway and adapter. No raw Ollama port is published; the gateway is loopback/token protected, and the browser never receives its token.

Embedding changes build all published versions under a parallel configuration before an atomic global activation. Failed/incomplete builds retain the prior publication. Source replacements and embedding rebuilds are separate operations. Rollback uses retained compatible builds plus a fresh authorized evaluation/activation. Changing a model lock is an explicit reviewed release, never an automatic runtime pull.
