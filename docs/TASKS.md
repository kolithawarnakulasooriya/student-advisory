# Student advisory agent task list

Version 1.1 • November 11, 2026 • 61 implementation tasks • Statuses reflect recorded acceptance evidence

This file breaks the [implementation backlog](IMPLEMENTATION_BACKLOG.md) into assignable work for coding agents. The [PRD](PRD.md) controls product behavior. This is a work plan; the application and cloud resources are not implemented by this file.

## How agents use this file

Read [AGENTS.md](../AGENTS.md), the applicable frontend/backend instructions, and the linked design documents before editing. Select a task whose dependencies have completed acceptance evidence. The owner below is a recommended specialist perspective, not an automatically launched agent. One agent may complete several tasks; ownership does not grant cloud permissions or access to student records.

Use the task ID in branches, PR descriptions, test reports, and handoffs. Before starting, record an assignee and mark the task in progress in its status line. When blocked, record the exact dependency or missing decision. Mark the checkbox complete only when deliverables and acceptance criteria are met and the required checks have actually run. Never infer completion from an earlier task's checkbox alone.

Each task includes its owner, dependencies, PRD requirements, intended deliverables, work scope, acceptance criteria, and verification. Paths for application code are proposed destinations to create when scaffolding, not files that already exist. Implementation checkboxes reflect recorded acceptance evidence; see the Release 0.1 handoff for foundation-only completion boundaries.

## Shared completion criteria

- [ ] Read the task's requirements and relevant design contract; preserve scope and source applicability.
- [ ] Implement the affected database/API/worker/UI contract or hand off an explicit interface to the dependent task.
- [ ] Add meaningful behavior checks for changed authorization, state, retrieval, or side effects; use synthetic data only.
- [ ] Update OpenAPI, migrations, generated client, event schemas, and instructions when affected.
- [ ] Record real check commands/results and untested limitations. Do not claim mock results establish production performance.
- [ ] Review errors, logs, caches, downloads, jobs, and exports for sensitive data exposure.
- [ ] Attach a concise completion handoff and update task status after review.

These shared checkboxes are a reusable checklist, not additional implementation tasks. Each task must satisfy the relevant items individually.

## Specialist ownership

| Owner | Primary responsibilities | Reference |
| --- | --- | --- |
| Product architect | Decisions, requirement traceability, institutional pilot inputs | [Brief](../.codex/personas/product-architect.md) |
| Backend engineer | Identity, authorization, transactions, jobs, forms | [Brief](../.codex/personas/backend-engineer.md) |
| Frontend engineer | Role journeys, typed contracts, safe rendering, accessible UI | [Brief](../.codex/personas/frontend-engineer.md) |
| Retrieval engineer | Ingestion/indexing interfaces, retrieval, guidance, academic checks, evaluation | [Brief](../.codex/personas/rag-engineer.md) |
| Cloud engineer | IaC, private services, identities, GPU/vLLM, CI/CD, recovery | [Brief](../.codex/personas/cloud-engineer.md) |
| QA reviewer | Acceptance, isolation, concurrency, accessibility, end-to-end evidence | [Brief](../.codex/personas/qa-reviewer.md) |

Use the [security brief](../.codex/personas/security-reviewer.md) for sensitive feature reviews. Review responsibility is separate from task implementation ownership. Assign frontend/backend subtasks explicitly when a task crosses both; the listed owner integrates the result.

## Ordering and coordination

Follow dependency IDs rather than heading order. Within B01, frontend and backend scaffolding can be separate work after contracts exist. Complete T061 college/department administration after Release 0.2 and before Release 0.3 onboarding. After authorization, onboarding and document ingestion can progress separately. Cloud planning may proceed after scaffolding and required environment inputs; final cloud deployment requires the application/model interfaces. B16 dashboard and accessibility work completes earlier UI slices rather than postponing all frontend work.

If multiple agents are explicitly assigned, use isolated branches/worktrees and reserve shared migrations, OpenAPI, generated-client changes, and IaC state for one integration owner at a time. Do not edit the same migration or run competing cloud applies. Merge prerequisite interfaces before dependent implementation. No agents are launched by this document.

The production pilot is blocked until identity integration, privacy/retention decisions, signature acceptance, model license, environment/budget, evaluations, and recovery evidence are resolved. These gates do not block synthetic local scaffolding. Do not request production access merely to finish a local development task.

## Task index

| Stage | Task IDs | Focus |
| --- | --- | --- |
| Phase 0 Decisions and contracts | T001–T004 | Confirm role and scope decisions through record pilot policy dependencies |
| B01 Repository and local development | T005–T007 | Scaffold the backend through add disposable database and local ci |
| B02 Identity and organization | T008–T010, T061 | Organization model, registration/session UI, and administrative college/department management |
| B03 Authorization and audit | T011–T013 | Implement capability and relationship checks through implement administrative audit and oversight history |
| B04 Invitations approvals and account lifecycle | T014–T016 | Implement email invitations through implement suspension and delegated staff management |
| B05 Advisor assignments and revocation | T017–T018 | Implement assignment and reassignment through cancel stale jobs caches and streams |
| B06 Student onboarding | T019–T021 | Implement academic profile versions through propagate material profile changes |
| B07 Documents and extraction | T022–T024 | Implement authorized uploads and pasted text through build source management and pipeline status |
| B08 Knowledge publication and tuning | T025–T027 | Implement chunks and embedding versions through implement rules and prompt release controls |
| B09 Retrieval and model responses | T028–T030 | Implement filtered hybrid retrieval through implement grounded structured responses |
| B10 Student chat | T031–T032 | Implement versioned conversations and generation jobs through build cited chat and evidence drawer |
| B11 Advisor guidance | T033–T035 | Implement guidance and private notes through build advisor conversation tools |
| B12 Human cases and notifications | T036–T038 | Implement outbox publishing and delivery deduplication through implement notifications email and case views |
| B13 Plans and academic validation | T039–T040 | Implement deterministic academic checks through implement saved plan versions and comparison |
| B14 Forms and artifacts | T041–T043 | Implement versioned form templates and eligibility through build exact revision preview and consent ui |
| B15 Signature workflow | T044–T046 | Implement student signature transaction through implement returns holds withdrawal and supersession |
| B16 Complete role workspaces and accessibility | T047–T049 | Complete admin manager and secretary dashboards through verify accessibility and responsive layouts |
| B17 Google Cloud infrastructure and private inference | T050–T053 | Prepare environment inventory and IaC plan through deploy frontend backend and workers in development |
| B18 Evaluation delivery and operations | T054–T057 | Build frozen advising evaluation and release gate through run full security state and load acceptance |
| B19 Recovery and pilot readiness | T058–T060 | Rehearse backup restore and release rollback through complete operator and end-user handoff |

