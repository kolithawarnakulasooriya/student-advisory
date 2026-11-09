# RAG Based Student Advisory System

Product requirements document • Version 1.0 • November 5, 2026

This document defines a student advising platform with a web frontend, a backend API, a document retrieval pipeline, human advisor participation, and an approval form workflow. It translates the requested roles and behavior into implementable requirements. The platform provides recommendations supported by approved institutional material and routes unresolved questions to assigned advisors. Academic decisions remain reviewable by authorized people.

The development package is a specification and implementation guide. It does not contain a completed application or provisioned cloud resources. All architecture choices below are proposed defaults unless identified as an explicit user requirement.

## 1 Product goals and scope

Students should be able to understand requirements that apply to their program and catalog year, discuss possible plans, obtain help from a human advisor, and submit an agreed plan for signatures. Staff should be able to manage their assigned population and maintain the material that supports recommendations.

The first release supports one institution with multiple colleges and departments. All institutional data still carries an institution identifier to prevent accidental mixing and to support future separation. A department is the normal operational scope; a college manager may receive explicit grants covering its departments. A college grant does not imply access to departments outside that college.

The minimum release includes verified email registration and invitations, approval queues, scoped role grants, student onboarding, versioned knowledge publication, cited RAG chat, advisor guidance, escalation, notifications, and sequential signatures. It includes administrative audit records, revocation, backups, and evaluation gates.

Out of scope for the first release are autonomous course registration, registrar decisions, payment or financial aid decisions, automated policy exceptions, clinical counseling, predictive student risk scoring, unrestricted web browsing, model training on student conversations, external student information system writes, and cross-institution tenancy. Read-only SIS integration and commercial signature-provider integration are later extensions.

## 2 Decisions and assumptions

| Topic | Default decision | Reason or unresolved dependency |
| --- | --- | --- |
| Secretary | Delegated department staff role with enrollment and assignment capabilities | Requested in the student workflow although absent from the original role list |
| Admin hierarchy | Super admin plus delegated platform admin | Only super admins create other super admins or alter platform security settings |
| Manager appointment | Verified request or invitation followed by super admin approval | No self-appointment to a department |
| Student approval | Secretary, manager, or authorized admin in the requested department | A request never grants access by itself |
| Advisor guidance | Typed human message and explicit scoped instruction | No automatic assistant reply to advisor messages |
| RAG tuning | Document publication, structured rules, prompts, chunking, retrieval, reranking, evaluations | Uploading documents does not update model weights |
| Signatures | Authenticated electronic signature using initials or typed name and affirmative intent | Cryptographic certificate signing and legal sufficiency require separate institutional decisions |
| Student visibility | Students see chat-visible advisor guidance; staff-only notes remain outside the model context | Prevent hidden notes from leaking through generated answers |
| Department transfer | New approval and transactional assignment update | Historical access and pending forms require an explicit transfer decision |
| Catalog authority | Structured institution-approved policy with validity and authority metadata | Upload time alone does not determine authority |

Decisions required before a real student pilot: institution and identity provider; secretary delegation policy; advisor assignment limits; official form template; accepted signature method and retention policy; model license and GPU budget; catalog sources and policy owner; data location; privacy review; and notification provider. Development may proceed with synthetic fixtures and these defaults.

## 3 Users and permissions

Authorization combines role, scope, relationship, resource state, and action. A role label is insufficient. A user may have multiple grants in different scopes; every request selects an active institution and scope and the backend validates it. No scope supplied by a browser is trusted without database verification.

| Capability | Super admin | Platform admin | Manager | Secretary | Advisor | Student |
| --- | --- | --- | --- | --- | --- | --- |
| Configure platform and appoint super admins | Global | No | No | No | No | No |
| Manage department managers | Global | Only explicit delegated scope | No | No | No | No |
| Approve and revoke advisors | Global | Delegated scope | Own scope | No | No | No |
| Approve students and assign advisors | Global | Delegated scope | Own scope | Delegated scope | No | No |
| Publish institutional knowledge | Global | Explicit publishing grant | No | No | No | No |
| Publish department knowledge | Global | Delegated scope | Own scope | No | No | No |
| Upload student-specific documents | Global | Delegated scope | Own scope | No by default | Assigned students | No in MVP |
| View student chat and student documents | Global with audit | Explicit records grant | Own scope | No by default | Assigned students | Own records |
| Add advisor guidance in chat | Only with advisor grant | Only with advisor grant | Only with advisor grant | No | Assigned students | No |
| Sign student step | No proxy | No proxy | No proxy | No | No | Own form |
| Sign advisor step | Only as assigned advisor | Only as assigned advisor | Only as assigned advisor | No | Assigned form | No |
| Sign manager step | Only designated manager signer | Only designated manager signer | Designated scope | No | No | No |
| View administrative audit | Global | Delegated audit grant | Own operational scope | Own actions only | Own actions only | Own form history |

