# Release QA Checklist

Use this checklist to verify each release in [docs/RELEASE_PLAN.md](docs/RELEASE_PLAN.md). Check an item only after performing the test and recording evidence. A release status of completed does not by itself mean these QA checks have been run.

## QA run details

- Release/version:
- Build or commit:
- Environment:
- Tester and date:
- Test data: synthetic only
- Evidence link or location:
- Open issues / limitations:

## Shared pre-release checks

- [x] Confirm the release scope and acceptance criteria in [docs/RELEASE_PLAN.md](docs/RELEASE_PLAN.md).
- [x] Use synthetic accounts, academic records, documents, and conversations only.
- [x] Record the tested build, environment, test results, and reproducible defects.
- [x] Verify errors are visible and actionable; confirm no secrets or sensitive student data appear in UI, logs, emails, or test artifacts.
- [x] Confirm results distinguish local/mock checks from staging or production evidence.

## Release 0.1 — Foundation and safe auth

### Backend

- [x] Start the backend with synthetic local configuration; confirm required missing configuration fails explicitly.
- [x] Check health endpoints and structured error responses.
- [x] Create/reset the disposable database, run migrations, and load synthetic seed data.
- [x] Verify institution/organization relationships reject invalid cross-institution parents and cycles.
- [x] Verify verified identity/session behavior, logout, session revocation, and configured session protections.
- [x] Attempt an unauthorized or wrong-scope request directly against the API; confirm server-side denial.

### UI

- [x] Start the frontend and verify loading, connection failure, and recovery states.
- [x] Exercise registration/verification and sign-in with synthetic identities.
- [x] Verify signed-in landing state reflects the user's role.
- [x] Expire a session and confirm the UI presents a clear recovery action.
- [x] Sign out and confirm protected views are no longer available.
- [x] Inspect browser storage and confirm session tokens are not stored in localStorage.

### Release exit

- [x] Frontend and backend run locally together.
- [x] Synthetic user can complete the supported sign-in flow and reach the appropriate landing state.
- [x] No secrets or private records are exposed by tested UI or logs.
- [x] Review [docs/RELEASE_0_1.md](docs/RELEASE_0_1.md) for the agreed synthetic-local scope and remaining pilot limitations.

## Release 0.2 — Role permissions and staff workflows

### Backend

- [x] Run positive and negative authorization cases for student, advisor, secretary, manager, and administrator capabilities.
- [x] Attempt wrong-institution, wrong-department, unassigned-advisor, pending-user, and revoked-user requests directly through the API; confirm denial.
- [ ] Verify scoped queries fail closed when scope context is missing and do not leak scope through connection reuse.
- [ ] Exercise invitation acceptance, expiry, reuse, and email mismatch cases.
- [ ] Exercise request approval and rejection, including duplicate decisions, wrong-scope decisions, and self-approval attempts.
- [ ] Suspend an account and confirm active sessions/grants stop working; verify reactivation restores only approved grants.
- [ ] Assign and reassign an advisor; verify the former advisor cannot access current student records.
- [ ] Review audit/history results for correct access checks and absence of raw prompts or transcripts.

### UI

- [x] Verify each role sees only the navigation and actions allowed for its capabilities.
- [x] Submit and review a staff/student request; confirm status and decision are visible to the right users.
- [ ] Assign and reassign an advisor; confirm the displayed current assignment updates.
- [ ] Verify suspended-account and delegated-staff states and error messages.
- [ ] Try a wrong-scope direct URL and a scope switch; confirm access is denied and private cached data is cleared.

### Release exit

- [x] Wrong-scope users cannot read or change protected records through either UI or API.
- [x] Authorized manager can approve/reject requests; unauthorized/self-approval attempts fail.
- [ ] Suspension takes effect immediately in tested sessions.
- [ ] Review [docs/RELEASE_0_2.md](docs/RELEASE_0_2.md) for the agreed synthetic-local scope and remaining work.

## Release 0.3 — Student onboarding and document intake

### Backend

- [x] Create and update a synthetic academic profile; confirm corrections create versions rather than overwriting history.
- [x] Verify incomplete or self-reported facts are not treated as verified course completion.
- [x] Change a material profile fact and confirm the profile/context version advances and downstream change events are emitted idempotently.
- [x] Upload supported synthetic documents and pasted text within authorized scope.
- [x] Attempt scope forgery, oversized/encrypted inputs, and unsafe or unreadable files; confirm they are rejected or isolated from publication.
- [x] Verify extraction preserves expected page/heading locators and processing failures do not duplicate source versions on retry.

### UI

- [x] Begin onboarding, save a draft, leave, and resume it.
- [x] Correct a profile answer and confirm provenance, verification, missing facts, and catalog selection are clear.
- [x] Upload a document as each supported role; confirm the UI cannot broaden its visibility or association.
- [x] Follow processing progress, needs-review, failure, and retry states, including accessible progress announcements.
- [x] Confirm inaccessible source filenames and metadata are not revealed.

### Release exit

- [x] Synthetic student can complete, resume, and correct onboarding.
- [x] Authorized upload and extraction status work end-to-end; failures have a safe resolution path.
- [x] Cross-scope users cannot view or download source content.
- [x] Material profile edits invalidate stale recommendation context.

## Release 0.4 — Retrieval, cited answers, and advisor guidance

### Backend