## Phase 0 Decisions and contracts

### T001 Confirm role and scope decisions

- [x] Status: Completed; assignee: Codex; owner perspective: Product architect.

Release 0.1 evidence: role/scope defaults and unresolved institutional choices recorded in [role decisions](decisions/roles.md).

Dependencies: None. Requirements: PRD sections 2–4.

Deliverables: docs/decisions/roles.md.

Work: Document secretary delegation, platform-admin grants, college scope, primary advisor policy, and transfer behavior.

Acceptance: Every role has an explicit scope and delegation ceiling; unresolved choices are labeled and do not grant access.

Verification: Compare the decision table against the PRD permission matrix with synthetic role examples.

### T002 Define API and event contracts

- [ ] Status: Inprogress; assignee: Codex; owner perspective: Backend engineer.

Release 0.1 subset completed: foundation OpenAPI, generated frontend types/client wrapper, structured errors and self/scope contracts. Workflow OpenAPI, bounded signed cursors, idempotency/ETags and invitation outbox metadata completed in Release 0.2; full event publication and later-resource schemas remain open; see [foundation contract](decisions/foundation-contract.md).

Postman subset completed: all 51 current API operations (including T061) with generated collection/local environment, session/CSRF scripting, idempotency/revision examples and CI drift checks. Official-schema/body validation passed; Newman smoke passed 25 assertions and registration/verification/approval with idempotent retry passed 34 assertions. See [Postman instructions](../postman/README.md). Full later-resource/event contracts remain open.

Dependencies: T001. Requirements: PRD sections 12–13.

Deliverables: backend/contracts/ and frontend generated-client interface.

Work: Define payloads, error codes, pagination, identity inputs, idempotency rules, ETags, and versioned event envelopes before feature implementation.

Acceptance: No client payload can select its own actor, capabilities, model endpoint, or signature timestamp.

Verification: Validate contract schemas and review one allowed and one denied request per sensitive resource.

### T003 Define synthetic academic fixtures

- [ ] Status: Inprogress; assignee: Codex; owner perspective: Retrieval engineer.

Release 0.1 subset completed: deterministic identity/org fixtures and denied-state accounts in backend/app/seed.py. Release 0.2 adds advisor/delegation/enrollment fixtures and finite-capacity/concurrency cases. Academic catalogs, private sources, contradictory rules and reviewed gold labels remain open; see [test data](decisions/test-data.md).

Dependencies: T001. Requirements: ON-01–04, RG-01–07.

Deliverables: evals/fixtures/ and docs/decisions/test-data.md.

Work: Create two departments, separate students/advisors, a secretary, managers, two catalog years, private sources, and known contradictory rules.

Acceptance: All data is clearly synthetic; expected source applicability and prerequisite outcomes are documented.

Verification: Check fixture isolation and manually review labeled course-rule examples.

### T004 Record pilot policy dependencies

- [x] Status: Completed; assignee: Codex; owner perspective: Product architect.

Release 0.1 evidence: required institutional decision owners and deployment blockers recorded in [pilot inputs](decisions/pilot-inputs.md); no real-data approvals claimed.

Dependencies: T001. Requirements: PRD sections 2, 9, 14–16.

Deliverables: docs/decisions/pilot-inputs.md.

Work: Track identity provider, source owners, form template, signature method, retention, notification provider, region, model license, and budget with decision owners.

Acceptance: Each unresolved input states which deployment task it blocks; synthetic development remains possible.

Verification: Review the register before provisioning or handling real student records.

## B01 Repository and local development

### T005 Scaffold the backend

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.1 completed: backend scaffold, locked tooling, health/configuration/error checks; see [handoff](RELEASE_0_1.md).

Dependencies: T002, T003. Requirements: PRD section 12.

Deliverables: backend/app/, backend/pyproject.toml, backend/uv.lock.

Work: Create FastAPI modules, validated configuration, health endpoints, structured errors, and pinned lint/type/test tooling.

Acceptance: The backend starts with synthetic development settings and rejects missing required configuration.

Verification: Run actual lint/type checks and a health/configuration smoke test; record commands.

### T006 Scaffold the frontend

- [x] Status: Completed; assignee: Codex; owner perspective: Frontend engineer.

Release 0.1 completed: Next.js shell, generated client workflow and actual component/type/lint scripts; see [handoff](RELEASE_0_1.md).

Dependencies: T002. Requirements: PRD section 11.

Deliverables: frontend/app/, frontend/package.json, frontend/package-lock.json.

Work: Create Next.js TypeScript shell, generated API-client workflow, semantic layout, error boundary, and test scripts while preserving AGENTS.md.

Acceptance: The frontend starts and renders connection/loading/failure states against the development API.

Verification: Run actual lint, typecheck, and component checks.

### T007 Add disposable database and local CI

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.1 completed: digest-pinned pgvector Compose service, fresh migrations, guarded seed/reset and CI definition. Local checks passed; hosted GitHub Actions has not run. See [handoff](RELEASE_0_1.md).

Dependencies: T005, T006. Requirements: PRD sections 12, 15.

Deliverables: local development configuration, backend/alembic/, .github/workflows/ci.yml.

Work: Provide PostgreSQL/pgvector test service, migration baseline, synthetic seed command, and CI checks with locked dependencies.

Acceptance: A fresh checkout can create and reset a disposable database without production credentials.

Verification: Run migrations and smoke checks on a clean test database; verify secrets are excluded from artifacts.

## B02 Identity and organization

### T008 Implement institution and organization model

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.1 completed: scoped organization reads, hierarchy/timezone/database constraints and negative integration checks; see [handoff](RELEASE_0_1.md).

Dependencies: T007, T001. Requirements: PRD section 12.

Deliverables: backend organization models, migrations, and scoped org endpoints.

Work: Create institution/college/department relationships with timezone, unique identifiers, and cycle prevention.

Acceptance: Invalid cross-institution parents and organization cycles are rejected.

Verification: Run database constraints and organization hierarchy integration tests.

