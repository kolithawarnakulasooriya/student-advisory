# Release Plan

This release plan is based on the backlog in [docs/TASKS.md](TASKS.md). It is organized so the product team can test working slices of the application at each stage instead of waiting for the full platform.

## Release 0.1 — Foundation and safe auth

Goal: Get a working local app with identity, roles, and secure session boundaries.

Status: Completed for the agreed synthetic-local scope on November 11, 2026. See [verification and limitations](RELEASE_0_1.md). Includes the foundation subset of T011/T012; their remaining authorization work stays in Release 0.2. Live institutional identity integration remains a pilot dependency.

### Backend
- T005: FastAPI scaffold with health checks, config validation, and structured errors
- T007: disposable PostgreSQL + pgvector, migration baseline, synthetic seed data
- T008: institution and organization model
- T009: verified identity, session handling, logout, revocation, MFA hooks

### Frontend
- T006: Next.js app shell with loading/error states
- T010: sign-in, verification, registration, session expiry, sign-out UI

### Testable updates
- App boots locally with dev config
- User can sign in and sign out
- Expired session shows clear recovery flow
- Wrong-scope access is blocked server-side

### Exit criteria
- Local backend and frontend both run
- Synthetic users can log in and view a role-based landing state
- No secret/config leak in logs or UI

## Release 0.2 — Role permissions and staff workflows

Goal: Make the app usable for staff operations and access boundaries.

Status: Completed for the agreed synthetic-local scope on November 11, 2026. See [verification and limitations](RELEASE_0_2.md). T011–T017 cover current resources; T018 includes epochs/cache invalidation and T036 includes local invitation delivery. Their later-release work remains open.

### Backend
- T011: capability checks and role ceilings
- T012: scoped queries and row policies
- T013: audit history and oversight
- T014: email invitations
- T015: request/approval workflows
- T016: suspension and delegated staff management
- T017: advisor assignment/reassignment

### Frontend
- Staff dashboards and assignment views
- Request approval UI
- Suspended account and delegation states

### Testable updates
- Manager, secretary, advisor, and student receive only valid UI actions
- Advisor assignments can be changed safely
- Audit trail shows authorization events without exposing raw prompt/transcript content

### Exit criteria
- A user with the wrong scope cannot access records
- A manager can approve/reject requests
- A suspended user loses access immediately

## Organization administration prerequisite — T061

Completed for synthetic-local scope after Release 0.2 and before Release 0.3. Includes college/department creation and editing, explicit metadata-administration delegation, request-enrollment controls, safe archive/restore, separate manager appointment, forced RLS and audited UI/API workflows. See [T061 implementation and acceptance](T061_HANDOFF.md).

## Release 0.3 — Student onboarding and document intake

Completed for synthetic-local scope. See [Release 0.3 evidence](RELEASE_0_3.md) and [intake decisions](decisions/intake-contract.md). T021 delivers the context/event interface; recommendation and form consumers remain future work.

Goal: Deliver a visible student journey with profile capture and uploaded documents.

### Backend
- T019: academic profile versions
- T020: profile review and onboarding state
- T021: profile change invalidation and downstream events
- T022: authorized upload and pasted-text sources
- T023: isolated scanning and extraction jobs

### Frontend
- T020: onboarding form and profile review
- T024: upload, pipeline status, retry, and source management views

### Testable updates
- Student can start onboarding, save drafts, and resume
- Uploads are scoped correctly
- Source processing status is visible and actionable
- Profile changes invalidate stale recommendations

### Exit criteria
- Student can complete profile setup with synthetic data
- Processing errors show retry/resolution paths
- No file or document is visible outside the assigned scope

## Release 0.4 — Retrieval, cited answers, and advisor guidance

Goal: Enable the core advising experience with grounded answers and human guidance.

Status: Completed for the agreed synthetic-local scope on November 12, 2026: T025–T035, including T027. Durable case/queue portions of T037–T038 are included; notification/email/business-calendar portions remain Inprogress. See [verification and limitations](RELEASE_0_4.md).

### Backend
- T025: chunking and embedding versions
- T026: publication withdrawal and citation support
- T027: typed rules, bounded department settings and evaluated prompt release controls
- T028–T030: retrieval and grounded structured responses
- T031: conversation + generation job model
- T033: guidance and private notes
- T034: guidance prioritization in later questions
- T037–T038 subset: durable human-help cases, receipts/status and current-authority queues; email/notifications/business calendars remain pending

### Frontend
- T032: chat UI with citations and evidence drawer
- T035: advisor guidance composer and notes separation

### Testable updates
- User can ask a question and receive a cited answer
- Guidance from advisors affects later student questions without leaking private notes
- Private notes remain staff-only

### Exit criteria
- Grounded answers include valid sources
- Advising guidance is visible only to the intended audience
- Unvalidated model output is never rendered as final answer

## Release 0.5 — Plans, forms, and signatures

Goal: Move from chat and advice to formal academic planning and signed forms.

### Backend
- T039: deterministic academic validation
- T040: saved plan versions and comparison
- T041: versioned form templates and eligibility
- T042: canonical revision and durable PDF artifact flow
- T044: student signature transaction
- T045: advisor and manager review signatures
- T046: returns, holds, withdrawal, and supersession

### Frontend
- T043: exact revision preview and consent UI
- Form review, signature flow, revision history

### Testable updates
- Student can review exact form content before signing
- Advisor and manager approvals follow valid order
- Stale versions and duplicate signatures are rejected

### Exit criteria
- A signed revision cannot be modified
- Hold/return transitions are visible and auditable
- Browser-provided actor/time is never treated as authoritative

## Release 0.6 — Role workspaces, accessibility, and deployment smoke tests

Goal: Complete the usable product and confirm operational readiness.

### Backend
- T036–T038: outbox, case routing, notification delivery
- T050–T053: cloud environment and private inference
- T054–T060: evaluation gates, CI/CD, rollback, pilot readiness

### Frontend
- T047–T049: dashboards, integrated role workspaces, accessibility validation

### Testable updates
- Dashboard and role screens are complete
- Accessibility checks pass for keyboard and responsive layouts
- Dev deployment works with mock/synthetic data

### Exit criteria
- Core user journeys are available across student, advisor, manager, and secretary
- Critical flows are accessible without a mouse
- Release rollback and recovery steps are documented

## Suggested delivery cadence

- Sprint 1: Release 0.1 + 0.2
- Sprint 2: Release 0.3 + 0.4
- Sprint 3: Release 0.5
- Sprint 4: Release 0.6

## Suggested QA test windows by phase

- Release 0.1 QA:
  - Sign up, sign in, logout, expired session
- Release 0.2 QA:
  - Role matrix, denial checks, assignment changes
- Release 0.3 QA:
  - Onboarding resume flow, upload, extraction, status
- Release 0.4 QA:
  - Cited chat, guidance visibility, no private-note leak
- Release 0.5 QA:
  - Form preview, signatures, reviewer order, hold/return
- Release 0.6 QA:
  - Dashboard usability, accessibility, deployment smoke test

## Recommended product checkpoint

The best demo-ready milestone is Release 0.4:
- working auth
- role-based access
- onboarding
- document pipeline
- cited chat
- advisor guidance

This gives users a meaningful end-to-end experience without waiting for the full forms/signature stack.