Global visibility is a requested super admin capability, but record access must be logged with actor, reason, subject, time, and action. Default dashboards expose counts and queues rather than transcripts. Staff access must serve the institution's approved educational purpose. A system administrator cannot impersonate a student signature. High privilege alone does not satisfy a form signing relationship.

Managers may appoint advisors only within their own scope and only up to the advisor role. Secretaries cannot appoint managers or advisors, publish policy, inspect transcripts, or sign as another person. Student removal means membership suspension or revocation, preserving records according to retention policy rather than immediate destructive deletion.

## 4 Identity and enrollment requirements

**ID-01 Verified identity.** Users authenticate through an institution-approved provider. Invitations identify a normalized verified email but bind to an immutable identity subject on acceptance. Email is not the permanent primary key. Never strip plus suffixes or dots using assumptions about a provider. An email domain alone grants no role.

**ID-02 Invitations.** Admins may invite staff and students by email, role, and scope. Managers may invite advisors, students, and secretaries in their scope; secretary appointment requires the manager's explicit delegation. Secretaries may invite students only. Invitation tokens are single-use, expire after a configurable period, and are stored as hashes. Pending invitations expose no student records. Invitations may preselect an advisor, but access activates only after verification and acceptance.

**ID-03 Requests.** A verified user may request student, advisor, or manager membership in an available scope. Manager requests route to super admins; advisor requests route to that scope's manager or admin; student requests route to secretary or manager. The approver sees identity, requested department, justification, and suggested assignment, and records approval or rejection with a reason. The requester cannot approve their own request.

**ID-04 State and concurrency.** Membership states are invited, pending, active, suspended, rejected, and revoked. Expired invitations are tracked separately. Duplicate requests return the existing pending request. Approval and role grant creation occur in one transaction. Conflicting approvals return HTTP 409 without duplicate grants.

**ID-05 Bootstrap and privilege.** Bootstrap the first super admin through a controlled operator process with audit logging; disable the bootstrap path afterward. Prevent deletion or suspension of the last active super admin. Require staff MFA and recent authentication for role changes, knowledge publication, and signatures.

**ID-06 Reassignment.** Each active student department membership has one primary advisor in MVP. Reassigning checks the new advisor's active scope and capacity, records old and new relationships, cancels obsolete notifications, and revokes old advisor access for subsequent requests. In-progress model responses are cancelled or reauthorized before release. Historical participants retain no implicit access.

**Acceptance example.** An active advisor in Department A cannot open, search, export, receive notifications for, or retrieve chunks belonging to Department B by guessing an identifier. A pending student can see their request status and profile setup only.

**ID-07 User administration and history.** Super admins can search users by verified email and inspect an advisor timeline containing role/department changes, assignment history, authored guidance, case dispositions, document versions, and form-review/signature events. Scope-filtered managers see the equivalent history within their own department. Each history drill-down rechecks access to the underlying student record. Authorized admins can suspend an entire account across all memberships, revoke sessions, and record the reason; reactivation restores only explicitly approved grants. Last-super-admin protection still applies. History is an audited record, not an editable performance score.

## 5 Student onboarding

**ON-01 Profile.** Collect degree level, college, department, program, track or concentration, catalog year, entry term, current term, intended graduation term, academic goals, completed and current courses, transfer credits, and workload preferences. Collect grades only when necessary for stated prerequisites. Do not request SSNs, credentials, financial account details, or unrelated health information.

**ON-02 Provenance.** Each academic fact records source, verification status, effective term, and last confirmed date. Student-entered facts are self-reported. Future SIS facts may be institution-verified. Missing or conflicting data prompts clarification; the agent cannot infer completion or waivers from silence.

**ON-03 Schema.** Department managers configure required fields and valid program/track choices using a versioned schema. A catalog year is required before definitive requirement advice. Students can save drafts and resume. Schema upgrades never silently rewrite previously signed forms.