### T061 Implement college and department administration

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Delivered after Release 0.2 and before Release 0.3 student onboarding. This task extends T008's completed model/read interfaces; department creation previously required synthetic operator seeds. Frontend and authorization verification are required parts of this task, not deferred dashboard placeholders.

Completion evidence: additive migrations 0010–0011, explicit metadata grants, administrative API/UI, safe enrollment/archive and lifecycle integration. Fresh PostgreSQL suite: 107 passed; frontend components: 19 passed; E2E: 29 passed; generated contracts/Postman, build, lint/types and package checks passed. See [T061 handoff](T061_HANDOFF.md).

Dependencies: T008, T011, T012, T013, T016. Requirements: PRD sections 2–3, 11–13; explicit organization-administration addition requested by the user. Record the new capability policy in the PRD and access-control decisions before implementation.

Deliverables: authorized organization mutation APIs and forced-RLS write policies; administrative college/department forms and enrollment controls; audit events; updated OpenAPI, generated frontend/Postman contracts, synthetic fixtures, and setup instructions.

Work:

- Create colleges and departments within an existing institution; edit names, institution-unique codes, and valid timezones while preserving immutable identifiers and hierarchy constraints.
- Permit platform super admins to administer organizations. Allow platform admins only through a separately defined, explicit organization-management capability bounded to authorized institutions and parent units. Managers, secretaries, advisors, and students cannot create departments. Creating an organization never implicitly grants membership, records access, or wider administrative authority.
- Configure whether an active department is open for membership requests, using the existing verified-only membership-options boundary. Keep department-manager appointment as a separate authorized action under existing appointment ceilings; organization-management delegation alone cannot appoint managers.
- Provide archive/restore controls that retain memberships, assignments and history. Reject removal or archival of units with active memberships or active descendants. Prevent new enrollment/invitations under archived units and recheck outstanding requests/invitations on activation. No destructive organization deletion, institution transfer, or populated-unit reparenting is included without a separate approved data plan.
- Require staff MFA, recent authentication, CSRF, idempotency keys and revision checks on administrative mutations. Record successful changes atomically and denied attempts separately; invalidate affected organization selectors and scope-bound UI state.
- Record unresolved institutional naming, ownership and archival rules as assumptions. New institutions, department transfers and automatic expansion of existing college grants remain outside this task.

Acceptance: An authorized super admin can create a college/department, configure request availability, and separately appoint its manager through the UI. Explicitly delegated admins can act only within their granted organization boundaries. Wrong-institution parents, invalid timezones, duplicate codes, cycles, unauthorized writes and stale updates are rejected. Creating a new department does not expand any existing user's effective scope. Archival cannot destroy or orphan active memberships or history.

Verification: Use synthetic PostgreSQL integration tests for the role/delegation matrix, forced RLS and pooled connections, hierarchy constraints, concurrent duplicate creation, revision conflicts, archive/restore safeguards, and request/invitation reauthorization. Exercise admin create → enrollment configuration → authorized manager appointment and wrong-scope denial in browser tests; verify keyboard operation and 360/768/1280 px layouts. Run relevant backend/frontend checks, contract/Postman drift checks, and `python3 scripts/validate_package.py`; record actual results before marking complete.

### T009 Implement verified identity and sessions

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.1 completed for the authorized synthetic-local scope: immutable signed identity assertions, cookie sessions, CSRF, expiry, revocation, and MFA/recent-auth hooks. Live institutional identity integration remains a pilot dependency; see [handoff](RELEASE_0_1.md).

Dependencies: T008. Requirements: ID-01, ID-05, PRD section 13.

Deliverables: backend identity/session module and provider adapter.

Work: Bind immutable provider subject to verified email; validate issuer/audience/expiry; implement secure cookie, CSRF, logout, session revocation, and recent-auth/MFA hooks.

Acceptance: Unverified users cannot activate roles; production rejects mock auth and insecure session settings.

Verification: Test token validation, CSRF, logout/revocation, staff MFA, and production configuration failures.

### T010 Build registration and session UI

- [x] Status: Completed; assignee: Codex; owner perspective: Frontend engineer.

Release 0.1 completed: interactive synthetic registration/verification, account/MFA/expiry recovery, role landing, scope switch and sign-out; 14 browser journeys passed. Real membership requests/approval remain T015. See [handoff](RELEASE_0_1.md).

Dependencies: T006, T009. Requirements: ID-01, PRD section 11.

Deliverables: frontend registration, verification, sign-in, and session components.

Work: Build verified-email and pending-account states plus session expiry and sign-out; keep tokens out of localStorage.

Acceptance: Identity/session failures show clear recovery actions without exposing private records.

Verification: Exercise sign-in, verify, expired session, logout, and browser-storage inspection with synthetic identities.

## B03 Authorization and audit

### T011 Implement capability and relationship checks

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.1 subset completed: server-derived AuthContext, current explicit grants, /me foundation capabilities, centralized organization authorization and multi-role scope isolation. Role ceilings/delegation and student relationships are completed for current resources in Release 0.2 below; future-resource policies remain with their features.

Release 0.2 completed for current resources: explicit capability/appointment ceilings, separate platform authority, scoped student relationships, verified-only enrollment discovery, MFA/recent-auth checks, and delegation denial matrix. Later resources must extend these policies when introduced. See [Release 0.2 evidence](RELEASE_0_2.md).

Dependencies: T009, T002. Requirements: PRD section 3, ID-06.

Deliverables: backend authorization policy module and grant migrations.

Work: Build server-derived AuthContext, role ceilings, scope resolution, student relationships, and action/resource checks; add GET /me capabilities.

Acceptance: Wrong scope, unassigned advisor, pending user, and secretary transcript requests are denied.

Verification: Run a data-driven positive/negative permission matrix including multi-role users.

### T012 Enforce scoped queries and row policies

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.1 subset completed: foundation scoped queries, separate non-owner identity/application roles, FORCE RLS on six foundation tables, missing-context denial and pooled connection reuse tests. Release 0.2 extends current-resource RLS and restricted invitation-worker policies below; future-resource policies remain with their features.

Release 0.2 completed for current tables: additive migrations 0004–0009, forced RLS, scoped writes and counts, short auth transactions, non-owner runtime roles, restricted SMTP consumer, missing-context and pooled-reuse checks. Future-resource policies remain with their features. See [Release 0.2 evidence](RELEASE_0_2.md).

Dependencies: T011. Requirements: PRD section 12, ACCESS_CONTROL.md.