- [ ] Build or publish a complete synthetic knowledge release; confirm partial indexing is not searchable.
- [ ] Verify retrieval filters by institution, scope, source applicability, and publication state before candidate selection.
- [ ] Withdraw a source and confirm it is excluded from new retrieval and citations.
- [ ] Submit answerable, ambiguous, unsupported, and conflicting synthetic questions; verify grounded answers, clarification, abstention, or escalation as appropriate.
- [ ] Verify every returned citation resolves to an authorized, published, applicable source and exact source location.
- [ ] Post advisor-visible guidance and confirm it does not enqueue an automatic assistant response.
- [ ] Verify active student-visible guidance affects a later relevant student turn without overriding official requirements.
- [ ] Verify expired/superseded guidance is not applied and staff-only notes never enter student-facing model context.
- [ ] Retry generation and simulate stale profile/relationship/source context; confirm duplicate messages and stale answers are not committed.

### UI

- [ ] Ask synthetic student questions and inspect answer, citations, evidence drawer, assumptions, and help/abstention states.
- [ ] Confirm unvalidated model output and unsafe source markup are not rendered.
- [ ] Test safe links/Markdown, keyboard navigation, loading, retry, and model-unavailable states.
- [ ] As an advisor, post student-visible guidance and a private note; verify labels and visibility are distinct.
- [ ] Confirm student sees human authorship and relevant guidance only, never private notes or unpublished drafts.
- [ ] Revoke/reassign an advisor during a test and confirm the old advisor cannot continue accessing the conversation.

### Release exit

- [ ] Supported institutional claims are grounded in valid citations; unsupported claims abstain or escalate.
- [ ] Retrieval and evidence views respect authorization and publication boundaries.
- [ ] Advisor posts do not cause automatic AI typing or replies.
- [ ] Private notes and unvalidated output are not exposed to students.

## Release 0.5 — Plans, forms, and signatures

### Backend

- [ ] Test prerequisite, credit, repeat, equivalency, missing-data, and conflicting-rule fixtures; unknown facts remain unknown.
- [ ] Create and edit a plan; verify each edit creates a version with profile, evidence, guidance, and constraint snapshots.
- [ ] Confirm stale profiles, withdrawn sources, or unavailable course offerings are visible as blocking/stale conditions.
- [ ] Attempt form creation with missing fields, inactive membership, missing signer, or unresolved blocking conflicts; confirm it is rejected.
- [ ] Verify canonical form content and durable artifact checksums; confirm failed artifact persistence blocks signing.
- [ ] Sign a form as the correct student and verify duplicate, concurrent, wrong-student, stale-revision, and insufficient-auth attempts fail safely.
- [ ] Attempt advisor and manager signatures out of order, by wrong reviewers, or as proxy signatures; confirm rejection.
- [ ] Exercise return, resubmission, hold, withdrawal, and supersession; verify changed content/signers create a new revision and restart required signatures.
- [ ] Confirm completed revisions and signatures remain immutable and authorized downloads are enforced.

### UI

- [ ] Compare and edit plans; verify prior versions and unresolved issues remain visible.
- [ ] Preview the exact immutable form revision, evidence, signer order, and consent/intent text before signing.
- [ ] Change the revision or ETag while preview is open; confirm stale preview is reset and cannot be signed.
- [ ] Complete the student, advisor, then manager flow; verify each actor sees only their current action.
- [ ] Test pending artifact, hold, return/revise, withdrawn, and superseded form states.
- [ ] Complete the critical form path using keyboard navigation and verify confirmation is clear.

### Release exit

- [ ] No signer can sign a different or mutated revision than the one reviewed.
- [ ] Signer order, identity, authorization, consent, recent-auth, and idempotency are enforced server-side.
- [ ] Stale revisions and duplicate/concurrent signatures do not create extra signatures.
- [ ] Completed forms remain immutable; holds and returns are visible and auditable.

## Release 0.6 — Role workspaces, accessibility, and deployment smoke tests

### Backend and operations

- [ ] Create a case and verify routing to the current advisor or manager queue, including the no-advisor path.
- [ ] Redeliver outbox events and simulate publisher/consumer failure; confirm logical side effects are not duplicated.
- [ ] Revoke or reassign a recipient before delivery; confirm delivery reauthorizes and does not expose protected content.
- [ ] Simulate email failure; confirm the case remains authoritative and in-app notification is available.
- [ ] Verify email contains no transcript, grades, or document content.
- [ ] For development deployment, verify browser access is limited to the intended web/API routes and cannot directly access model/database services.
- [ ] Verify startup fails safely for missing secrets or insecure/mock production settings.
- [ ] Run documented evaluation and release gates against pinned synthetic fixtures; record actual results and do not infer production performance from mocks.
- [ ] Exercise documented rollback and recovery procedures in an approved non-production environment.

### UI and accessibility

- [ ] Complete student, advisor, manager, and secretary journeys; verify scope switch invalidates private cached records.
- [ ] Verify loading, empty, forbidden, offline, stale, and error states across integrated workspaces.
- [ ] Test critical journeys using keyboard only; confirm focus visibility, semantic controls, and status announcements.
- [ ] Run automated accessibility checks and record unresolved findings.
- [ ] Test responsive layouts at 360 px, 768 px, and 1280 px widths.
- [ ] Perform and record manual screen-reader checks for critical workflows.

### Release exit

- [ ] Core role journeys pass with synthetic accounts and no cross-scope access.
- [ ] Critical workflows are usable without a mouse and responsive at the specified widths.
- [ ] Development deployment smoke tests pass; inference and data services remain private.
- [ ] Rollback/recovery and end-user/operator handoff are documented and exercised where safe.
- [ ] Record remaining institutional, privacy, identity, model-license, budget, evaluation, and recovery gates; do not treat development acceptance as production-pilot approval.

## Defect and sign-off record

- [ ] All release-blocking defects are fixed and retested, or the release is explicitly blocked with an owner and rationale.
- [ ] Results, commands, environment, synthetic fixtures, and evidence are attached to the release handoff.
- [ ] Product/QA sign-off is recorded before promoting the release.

Sign-off:

- QA:
- Product:
- Date:
- Decision: pending / approved / blocked