**ON-04 Review.** Show a profile summary before the first recommendation. Students can correct their own supplied information. An advisor may confirm or dispute a fact without overwriting the original source. Material changes invalidate cached recommendations and flag pending forms for review.

## 6 Knowledge management

**KN-01 Inputs.** Accept PDF, DOCX, plain text, Markdown, and pasted text in MVP. Convert text entries to versioned sources. Suggested initial limits are 25 MiB per file and 200 pages, configurable by policy. Reject encrypted, malformed, unsupported, or oversized files with a clear reason. Scanned documents enter OCR processing and must be reviewed when extraction quality is insufficient. No arbitrary remote URL fetching in MVP.

**KN-02 Scope.** Sources have institution, department or college, program, track, catalog year range, effective dates, document class, authority rank, owner, visibility, and version. Student-specific sources also have an explicit student membership identifier. An advisor cannot publish institution-wide policy. One source version belongs to one scope; broaden access through reviewed publication, not by copying private chunks into a public index.

**KN-03 Pipeline.** Use upload authorization, quarantine, file validation and malware checks, isolated extraction/OCR, metadata review, chunking, embedding, validation, and publication. States are uploaded, scanning, extracting, needs_review, indexing, ready_for_review, published, failed, superseded, and archived. Retriable jobs are idempotent by source hash, version, embedding configuration, and chunker version.

**KN-04 Publication.** Retrieval uses only published versions within their effective scope. Replacement versions are built separately; a transaction switches the active version only after all chunks and checks pass. Failure keeps the previous published version active. Warn about conflicts and duplicate catalogs before publishing. Record the approving publisher and reason. A manager can publish their own department material in MVP; an optional second approver can be enabled later.

**KN-05 Tuning.** Separate structured academic rules from model-behavior instructions and factual documents. Managers may customize department terminology and clarification questions through allowed fields. They cannot override authorization, citation requirements, safety restrictions, or signature workflow. Super admins may version global prompts with evaluation and rollback gates. Prompt text is not executable code.

**KN-06 Removal.** Withdrawn sources stop being retrievable immediately through active-version filtering, including during cache hits and queued jobs. Delete embeddings asynchronously with retry. Signed forms retain an authorized frozen evidence snapshot under retention policy. Historical messages show that a source was withdrawn; do not silently replace historical citations with a newer version.

**KN-07 Citation access.** Citation links resolve through an authorized endpoint to an exact version, page or heading, excerpt, and publication date. Storage objects are private; short-lived download URLs are issued only after a current access check. A filename and chunk title may themselves contain private information and must be filtered too.

## 7 RAG and advising behavior

**RG-01 Retrieval sequence.** Authenticate and resolve membership, load the student's applicable academic facts and active advisor guidance, resolve authorized source IDs, apply institution/department/student/catalog/date filters inside retrieval, run hybrid keyword and vector retrieval, rerank the authorized candidates, assemble a bounded evidence context, generate a structured response, validate citations and policy constraints, persist the result, and release it to the student. Recheck relevant authorization and version epochs before committing output.

Filtering after global top-k retrieval is prohibited. Database row policies and query filters provide layered protection. Do not give raw vector search to browsers. Cache keys include institution, subject or permitted visibility set, relationship epoch, catalog/profile version, knowledge release, prompt version, and model/embedding identifiers. Disable cross-user response caching in MVP.

**RG-02 Answers.** Course-specific recommendations identify assumptions, applicable catalog year, prerequisites, constraints, next actions, and citations. Each material institutional claim maps to a supporting excerpt. Generated citations reference only retrieved authorized chunks; fabricated IDs are rejected. Separate confirmed requirements from student preferences and tentative recommendations. A course schedule is not an enrollment guarantee.

**RG-03 Deterministic constraints.** Check prerequisite expressions, credit limits, required course groups, course repeat restrictions, and mutually exclusive choices using structured, versioned rules where available. Use program-owned data rather than having an LLM invent these rules. Unknown offerings and unstructured equivalencies trigger a qualifier or human review. Never declare a student eligible for graduation solely from a generated answer.

**RG-04 Instruction priority.** Platform security and workflow controls always apply. Institutional policies and approved scope rules define academic constraints. Relevant active advisor guidance receives priority over generic planning suggestions and the agent's preferences. Verified exception records may modify a requirement only when the institution's authorized approver, affected rule, validity, and evidence are recorded. An ordinary advisor message is not a policy waiver. Conflicts between guidance and official requirements trigger explanation and escalation rather than silent override.

