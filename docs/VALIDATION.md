# Validation record

Updated November 11, 2026 for Release 0.3, preserving Release 0.2 and T061 organization-administration evidence. The original November 5 specification-package validation preceded application implementation; the current results below supersede its application-not-built limitation.

## Checks performed

Current local checks passed: 107 backend tests against real disposable PostgreSQL/pgvector, 19 frontend component tests, 29 Chromium end-to-end journeys, backend/frontend lint and type checks, locked dependency installs, fresh migrations and schema-drift checks, generated OpenAPI/client drift checks, and an optimized frontend build. The npm audit reports zero vulnerabilities; pip-audit reports no known vulnerabilities in the exported pinned Python dependency graph. A scan found no generated local signing key in source or built browser assets. Git whitespace checks passed.

The package validator passed 262 checks covering required assets, five workflow frontmatters, source Markdown links/fences, 24 synthetic behavioral seed cases, infrastructure template properties, and six rule examples. It excludes dependency/build/cache directories. This count is package integrity evidence, not application security or model evaluation evidence.

Detailed commands, scenarios, migration effects, and limitations are recorded in the [Release 0.2 handoff](RELEASE_0_2.md) and [T061 handoff](T061_HANDOFF.md). Setup is reproducible from README using the committed lockfiles and disposable Compose service.

## Limits

No live institutional identity, real MFA/external email, real student records, cloud provisioning, model inference, academic benchmark, signature workflow, load/recovery rehearsal, or institutional/legal review was performed. Local Mailpit delivery and restricted invitation worker access were tested; future-resource authorization and other worker access remain later tasks. GitHub Actions is defined but has not executed on GitHub in this session.

Browser evidence covers Chromium keyboard/recovery flows and 360/768/1280 px layouts. Full screen-reader/WCAG assessment and other browser engines are outstanding. The backend test client and pinned ESLint major emit deprecation notices; the locked checks pass.

The Kubernetes templates retain unresolved environment placeholders. The package's native Codex rule engine and Kubernetes server-side validation were not exercised. Synthetic eval seeds are behavioral inputs, not academic ground truth or measured model results. No claim of deployment, GPU fit, legal sufficiency, production security certification, or production performance is made.


## Release 0.3 acceptance

The implementation run passed backend lint, strict typing, additive migrations and Alembic drift checks, OpenAPI/Postman reproducibility, frontend lint/type/client checks, 19 component tests, production build, and all 35 Playwright journeys. The six intake journeys were rerun successfully after the final document display/filter changes. Backend coverage includes profile concurrency, current authorization, explicit capabilities, immutable history, source scope, worker leases/revocation/timeouts, safe paths, and subject-specific audit.

A fresh allowlisted advisory_test database migrated successfully and passed 131 tests with real scanner/OCR enabled at that stage. The final ordinary backend suite passed 134 tests, with the three real-container tests intentionally skipped there. Later hardening also passed the 27-test intake suite. Real parser tests separately exercised PDF, DOCX, Markdown, text, scanned/encrypted/malformed files, harmless EICAR rejection, and DOCX expansion limits. Ordinary pytest explicitly skips the three real-container tests unless RUN_PARSER_TESTS=1; CI enables them. The final package integrity check passed 285 checks. See [Release 0.3 evidence](RELEASE_0_3.md) for limitations.