Deliverables: backend query scopes, RLS migrations, DB role setup.

Work: Apply scoped query builders and transaction-local database context under a non-owner application role; restrict background-job roles.

Acceptance: Missing context fails closed and pooled connections cannot carry another user's scope.

Verification: Run real PostgreSQL tests for wrong-department access and pooled connection reuse.

### T013 Implement administrative audit and oversight history

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.2 completed: atomic successful audits, durable independent denial records, append-only runtime access, separately protected reasons, purposeful global reads, and current-access history filtering. See [Release 0.2 evidence](RELEASE_0_2.md).

Dependencies: T011, T012. Requirements: ID-07, PRD sections 3, 16.

Deliverables: backend audit/history module, scoped audit endpoints.

Work: Record privileged reads/writes/denials and expose user/advisor timeline contracts; sensitive reads require an audited reason where specified.

Acceptance: History drill-downs recheck student access and contain no raw prompt/transcript in audit payloads.

Verification: Test scoped audit queries, reason capture, append restrictions, and denied history access.

## B04 Invitations approvals and account lifecycle

### T014 Implement email invitations

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.2 completed: scoped invitation creation/resend/revoke/accept, hash-only tokens, verified target binding, inviter reauthorization, Mailpit delivery, expiry/reuse checks and browser acceptance. Live email remains deferred. See [Release 0.2 evidence](RELEASE_0_2.md).

Dependencies: T011, T012, T010. Requirements: ID-02, ID-04.

Deliverables: backend invitation module and invitation acceptance UI.

Work: Issue hashed single-use expiring tokens; normalize email conservatively; bind verified identity and activate optional preselected assignment only when valid.

Acceptance: An unaccepted invite grants no records; expired/reused tokens and role escalation are rejected.

Verification: Test direct student invite, advisor invite, email mismatch, duplicate invite, expiry, and token reuse.

### T015 Implement requests and approval queues

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.2 completed: self-service requests/status, correctly scoped decision queues, manager requests decided only by platform super admins, required advisor activation, transactional decisions, idempotency and stale/concurrent-decision tests. See [Release 0.2 evidence](RELEASE_0_2.md).

Dependencies: T014. Requirements: ID-03–04.

Deliverables: backend request/decision module, frontend approval and request-status views.

Work: Route managers to super admins, advisors to managers, students to secretary/manager; commit grant plus decision transactionally with reason.

Acceptance: No self-approval or duplicate active grant is possible; a pending student sees status only.

Verification: Test each request route, duplicate decisions, wrong scope, rejection, and approval races.

### T016 Implement suspension and delegated staff management

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.2 completed: membership lifecycle, individual secretary delegation, scoped platform-admin ceilings, audited one-time bootstrap, serialized last-super-admin protection, immediate account/session suspension and explicit grant restoration. See [Release 0.2 evidence](RELEASE_0_2.md).

Dependencies: T015, T013. Requirements: ID-05, ID-07.

Deliverables: backend lifecycle services, frontend staff and account controls.

Work: Add scoped revoke/reactivate, whole-account suspension, secretary delegation, controlled bootstrap, and last-super-admin protection.

Acceptance: Suspension revokes sessions and grants immediately; reactivation restores only approved grants.

Verification: Test last-admin guard, delegation ceilings, session revocation, and disabled bootstrap.

## B05 Advisor assignments and revocation

### T017 Implement assignment and reassignment

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.2 completed: eligible/capacity selectors, required primary advisor on activation, immutable assignment history, optimistic revisions, capacity contention, reassignment queue, and immediate former-advisor denial. See [Release 0.2 evidence](RELEASE_0_2.md).

Dependencies: T015, T016. Requirements: ID-06.

Deliverables: backend assignments module, frontend roster/assignment controls.

Work: Enforce one active primary advisor, matching scope/capacity, effective history, and transactional relationship epochs.

Acceptance: Invalid assignments fail and historical chat participation does not preserve former-advisor access.

Verification: Test reassignment, concurrent assignment, wrong department, inactive advisor, and history visibility.

### T018 Cancel stale jobs caches and streams

- [ ] Status: Inprogress; assignee: Codex; owner perspective: Backend engineer.

Release 0.2 subset completed: transactional grant/relationship epochs, affected-advisor epoch changes, identity/scope-bound UI invalidation and invitation-delivery reauthorization. Release 0.4 adds current-authority generation/index jobs, output commits, citation reauthorization and advisor access-loss coverage. Future-resource streams and general notification cancellation remain open. See [Release 0.2 evidence](RELEASE_0_2.md).

Dependencies: T017. Requirements: ID-06, RG-08.

Deliverables: backend context epoch utilities, event access checks, frontend cache invalidation.

Work: Recheck identity/relationship epochs before job execution, output commit, stream events, and notification delivery; clear scope-bound browser caches.

Acceptance: Old advisors receive no new sensitive content after reassignment; stale generated answers are discarded.

Verification: Exercise reassignment while a synthetic generation job and notification are queued.

## B06 Student onboarding

### T019 Implement academic profile versions

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.3 completed for synthetic-local scope. See [acceptance evidence](RELEASE_0_3.md) and [intake contract](decisions/intake-contract.md).

Dependencies: T017, T003, T061. Requirements: ON-01–04.

Deliverables: backend profile schemas, migrations, and versioned profile API.

Work: Store program/track/catalog/term, course history, transfer facts, workload goals, provenance, verification, and disputes.

Acceptance: Corrections append a new version; missing completion facts are never interpreted as completed courses.

Verification: Test catalog validation, self-reported versus verified facts, conflicting updates, and profile ETags.

### T020 Build initial questions and profile review

- [x] Status: Completed; assignee: Codex; owner perspective: Frontend engineer.

Release 0.3 completed for synthetic-local scope. See [acceptance evidence](RELEASE_0_3.md) and [intake contract](decisions/intake-contract.md).

Dependencies: T019, T010. Requirements: ON-01–04.

Deliverables: frontend student onboarding and profile summary.

Work: Ask department-configured questions, save drafts, display provenance and missing facts, and require catalog confirmation before definitive recommendations.

Acceptance: A student can resume and correct onboarding; schema changes preserve historical versions.

Verification: Test incomplete/resumed onboarding, validation, correction, and keyboard operation.

### T021 Propagate material profile changes

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.3 completed for synthetic-local scope. See [acceptance evidence](RELEASE_0_3.md) and [intake contract](decisions/intake-contract.md).