**RG-05 Advisor event behavior.** Store advisor messages as author_type=advisor, with separate student_visible_guidance and staff_only_note types. Guidance requires a student/chat scope, effective period, author, version, and optional superseded instruction. Persist and notify participants, but do not enqueue model generation. On the next student question, include relevant active guidance as a typed high-priority input. Provide an explicit advisor action to request an AI draft if needed; drafts are not auto-posted to students. Staff-only notes never enter student-facing prompts or generated summaries.

**RG-06 Clarification and abstention.** Ask targeted questions for missing program, catalog, completion facts, or ambiguous goals. Abstain from a definitive answer when evidence is missing, stale, contradictory, outside scope, or fails validation. Confidence is a calibrated evaluation outcome using retrieval coverage and validation, not the model's self-reported number. Display an explanation and a human advisor action. Do not promise an answer or invent an advisor response time.

**RG-07 Injection resistance.** Treat student text, source text, filenames, and retrieved snippets as untrusted data. They cannot alter roles, source access, prompts, publication states, or signatures. No arbitrary shell, URL, SQL, or email tools are available to the advising model. Backend services perform authorized actions through deterministic handlers after user intent confirmation where applicable.

**RG-08 Output delivery.** In MVP, validate the complete response before releasing it; show progress events rather than unvalidated token text. Persist message status pending, completed, blocked, or failed. A retry does not create duplicate student messages. Cancel stale generation if the profile, assignment, guidance, or relevant knowledge version changes while it runs. Record evidence IDs and versions for reproducibility without logging unrestricted prompt content.

**RG-09 Plan versions.** Saving a recommendation creates a versioned plan linked to profile facts, evidence versions, active guidance, and constraints. Students can compare revisions. A saved plan is a draft until signed and approved; accepting a chat response alone does not approve a plan or register courses.

## 8 Human advisor escalation and notifications

**HU-01 Triggers.** Students can request an advisor at any point. The backend also offers escalation for insufficient evidence, inconsistent policies, unsupported exceptions, or failed constraints. A student action creates a case and confirms receipt in the UI.

**HU-02 Routing.** Route to the student's current primary advisor. If no eligible advisor exists or the advisor is inactive, route to the department manager's assignment queue. Cases carry student, department, related chat, question, approved context summary, reason, priority, status, assignee, and timestamps. The advisor opens the authorized chat and responds as a human.

**HU-03 Lifecycle.** States are open, assigned, in_progress, waiting_for_student, resolved, and cancelled. Reopening records a new event. Resolution records the responsible person and disposition. Model recovery does not automatically close a human case.

**HU-04 Delivery.** Use a transactional outbox committed with the case or form event, asynchronous delivery, idempotency, bounded retries, exponential backoff, and a dead-letter queue. In-app notifications are the source of truth. Email contains an event description and authenticated link, never transcript text, grades, private documents, or a signed form attachment. Reauthorize recipients before delivery. A failed email does not remove the case.

**HU-05 Operations.** Department managers configure business-hour service targets and escalation timers; a proposed pilot target is acknowledgement within two business days. Timers use the department timezone and calendar. Display case status rather than a guaranteed resolution date. Group duplicate requests for the same unresolved question; preserve the student's individual messages.

## 9 Advising forms and signatures

**FO-01 Initiation.** A student may initiate a form from a saved plan after seeing a complete preview. Require active student membership, an active assigned advisor, an eligible manager signer, required profile fields, a valid template, and no unresolved blocking policy conflict. The form identifies term, program, catalog, proposed courses, rationale, evidence, and unresolved nonblocking assumptions.

**FO-02 Immutable revisions.** Each revision freezes template version, plan, academic facts, course data, citations, advisor guidance, expected signers, and canonical content hash. Create a human-readable PDF artifact from that revision. The hash covers canonical content; each generated artifact has its own checksum. Artifacts remain pending until durable upload succeeds, and cannot be signed while pending. Do not claim a content hash proves a person's identity.

**FO-03 Signature capture.** Require a full preview, a clear intent statement, an affirmative control, typed name or initials, current authenticated identity, and recent authentication. Record signer role, subject, timestamp from the server, revision ID, content hash, consent-text version, method, and audit event. Collect network/client metadata only if approved and documented. Never accept a signer ID or timestamp supplied by the browser as authority.

**FO-04 Sequence.** Student signs and submits to the advisor. Advisor reviews and either signs, returns for changes, or declines with a reason. Advisor signature routes to the manager. Manager reviews and either signs, returns, or declines. Completion requires all three signatures on the same revision. No model can sign, and a super admin cannot bypass sequence by editing state.

