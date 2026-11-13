# Implementation backlog

Use these slices in dependency order. They define implementation work, not completed features. Each slice must update OpenAPI, relevant UI states, migrations, audit events, and tests where applicable. Estimates require a staffed team and institutional decisions.

| ID | Slice | Depends on | Acceptance evidence | Status |
| --- | --- | --- | --- | --- |
| B01 | Scaffold Next.js/TypeScript, FastAPI, Postgres/pgvector, migrations, test containers, pinned lockfiles and CI | None | Local synthetic app starts; lint/type/test scripts are real; health endpoints work | Completed (Release 0.1) |
| B02 | Institution/org units, users, identity binding, sessions, CSRF, staff MFA hooks | B01 | Verified identity and secure session tests; mock mode rejected in prod | Completed for synthetic-local scope (Release 0.1); organization administration T061 completed before 0.3 |
| B03 | Role grants and policy service, query scopes, RLS, audit | B02 | Role/scope/relationship matrix passes, including pooled connections | Completed for current resource surfaces (Release 0.2); future resources extend policies |
| B04 | Invitations, requests, approval queues, secretary delegation, membership revocation | B03 | No self-approval; email activation and duplicate approval tests | Completed for synthetic-local scope (Release 0.2) |
| B05 | Advisor assignment and transactional epochs | B04 | Former advisor denied on API, queued job, stream, and citation route | Inprogress — assignments and epochs complete (Release 0.2); current intake/generation jobs and citations covered through Release 0.4; future resources/streams pending |
| B06 | Versioned student onboarding and academic facts | B05 | Catalog validation, provenance, correction, and incomplete profile journeys | Completed for synthetic-local scope (Release 0.3) |
| B07 | Private upload/pasted text, quarantine and isolated extraction | B03 | Unsupported/malicious files fail; job retries idempotent | Completed for synthetic-local scope (Release 0.3) |
| B08 | Metadata review, chunking, embeddings, release publication and withdrawal | B07 | Atomic version switch; private/student/catalog filters; withdrawal gate | Completed for synthetic-local scope (Release 0.4) |
| B09 | Hybrid retrieval, evidence routes, model adapter and structured validation | B06, B08 | Labeled retrieval results; no fabricated evidence IDs; no cross-scope candidates | Completed for synthetic-local scope (Release 0.4) |
| B10 | Chat UI/API, bounded jobs, context versions and stale cancellation | B09 | Complete validated outputs; timeout, retry, and permission change journeys | Completed for synthetic-local scope (Release 0.4) |
| B11 | Advisor guidance, private notes and explicit draft actions | B10 | Guidance produces zero auto-replies; next student turn honors applicable guidance | Completed for synthetic-local scope (Release 0.4) |
| B12 | Cases, outbox, in-app notifications and email adapter | B05, B10 | Unassigned fallback, delivery retries, deduplication, revoked-recipient exclusion | Inprogress — invitation delivery complete (Release 0.2), durable case/queue subset implemented in Release 0.4; notification/email/business-calendar portions pending |
| B13 | Versioned saved plans and deterministic academic checks | B09, B11 | Prerequisite/missing fact/conflict cases reviewed against synthetic rules | |
| B14 | Form templates, revisions, canonical hashes, artifact generation | B13 | Stable exact previews, pending artifact gate, authorized download | |
| B15 | Student/advisor/manager signatures, returns, holds and concurrency | B12, B14 | No skipped steps, stale signature, duplicate race, or mutation of signed revision | |
| B16 | Role dashboards, accessibility, responsive workflows | B04–B15 incrementally | Keyboard and screen-reader critical paths plus 360/768/1280 px checks | |
| B17 | Infrastructure as code, GKE CPU/GPU pools, WIF, private SQL/storage/model traffic | B01, cloud inputs | Plan reviewed; scoped identity and network reachability tests in dev | |
| B18 | Staging CI/CD, model/retrieval eval gates, observability and load tests | B09, B15, B17 | Frozen metrics, synthetic full journey, queue saturation and downtime results | |
| B19 | Restore/rollback rehearsal and institutional pilot review | B18 | Restore evidence and resolved privacy/signature/retention decisions | |