Dependencies: T019, T018. Requirements: ON-04, RG-08, FO-05.

Deliverables: profile-change events and downstream invalidation interfaces.

Work: Increment profile/context version and emit change events for recommendations and pending-form review; define consumers without assuming forms exist yet.

Acceptance: Old recommendation contexts become stale and subscribers can distinguish material updates.

Verification: Test version invalidation and durable idempotent change-event emission.

## B07 Documents and extraction

### T022 Implement authorized uploads and pasted text

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.3 completed for synthetic-local scope. See [acceptance evidence](RELEASE_0_3.md) and [intake contract](decisions/intake-contract.md).

Dependencies: T012, T011. Requirements: KN-01–02.

Deliverables: backend source upload/text API and source-version migrations.

Work: Authorize scope and student relationship; validate file type/size; write private quarantine objects; turn text input into immutable source versions.

Acceptance: An advisor can upload for assigned students only and cannot choose institution-wide visibility.

Verification: Test scope forgery, metadata privacy, oversized/encrypted input, and sanitized filenames.

### T023 Implement isolated scanning and extraction

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Release 0.3 completed for synthetic-local scope. See [acceptance evidence](RELEASE_0_3.md) and [intake contract](decisions/intake-contract.md).

Dependencies: T022. Requirements: KN-01, KN-03.

Deliverables: backend ingestion worker, parser container, and extraction jobs.

Work: Scan files, extract PDF/DOCX/text, OCR when needed, preserve page/heading locators, and enforce resource/time/network limits.

Acceptance: Unsafe or unreadable inputs never publish; retries do not duplicate source versions.

Verification: Run parser fixture tests for malformed, scanned, supported, and malicious-looking documents.

### T024 Build source management and pipeline status

- [x] Status: Completed; assignee: Codex; owner perspective: Frontend engineer.

Release 0.3 completed for synthetic-local scope. See [acceptance evidence](RELEASE_0_3.md) and [intake contract](decisions/intake-contract.md).

Dependencies: T022, T023. Requirements: KN-01–03, PRD section 11.

Deliverables: frontend manager/admin/advisor upload and processing views.

Work: Show allowed scope, student association, progress, needs-review, failure, and retry states with metadata editing.

Acceptance: The UI cannot broaden source scope and does not expose inaccessible filenames.

Verification: Test each role's upload scope, processing errors, and accessible progress announcements.

## B08 Knowledge publication and tuning

### T025 Implement chunks and embedding versions

- [x] Status: Completed; assignee: Codex; owner perspective: Retrieval engineer.

Dependencies: T023, T003. Requirements: KN-03–04, RG-01.

Deliverables: backend chunker/embedding adapter and index migrations.

Work: Persist chunk locators, source hashes, extractor/chunker settings, embedding revision/dimension, and index release; use a separate embedding model.

Acceptance: A partially built release is not searchable; mismatched vector dimensions are rejected.

Verification: Test deterministic chunk metadata, retry deduplication, and parallel index rebuilds.

### T026 Implement publication withdrawal and citations

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Dependencies: T025, T024. Requirements: KN-04, KN-06–07.

Deliverables: backend release/publish/withdraw services and citation/download routes.

Work: Require reviewed metadata and clean indexing; switch active versions atomically; immediately exclude withdrawn versions; authorize exact-version citations.

Acceptance: Failed replacement retains prior release; withdrawn chunks cannot support new answers or bypass download policy.

Verification: Test publication races, cache invalidation, withdrawal, wrong-student citation, and signed-link expiry.

### T027 Implement rules and prompt release controls

- [x] Status: Completed; assignee: Codex; owner perspective: Retrieval engineer.

Dependencies: T026, T011. Requirements: KN-05, RG-03–04.

Deliverables: backend typed rules/prompt release services and frontend configuration views.

Work: Separate factual documents, typed academic rules, allowed department instructions, and global prompt releases; add approval/evaluation/rollback interfaces.

Acceptance: Manager text cannot alter authorization or signature controls; ambiguous rules require policy-owner review.

Verification: Test forbidden overrides, rule validation, release versioning, and rollback pointer behavior.

## B09 Retrieval and model responses

### T028 Implement filtered hybrid retrieval

- [x] Status: Completed; assignee: Codex; owner perspective: Retrieval engineer.

Dependencies: T025, T026, T019. Requirements: RG-01.

Deliverables: backend retrieval module and authorized evidence resolver.

Work: Filter institution/org/student/publication/catalog/effective dates before vector/full-text candidate selection; fuse and rerank only permitted chunks.

Acceptance: Private wrong-student evidence never reaches either reranker or chat model.

Verification: Measure Recall@10 on labeled fixtures and inspect candidates for cross-scope leakage.

### T029 Implement private vLLM client and mock adapter

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Dependencies: T005, T002. Requirements: RG-07–08, PRD section 14.

Deliverables: backend chat inference adapter and configuration validation.

Work: Use fixed internal endpoint/model alias, bounded timeouts/output tokens, redacted telemetry, tested chat formatting, and a deterministic dev mock.

Acceptance: Student input cannot select endpoints/tools; production rejects mock inference and missing auth.

Verification: Run adapter contract tests for auth, timeout, malformed model JSON, and production startup guards.

### T030 Implement grounded structured responses

- [x] Status: Completed; assignee: Codex; owner perspective: Retrieval engineer.

Dependencies: T028, T029, T027. Requirements: RG-02, RG-06–08.

Deliverables: backend context builder, answer validator, abstention and repair logic.

Work: Attach exact evidence IDs and assumptions; validate schema/support/constraints; permit one bounded repair then clarify or escalate.

Acceptance: Fabricated citations and unsupported definitive course claims never reach students.

Verification: Run answerable, unanswerable, conflict, injection, missing-fact, and invalid-citation cases.

## B10 Student chat

### T031 Implement versioned conversations and generation jobs

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Dependencies: T030, T018, T021. Requirements: RG-08–09.

Deliverables: backend conversation/message API and generation worker.

Work: Persist typed authors, student messages, idempotency, pending/completed/blocked/failed states, and context/evidence trace IDs; buffer output until validation.

Acceptance: Retry does not duplicate a question and stale contexts never commit an answer.

Verification: Test timeout/retry, duplicate request, source withdrawal during generation, and epoch changes.

### T032 Build cited chat and evidence drawer