**FO-05 Changes.** A return creates an editable successor revision. Any material content change requires a new revision and all signatures again. Preserve prior revisions, reasons, and signatures. Reassignment or eligibility changes place a pending form on hold until a manager revalidates signers; any signer change creates a new revision. A changed policy or profile flags pending forms for review before further signing. Completed forms are immutable and may be superseded by a newly signed form.

**FO-06 Concurrency.** Signing and state transitions use row locks or compare-and-swap with revision ETag and idempotency keys. A stale preview returns 409 and requires another review. Two concurrent sign requests produce one signature. Enforce unique revision/step constraints in the database. Store notifications via the same transaction's outbox.

**FO-07 Access.** Students download their own completed forms; assigned advisors and scoped managers can view authorized forms. Secretaries see routing status only by default. Export and verification endpoints apply the same permissions as the UI. Signed artifact access, return reasons, holds, and signature events are audited.

These are electronic signatures. Whether initials satisfy the institution's requirements, and whether a certificate-backed digital signature or third-party provider is required, must be determined before production use. The product makes no universal legal-validity claim.

## 10 State transitions

| Object | Allowed transitions | Guard |
| --- | --- | --- |
| Membership | pending → active or rejected; active → suspended or revoked; suspended → active or revoked | Eligible approver, valid scope, audited reason |
| Knowledge version | uploaded → scanning → extracting → indexing → ready_for_review → published | Clean extraction, complete index, approved metadata |
| Knowledge exception | extracting → needs_review; any processing stage → failed; published → superseded or archived | Review or retry preserves prior release |
| Form | draft → awaiting_advisor after student signature | All preconditions and frozen revision |
| Form | awaiting_advisor → awaiting_manager after advisor signature | Assigned advisor, current revision |
| Form | awaiting_manager → completed after manager signature | Eligible manager, prior signatures |
| Form | awaiting_advisor or awaiting_manager → returned or declined | Reviewer records reason |
| Form | returned → draft successor revision | New revision invalidates prior signature sequence |
| Form | pending state → on_hold → previous pending state or returned | Revalidate policy and signers; changed content returns |
| Form | draft or pending state → withdrawn | Student or authorized manager reason; retained audit |

Completed forms cannot transition to editable draft. Corrections use a successor form. A held form records its previous state; release without changes restores it only after eligibility and version checks pass.

## 11 Frontend requirements

Use role-aware navigation with a clear active department indicator for multi-scope staff. A user with several grants can switch scopes without mixing cached data. The UI must not infer authorization from hidden buttons; server permissions control every action.

| Surface | Required behavior |
| --- | --- |
| Registration and requests | Verify email, select department and requested role, show pending/rejected status |
| Student workspace | Onboarding progress, current profile, cited chat, advisor identity, human-help status, saved plans, forms |
| Chat | Distinct student, advisor, and assistant authors; source drawer; guidance indicator; retry and abstention states |
| Advisor workspace | Assigned roster, pending cases, student context, guidance composer, scoped upload, forms to review |
| Secretary workspace | Student request queue, invitations, assignments, membership status; no default transcript access |
| Manager workspace | Staff approval and assignment, department knowledge, pipeline status, cases, signature queue |
| Admin workspace | Institution structure, scoped grants, global knowledge, audit search, model and release configuration |
| Form workspace | Exact revision preview, consent, initials/name, signer order, holds, returned reasons, completed download |

Target keyboard operation, readable focus states, semantic labels, screen-reader announcements, appropriate contrast, and responsive layouts at 360, 768, and 1280 CSS pixels. WCAG 2.2 AA is a proposed verification target. Save partial onboarding, prevent duplicate submissions, and show explicit loading, empty, forbidden, failed, stale, and offline states. Do not persist student transcripts or authentication tokens in localStorage. Never render unsanitized source HTML or model output. Clear scoped caches at logout, role changes, and department switches.

## 12 Backend and data model

Use a modular backend with identity/authorization, memberships, assignments, profiles, knowledge, retrieval, conversations, cases, forms, notifications, and audit modules. A relational database is the source of truth; a vector index supports retrieval but never grants access.

| Entity | Principal fields and constraints |
| --- | --- |
| Institution and OrgUnit | Institution ID, parent unit, college/department type, timezone; no cycles |
| User and Identity | Immutable internal ID, external subject/provider, verified email, status; unique provider/subject |
| RoleGrant | User, role, institution, scope, capability set, validity, approver; no client-controlled capabilities |
| MembershipRequest and Invitation | Requested role/scope, normalized email, status, approver, expiry, token hash |
| StudentMembership and AdvisorAssignment | Student, department, status, primary advisor, effective dates; one active primary assignment |
| ProfileVersion and AcademicFact | Immutable snapshot, provenance, catalog year, verification and disputed status |
| Source and SourceVersion | Scope, owner, classification, version, hash, publication state, validity, authority |
| Chunk and Embedding | Source version, locator, text, embedding model/revision/dimension, index release |
| RuleSet and PromptRelease | Scope, typed rule schema, version, approval, evaluation result, rollback pointer |
| Conversation and Message | Student membership, author type, visibility, context version, status, idempotency key |
| AdvisorGuidance | Student/chat scope, visibility, validity, supersession, author, text hash |
| RetrievalRun and Citation | Query trace ID, authorized evidence IDs, scores, filter/version identifiers, answer mapping |
| PlanVersion | Profile/evidence/guidance snapshot and constraint outcomes |
| EscalationCase | Subject, assignee, reason, state, conversation link, SLA policy |
| Form and FormRevision | Term, template, immutable content, checksum, expected signers, state, row version |
| Signature | Revision/step uniqueness, signer identity, method, consent version, server timestamp |
| Outbox and DeliveryAttempt | Event, recipient, retry state, deduplication key; no sensitive email body |
| AuditEvent | Actor, action, subject, scope, result, reason, correlation ID, timestamp |

Enforce foreign keys, unique constraints, soft-revocation, and transactional updates. Student-only documents bind to a student membership, not merely to an email. Use database row-level security where practical, with a non-owner application role that cannot bypass policies. Transaction-local scope prevents pooled-connection context leakage. Privileged jobs require explicit narrowly scoped service roles. Store UTC timestamps and use department timezones for display and deadlines.

## 13 API contract requirements

All routes below use /api/v1. They are the contract inventory to implement, not claims of existing endpoints. Generate OpenAPI and a typed frontend client during implementation. Pagination uses opaque cursors and a configured maximum page size. Errors include code, human message, field errors where applicable, and correlation ID without secrets.

| Method and route | Purpose and critical guard |
| --- | --- |
| GET /me | Current identity, active grants, capabilities, scope epoch |
| POST /membership-requests | Verified identity; no self-grant |
| POST /invitations | Allowed role and scope; unique pending email/scope/role |
| POST /invitations/accept | One-use verified identity binding |
| POST /membership-requests/{id}/approve or /reject | Server-selected approver policy, transactional grant |
| PATCH /memberships/{id} | Suspend/revoke/reactivate; scope and last-admin protection |
| PUT /students/{id}/advisor | Eligible scoped advisor; relationship epoch increment |
| GET or PATCH /students/{id}/profile | Own or authorized staff; ETag for changes |
| POST /sources/uploads and /sources/text | Authorized scope; restricted upload target |
| POST /sources/{id}/versions/{version}/publish | Publisher grant, clean pipeline, evaluation gate |
| POST /sources/{id}/withdraw | Immediate retrieval exclusion and audit |
| GET /citations/{id} | Current permission, exact frozen locator |
| POST /conversations/{id}/messages | Student author or explicit authorized human message type |
| POST /conversations/{id}/guidance | Assigned advisor; does not enqueue model response |
| POST /guidance/{id}/supersede | Assigned advisor, append-only replacement |
| POST /conversations/{id}/advisor-drafts | Explicit advisor request; staff-only result |
| POST /cases and PATCH /cases/{id} | Student or authorized staff; valid state transition |
| POST /plans and POST /plans/{id}/forms | Authorized student, validated snapshot |
| GET /forms/{id}/revisions/{revision} | Authorized exact preview and ETag |
| POST /forms/{id}/sign | Revision ETag, step, consent, recent auth, idempotency |
| POST /forms/{id}/return or /decline | Current reviewer, reason, immutable history |
| POST /forms/{id}/withdraw | Eligible student/manager, state validation |
| GET /forms/{id}/artifact | Authorized signed download |
| GET /notifications and POST /notifications/{id}/read | Own recipient only |
| GET /audit-events | Authorized scope and minimum necessary filters |