- [x] Status: Completed; assignee: Codex; owner perspective: Frontend engineer.

Dependencies: T031, T020. Requirements: RG-02, RG-06, PRD section 11.

Deliverables: frontend chat workspace, citation viewer, progress and failure components.

Work: Distinguish student/advisor/assistant messages; show validated answers, assumptions, citations, clarify/abstain states, and a human-help action.

Acceptance: No unvalidated text is rendered and raw model/source HTML cannot execute.

Verification: Test safe Markdown/links, forbidden citations, keyboard flow, retry, and model downtime.

## B11 Advisor guidance

### T033 Implement guidance and private notes

- [x] Status: Completed; assignee: Codex; owner perspective: Backend engineer.

Dependencies: T031, T017. Requirements: RG-04–05.

Deliverables: backend guidance/note services and advisor draft endpoint.

Work: Add validity/supersession and explicit visibility types; guidance persistence may notify but must not enqueue generation; explicit AI drafts remain staff-only.

Acceptance: Advisor guidance creates zero assistant reply jobs; private notes stay outside all student-facing contexts.

Verification: Test wrong advisor, expiry, supersession, private marker non-disclosure, and explicit-draft visibility.

### T034 Prioritize guidance in subsequent questions

- [x] Status: Completed; assignee: Codex; owner perspective: Retrieval engineer.

Dependencies: T033, T030. Requirements: RG-04–05.

Deliverables: backend active-guidance context resolver and conflict handling.

Work: Load relevant active student-visible guidance on later student turns; apply planning preferences while preserving official constraints and verified exceptions.

Acceptance: Guidance affects relevant plans but cannot silently waive a prerequisite.

Verification: Run no-auto-reply, next-turn preference, expired instruction, and policy-conflict scenarios.

### T035 Build advisor conversation tools

- [x] Status: Completed; assignee: Codex; owner perspective: Frontend engineer.

Dependencies: T033, T034, T032. Requirements: RG-05, PRD section 11.

Deliverables: frontend advisor roster/chat, guidance composer, private notes, and draft preview.

Work: Provide clearly separated visible guidance/private note actions, source uploads, expiry/supersession controls, and manual draft publication flow.

Acceptance: Students see human authorship and never see private notes or unpublished drafts.

Verification: Test visibility boundaries, author labels, assignment revocation, and absence of automatic AI typing after guidance.

## B12 Human cases and notifications

### T036 Implement outbox publishing and delivery deduplication

- [ ] Status: Inprogress; assignee: Codex; owner perspective: Backend engineer.

Release 0.2 subset completed: business-transaction outbox metadata and restricted invitation.send SMTP consumer, reauthorization/cancellation, bounded retries and real Mailpit delivery tests. SMTP can repeat email after a crash; acceptance is single-use. General publishing, consumers, notifications and dead-letter UI remain open. See [Release 0.2 evidence](RELEASE_0_2.md).

Dependencies: T007, T002, T011. Requirements: HU-04.

Deliverables: backend outbox models, publisher, retry/dead-letter interfaces.

Work: Commit events with originating business transactions, publish asynchronously, deduplicate consumers, and reauthorize recipients.

Acceptance: A publishing crash or redelivery cannot duplicate the logical side effect.

Verification: Test crash between publish/ack, bounded retry, malformed event, and revoked recipient.

### T037 Implement advisor cases and routing

- [ ] Status: Inprogress; assignee: Codex; owner perspective: Backend engineer.

Dependencies: T031, T017, T036. Requirements: HU-01–03, HU-05.

Deliverables: backend case API/state machine and business-calendar settings.

Work: Create student-requested cases, route to current advisor or manager queue, track lifecycle and reopen history, and configure business-hour targets.

Acceptance: Missing advisors do not lose requests; model recovery does not close cases automatically.

Verification: Test duplicate requests, no advisor, reassignment, invalid transitions, and timezone deadlines.

Release 0.4 delivers durable cases/receipt/status and the current-authority queue. Notification, email and business-calendar/SLA portions remain pending.

### T038 Implement notifications email and case views

- [ ] Status: Inprogress; assignee: Codex; owner perspective: Frontend engineer.

Dependencies: T037, T036, T032. Requirements: HU-04–05, PRD section 11.

Deliverables: backend mail adapter plus frontend case/in-app notification queues.

Work: Show case status, staff replies, unread events, and authenticated links; email contains no transcript/grades/documents; use mock email in development.

Acceptance: Email failure preserves the case and an authoritative in-app notification.

Verification: Test mail failure/retry, exact recipient scope, sensitive-content exclusion, and case acknowledgment UI.

Release 0.4 delivers durable cases/receipt/status and the current-authority queue. Notification, email and business-calendar/SLA portions remain pending.

## B13 Plans and academic validation

### T039 Implement deterministic academic checks

- [ ] Status: todo; assignee: unassigned; owner perspective: Retrieval engineer.

Dependencies: T027, T019, T003. Requirements: RG-03–04.

Deliverables: backend prerequisite/credit/group/repeat-rule validator.

Work: Evaluate approved typed rules against versioned academic facts, with explicit unknown and conflict outcomes and verified exception references.

Acceptance: Missing data yields unknown rather than false eligibility; ordinary guidance cannot override rules.

Verification: Run labeled prerequisite, credit-limit, repeat, equivalency-unknown, and conflict fixtures.

### T040 Implement saved plan versions and comparison

- [ ] Status: todo; assignee: unassigned; owner perspective: Backend engineer.

Dependencies: T039, T034, T031. Requirements: RG-09.

Deliverables: backend plan API and frontend plan editor/comparison.

Work: Snapshot evidence/profile/guidance/constraints for each plan; distinguish draft recommendation from registration or approved form.

Acceptance: Editing creates a new plan version and preserves previous evidence; unresolved blocking issues remain visible.

Verification: Test compare/edit, stale profile, missing course offering, and source withdrawal.

## B14 Forms and artifacts

### T041 Implement versioned form templates and eligibility

- [ ] Status: todo; assignee: unassigned; owner perspective: Backend engineer.

Dependencies: T040, T017, T004. Requirements: FO-01–02.

Deliverables: backend template/form module and form-creation API.

Work: Define a synthetic local template, required fields, expected signers, and preconditions; use institution-approved templates for the real pilot.

Acceptance: No form starts with inactive membership, missing signer, or unresolved blocking conflict.