Use secure HttpOnly SameSite cookies through a same-origin web entry point, CSRF protection on mutations, explicit CORS allowlists when needed, and session revocation. If bearer tokens are chosen instead, document that decision and keep tokens out of browser storage. Streaming progress requires authenticated event access and per-event relationship checks. Never pass a user-selected system prompt, model endpoint, or raw retrieval filter to inference.

## 14 Proposed Google Cloud architecture

Deploy the frontend and API as separate CPU workloads on private GKE Standard node pools and vLLM on a dedicated GPU node pool. Expose the frontend and /api through one HTTPS external entry point. Keep vLLM, the embedding service, the database, and workers private. This single-cluster application topology avoids introducing a second hosting platform and a cross-platform network path in the first release.

Use Cloud SQL for PostgreSQL with pgvector plus full-text search for the pilot, Cloud Storage for quarantined and published source/artifact objects, Pub/Sub for document processing and asynchronous jobs, Artifact Registry for immutable container artifacts, Secret Manager for secrets, and Cloud Logging/Monitoring for redacted telemetry. Use Workload Identity Federation for GKE and distinct service accounts for API, ingestion, notifications, and inference. Retain a separate application audit store with restricted writes and retention settings.

vLLM serves the selected open-weight chat model through an OpenAI-compatible interface. Embeddings require a separately selected embedding model/service; the chat model is not assumed to support embeddings. The API uses an internal model adapter with fixed endpoint and served-model alias. Never expose a model API key to a browser. The service must have a private network boundary and authentication; compatibility with an API schema does not provide application authorization.

Model, GPU type/count, context length, quantization, concurrent sequences, and replica count require benchmarking before selection. Record model license, immutable revision, vLLM image digest, chat template, embedding version, and evaluation report. GKE and vLLM guidance supports GPU serving; it does not establish that a particular model fits any selected GPU. See the deployment guide and source register.

## 15 Quality and operating targets

The following are proposed pilot acceptance targets, not measured performance claims. Measure them on a frozen synthetic/de-identified test set and a recorded load profile before adopting them as service commitments.

| Measure | Initial target and measurement |
| --- | --- |
| Authorization | Zero unauthorized records, chunks, citations, exports, cache hits, or notifications in negative tests |
| Grounding | At least 95% of reviewed material institutional claims supported by the attached excerpts on a 200-question pilot set |
| Retrieval | At least 90% Recall@10 on answerable questions with labeled authoritative passages |
| Abstention | At least 95% of unanswerable or conflicting cases avoid a definitive unsupported answer |
| Advisor behavior | 100% of advisor guidance events avoid automatic assistant replies; relevant active guidance used in follow-up tests |
| Form integrity | No skipped steps, duplicate signatures, or successful stale revisions in concurrency tests |
| API latency | p95 under 1 second for ordinary non-inference reads at the documented pilot load |
| Chat latency | Proposed p95 complete validated answer under 20 seconds at 20 concurrent chats and 8k input/1k output tokens; adjust after GPU benchmark |
| Availability | Pilot target 99.5% monthly for core application; measure model availability separately |
| Notification delivery | At least 99% of accepted events reach in-app queue within 1 minute excluding documented maintenance |
| Recovery | Proposed RPO 24 hours and RTO 8 hours; production targets require approved backup/restore design |
| Accessibility | Keyboard and screen-reader checks on all critical journeys; no critical automated findings |

Record latency distributions, queue depth, extraction failure rate, publication delay, unresolved cases, form return reasons, GPU utilization, tokens per second, and cost per completed advising session. LLM grading can supplement human review but cannot be the only grounding or privacy gate. Log structured IDs and error codes; do not log transcripts, signed URLs, prompts, or uploaded contents by default.

## 16 Privacy security and retention

Treat conversations, academic profiles, source documents, and advising forms as sensitive institutional records. FERPA applicability and the institution's disclosure rules must be reviewed by its responsible office. Official guidance limits staff disclosure to legitimate educational interests; super admin visibility is therefore an audited product capability, not an entitlement to unrestricted operational use. See source S8.

Use encryption in transit and at rest, private buckets, short-lived authorized access, staff MFA, least-privilege service accounts, secret rotation, dependency scanning, isolated parsers, and upload quotas. Protect logs, embeddings, backups, and caches as sensitive records. Disable training reuse and external model telemetry unless explicitly approved. Vendor and model services must satisfy the institution's data terms.

The institution must approve a record-class retention schedule before real student data enters production. Keep that schedule configurable for profiles, chat, cases, source versions, forms, audit, and backups. Default pilot data is synthetic and may be purged after 30 days. Account suspension does not immediately destroy records. Authorized deletion requests remove searchable chunks, caches, objects, and database records as permitted, while legal holds and signature-record requirements are handled through the approved policy. Backup expiry and restored-data deletion reconciliation must be documented. Never promise immediate deletion from immutable backups.

## 17 Release plan and acceptance

| Phase | Deliverable | Exit condition |
| --- | --- | --- |
| 0 Decisions and contracts | Scope decisions, permission model, synthetic fixtures, schema/OpenAPI plan, threat model | Institution owner approves role and record boundaries |
| 1 Identity and assignments | Authentication, invitations, approvals, scoped grants, rosters, onboarding | Positive and negative access tests pass |
| 2 Knowledge and retrieval | Upload pipeline, publication, pgvector/full-text retrieval, citations | Source isolation, withdrawal, and retrieval evaluation pass |
| 3 Chat and human help | Validated answers, advisor guidance, cases, outbox notifications | Guidance priority, no auto-reply, and escalation tests pass |
| 4 Forms | Immutable revisions, preview, sequential signatures, PDF artifacts | State, stale-sign, race, and artifact-access tests pass |
| 5 Cloud pilot | GKE/vLLM, CI/CD, observability, backup, rollback, pilot usability | Benchmarks and restore rehearsal pass; privacy/signature decisions approved |

Do not compress phases into an unvalidated schedule. Team size, procurement, identity integration, GPU quota, and institutional review determine dates. The implementation backlog supplies task-sized work items.

Required end-to-end demonstrations: a directly invited student activates their account and advisor assignment; a self-registered student is approved by a secretary; a manager request requires super admin approval; a manager publishes a catalog with citations; an advisor adds guidance with no AI reply; a subsequent student question uses that guidance; missing evidence creates an advisor case; a student signs a plan followed by advisor and manager; a returned form requires a new signature sequence; an old advisor loses access immediately after reassignment; a withdrawn source cannot be retrieved or downloaded by an unauthorized user.

## 18 Risks and unresolved choices

| Risk | Required response |
| --- | --- |
| Incorrect catalog or stale course data | Validity metadata, policy owner review, evaluation, citations, abstention |
| Cross-department or cross-student leakage | Server-side scope and relationship checks, filtered retrieval, RLS, negative tests |
| Hidden staff notes leaking in chat | Separate visibility types and strict prompt construction tests |
| Advisor recommendation conflicts with requirements | Explicit conflict display, no implied waiver, human resolution |
| Model or GPU cannot meet pilot load | Benchmark, reduce context/concurrency or change hardware after evaluation |
| False signature assurance | Institution-approved method, authenticated intent, immutable revisions, no universal validity claim |
| Department transfer or staff departure stalls forms | Holds, signer revalidation, manager assignment queue |
| Expensive idle GPU and parser abuse | Budget alerts, bounded uploads, quotas, explicit dev shutdown procedure |
| Unapproved use of student data | Institutional review and synthetic-only development |

## 19 Requirement traceability

| Requested behavior | Specification |
| --- | --- |
| Admin users and global history/documents | Sections 3, 4, 6, 12, 16 |
| Manager department approval and ownership | Sections 2, 3, 4, 6 |
| Staff/student assignment and removal | ID-02 through ID-06 |
| Manager documents and RAG instructions | KN-01 through KN-07 and RG-04 |
| Advisor chat history and priority input | Section 3 and RG-04 through RG-05 |
| Advisor student-specific uploads | KN-02 and scope matrix |
| Student secretary request or direct assignment | ID-02 and ID-03 |
| Initial student questions | ON-01 through ON-04 |
| Grounded student recommendations | RG-01 through RG-09 |
| Advisor notification and human loop | HU-01 through HU-05 |
| Student then advisor then manager signatures | FO-01 through FO-07 |
| Google Cloud with vLLM | Section 14 and GOOGLE_CLOUD_DEVELOPMENT.md |

## 20 Supporting documents

Read ACCESS_CONTROL.md for implementation decisions, RAG_DESIGN.md for the retrieval contract and test cases, API_AND_EVENTS.md for concrete payload examples, IMPLEMENTATION_BACKLOG.md for development slices, GOOGLE_CLOUD_DEVELOPMENT.md for deployment and operations, CODEX_GUIDE.md for the coding workflow, and SOURCES.md for official technical references. The requirements above control if an example template is less restrictive.