Verification: Test missing fields, wrong scope, ineligible signers, and template version changes.

### T042 Implement canonical revisions and durable PDF artifacts

- [ ] Status: todo; assignee: unassigned; owner perspective: Backend engineer.

Dependencies: T041, T026. Requirements: FO-02, FO-07.

Deliverables: backend canonical serializer, PDF artifact worker, and authorized artifact endpoint.

Work: Freeze complete content/signers/evidence; compute canonical and artifact checksums separately; gate signing until durable upload succeeds.

Acceptance: A signed revision cannot mutate; a failed artifact upload leaves signing unavailable.

Verification: Test stable canonical hashes, object-write retry, exact PDF content, and unauthorized download.

### T043 Build exact revision preview and consent UI

- [ ] Status: todo; assignee: unassigned; owner perspective: Frontend engineer.

Dependencies: T042, T006. Requirements: FO-02–03.

Deliverables: frontend form preview, initials/name, consent and signer timeline components.

Work: Display exact immutable revision, source references, intent text, current ETag, and signer order before accepting intent.

Acceptance: Students review the payload being signed and cannot bypass consent with a hidden UI control.

Verification: Test stale preview reset, keyboard signature flow, pending artifact, and server failure.

## B15 Signature workflow

### T044 Implement student signature transaction

- [ ] Status: todo; assignee: unassigned; owner perspective: Backend engineer.

Dependencies: T043, T036, T009. Requirements: FO-03–04, FO-06.

Deliverables: backend signing service and student submit action.

Work: Validate recent auth, own identity, intent, consent version, revision/ETag, state, and idempotency; atomically store signature/state/outbox.

Acceptance: One valid signature advances to awaiting_advisor; browser-supplied actor/time never becomes authoritative.

Verification: Test duplicate concurrent signs, wrong student, missing intent, stale revision, and old authentication.

### T045 Implement advisor and manager review signatures

- [ ] Status: todo; assignee: unassigned; owner perspective: Backend engineer.

Dependencies: T044, T035. Requirements: FO-04, FO-06–07.

Deliverables: backend reviewer actions and frontend advisor/manager review queues.

Work: Enforce current designated advisor then eligible manager, same revision, prior signatures, and scoped review/download.

Acceptance: A manager cannot sign before the advisor and high privilege cannot create proxy signatures.

Verification: Run three-party happy path, skipped step, wrong reviewer, duplicate race, and completed-form export.

### T046 Implement returns holds withdrawal and supersession

- [ ] Status: todo; assignee: unassigned; owner perspective: Backend engineer.

Dependencies: T045, T021, T018. Requirements: FO-05–07.

Deliverables: backend form transition handlers and frontend revision/history/hold states.

Work: Require reasons; create successor revisions for changes; restart all signatures; hold pending forms on policy/profile/eligibility change and revalidate signers.

Acceptance: Completed forms remain immutable; signer/content changes never reuse old signatures.

Verification: Test return/resubmit, reassignment, withdrawal, source/policy update, hold release, and stale reviewer browser.

## B16 Complete role workspaces and accessibility

### T047 Complete admin manager and secretary dashboards

- [ ] Status: todo; assignee: unassigned; owner perspective: Frontend engineer.

Dependencies: T015, T016, T013, T038, T045, T024, T061. Requirements: PRD sections 3, 11.

Deliverables: frontend role dashboards, scope switcher, history and review queues.

Work: Integrate staff approvals, assignments, source management, advisor history, cases, audit, and signing according to granted capabilities.

Acceptance: Secretary sees enrollment/assignment data only; switching scope invalidates cached private records.

Verification: Exercise complete role journeys, wrong-scope direct URLs, and scope-switch cache behavior.

### T048 Complete student and advisor workspace integration

- [ ] Status: todo; assignee: unassigned; owner perspective: Frontend engineer.

Dependencies: T035, T040, T046, T038. Requirements: PRD section 11.

Deliverables: frontend integrated student/advisor navigation and error states.

Work: Connect profile, chat, advisor help, plans, documents, form history, and notifications; include loading/empty/forbidden/offline/stale states.

Acceptance: All critical actions are reachable with clear authorship/status and server-confirmed outcomes.

Verification: Run invited and self-registered student journeys through completed forms using synthetic accounts.

### T049 Verify accessibility and responsive layouts

- [ ] Status: todo; assignee: unassigned; owner perspective: QA reviewer.

Dependencies: T047, T048. Requirements: PRD sections 11, 15.

Deliverables: frontend accessibility fixes and QA evidence.

Work: Check semantic controls, focus, contrast, status announcements, form intent, and 360/768/1280 px layouts using keyboard and screen-reader paths.

Acceptance: Critical workflows are operable without a mouse and have no unresolved critical automated findings.

Verification: Run actual automated checks plus manual keyboard/screen-reader sessions; record gaps.

## B17 Google Cloud infrastructure and private inference

### T050 Prepare environment inventory and IaC plan

- [ ] Status: todo; assignee: unassigned; owner perspective: Cloud engineer.

Dependencies: T005, T004. Requirements: PRD section 14, cloud guide sections 1–3.

Deliverables: infra Terraform modules, environment examples, provider lockfile, reviewed plan.

Work: Resolve intended project/region, supported versions, quota, billing inputs, model license, and GPU candidates; define separate dev/stage/prod state.

Acceptance: No ambiguous environment or secret is committed; unresolved GPU/model choices block allocation.

Verification: Run Terraform formatting/validation and review actual target-specific plan and cost inputs.

### T051 Provision private GKE data services and identities

- [ ] Status: todo; assignee: unassigned; owner perspective: Cloud engineer.

Dependencies: T050. Requirements: PRD sections 14, 16.

Deliverables: infra VPC/GKE/SQL/storage/PubSub/registry/secrets resources.

Work: Build private CPU/GPU pools, network enforcement, private SQL, buckets, topics, distinct workload identities, and least-privilege IAM.

Acceptance: Inference has no student database access and application workloads cannot administer infrastructure.

Verification: Verify resource IAM, SQL connectivity, bucket privacy, workload identity, and enforced network-policy tests in dev.

### T052 Deploy and benchmark private vLLM and embeddings

- [ ] Status: todo; assignee: unassigned; owner perspective: Cloud engineer.

Dependencies: T051, T029, T025. Requirements: PRD section 14, cloud guide sections 5–6.

Deliverables: rendered inference manifests, immutable release inventory, benchmark report.

Work: Pin image/weights/tokenizer/chat template; preload approved model cache; deploy authenticated private serving, separate embeddings, probes, service TLS, and egress allowances.

Acceptance: Only approved callers can reach inference; tested GPU profile handles documented context/concurrency without unhandled OOM.

Verification: Run native Kubernetes validation, probe/auth/blocked-caller tests, GPU memory/load benchmark, and no-prompt-log inspection.

### T053 Deploy frontend backend and workers in development

- [ ] Status: todo; assignee: unassigned; owner perspective: Cloud engineer.

Dependencies: T051, T052, T031, T036. Requirements: PRD section 14.

Deliverables: application Dockerfiles, CPU manifests, HTTPS routing, secret interfaces.

Work: Build immutable application images, route same-origin web/API over TLS, connect private services, and run controlled migrations with separate identity.

Acceptance: Browsers cannot reach model/database directly and production startup excludes mock or insecure settings.

Verification: Run synthetic API/chat/session smoke tests, private connectivity checks, and failed-secret startup tests.

## B18 Evaluation delivery and operations

### T054 Build frozen advising evaluation and release gate

- [ ] Status: todo; assignee: unassigned; owner perspective: Retrieval engineer.

Dependencies: T034, T039, T003, T030. Requirements: PRD section 15, RAG_DESIGN.md.

Deliverables: evals labeled dataset, evaluation runner, scored reports.

Work: Expand 24 seed scenarios into at least 200 reviewed questions; separate retrieval/grounding/abstention metrics and program/catalog coverage; block regressing releases.

Acceptance: Threshold decisions reference actual measurements and human-reviewed labels, not model self-confidence.

Verification: Run evaluation against pinned prompt/source/model/index releases and publish failure cases with provenance.

### T055 Implement staging CI CD and rollback promotion

- [ ] Status: todo; assignee: unassigned; owner perspective: Cloud engineer.

Dependencies: T053, T046. Requirements: PRD sections 15, 17, cloud guide section 7.

Deliverables: CI build/scan/deploy workflows and migration rollout runbook.

Work: Use short-lived CI federation, build-once digest promotion, contract-compatible migrations/events, staging checks, and explicit production environment targeting.

Acceptance: A failed rollout can restore compatible application/model/knowledge releases without editing signed forms.

Verification: Exercise staging rollout, failed health gate, image rollback, and queued-event compatibility.

### T056 Implement metrics alerts budgets and retention jobs

- [ ] Status: todo; assignee: unassigned; owner perspective: Cloud engineer.

Dependencies: T053, T037, T046, T004. Requirements: PRD sections 15–16, cloud guide section 8.

Deliverables: operational dashboards, redaction policy, alerting, retention/deletion workers.

Work: Measure queue/errors/latency/GPU/cost/cases/signature conflicts; redact content; configure budgets/quotas and retention/legal-hold-aware cleanup.

Acceptance: Operators can detect failed delivery, stale indexing, and model saturation; cleanup respects holds and backups policy.

Verification: Trigger synthetic alerts; inspect log redaction; test deletion of database/chunks/cache/objects and legal-hold exclusion.

### T057 Run full security state and load acceptance

- [ ] Status: todo; assignee: unassigned; owner perspective: QA reviewer.

Dependencies: T049, T055, T056, T054, T038. Requirements: PRD sections 15, 17.

Deliverables: recorded E2E/security/load results and release blockers.

Work: Exercise every seed category, all roles, cross-scope queries/jobs/caches/exports, signature races, model downtime, parser failures, and the recorded pilot load.

Acceptance: Zero known unauthorized disclosures, auto-reply violations, skipped/stale signatures, or unreviewed blocking regressions remain.

Verification: Run actual database/integration/E2E/concurrency/load suites and compare results with proposed PRD targets.

## B19 Recovery and pilot readiness

### T058 Rehearse backup restore and release rollback

- [ ] Status: todo; assignee: unassigned; owner perspective: Cloud engineer.

Dependencies: T057, T056. Requirements: PRD section 15, cloud guide section 9.

Deliverables: isolated restore evidence, recovery runbook, measured RPO/RTO.

Work: Restore database and objects consistently; rebuild indexes; reconcile deletions/holds; resume outbox without duplicate effects; restore prior model cache and release pointers.

Acceptance: Restored data preserves ACLs, form evidence, signature history, and deduplication; actual recovery time is recorded.

Verification: Run a full isolated restoration plus permission/form/outbox checks and rollback rehearsal.

### T059 Close institutional decisions and release evidence

- [ ] Status: todo; assignee: unassigned; owner perspective: Product architect.

Dependencies: T058, T004, T057. Requirements: PRD sections 2, 16–18.

Deliverables: pilot decision record, operating ownership, limitations and approved scope.

Work: Resolve source ownership, identity, signature acceptance, access/retention terms, support ownership, availability, budget, and model license before real data.

Acceptance: Every unresolved blocker has been resolved or the pilot remains synthetic-only; no legal/performance claims exceed evidence.

Verification: Review the decision register and all acceptance/recovery reports with the responsible institutional owners.

### T060 Complete operator and end-user handoff

- [ ] Status: todo; assignee: unassigned; owner perspective: QA reviewer.

Dependencies: T059. Requirements: PRD sections 11, 17.

Deliverables: README, operating guides, staff/student quick starts, task completion evidence.

Work: Document deployment, support queues, publication, guidance, signing, incident response, model/knowledge rollback, and development shutdown with GPU cost verification.

Acceptance: A new operator can follow the documented synthetic walkthrough and identify unimplemented or restricted features.

Verification: Reproduce setup and three-role advising/signature workflow from docs; verify links and current commands.

## Completion handoff template

```text
Task ID:
Assignee and branch or PR:
Requirements addressed:
Deliverables and interface changes:
Migrations and event compatibility:
Checks actually executed and results:
Acceptance evidence:
Untested areas and blocking decisions:
Next ready task IDs:
Reviewer and completion date:
```

Keep test outputs in the agreed project/CI report location and reference them here or in the PR. Avoid embedding student records, tokens, private source content, or signed artifacts in handoff text. If an institutional decision changes the product behavior, update the PRD and this task list together rather than implementing a silent exception.

Release 0.4 synthetic-local acceptance for T025–T035 is recorded in [the release evidence](RELEASE_0_4.md). T037–T038 are partial; notification/email/business-calendar portions remain Inprogress.
