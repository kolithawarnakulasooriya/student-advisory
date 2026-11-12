# Release 0.3 — Student onboarding and document intake

## Delivered requirements

| Tasks | Requirements | Behavior |
| --- | --- | --- |
| T019–T020 | ON-01–04 | Student membership-bound immutable profile revisions, resumable drafts, configured questions/programs/tracks/catalogs/terms, provenance, explicit review/catalog confirmation, schema adoption and advisor confirmations/disputes |
| T021 | ON-04, RG-08, FO-05 interface | Transactional metadata-only profile.changed events, profile/relationship context tokens and stale-context comparison; future recommendation/form consumer obligations are documented |
| T022 | KN-01–02 | Authorized private upload/pasted text, immutable source scope/versions, bounded inputs, metadata revisions, history, downloads and archived state |
| T023 | KN-01, KN-03 | Real ClamAV scan, PDF/DOCX/text/Markdown extraction, English OCR, preserved locators, container isolation/resource limits, leases, current-authority checks, retry/cancellation and immutable artifacts |
| T024 | KN-01–03, PRD 11 | Student read-only evidence, staff source management, progress/errors/retry/replacement, manager schema editing, profile history and responsive keyboard-accessible controls |

## Implementation areas

- Backend: profiles.py, sources.py, intake_models.py, intake_schemas.py, private_storage.py, ingest_worker.py and upload_limit.py; additive migrations 0012–0015; extended capability projection, outbox aggregate IDs, configuration and synthetic seeds.
- Frontend: intake/profile/schema/source workspaces, generated API client types, explicit source/schema administration capabilities, and isolated-port browser configuration.
- Tooling: parser Dockerfile and extractor, separate scanner updater, optional Compose build service, CI real-container gate, OpenAPI/Postman regeneration, and database/parser/browser tests.
- Existing Release 0.2/T061 changes and records were retained. No cloud resources, real identity integration, embeddings, publication, recommendations or forms were added.

## Validation

Verification uses synthetic fixtures only. The implementation run exercised real PostgreSQL with forced RLS and non-owner application/worker roles, plus real Docker scanner/extraction/OCR tests. Backend migration/type/lint checks, generated contracts, frontend component checks/build, browser workflows, Postman reproducibility and package integrity checks are part of release acceptance. Observed passing checks:

- Backend Ruff, strict mypy (28 application modules), Alembic upgrade/drift check, and generated OpenAPI check.
- Final ordinary backend suite: 134 passed, 3 intentionally skipped real-container tests. The intake regression suite passed all 27 tests. A fresh disposable-database run also passed 131 tests with real scanner/OCR enabled before the final hardening additions.
- Real format/scanner/OCR integration: two tests passed in the clean run; the additional real DOCX expansion-limit test also passed. The ordinary suite intentionally skips these three external-tool tests, while CI runs them explicitly.
- Frontend lint/type/client checks, 19 component tests, production build, and all 35 browser journeys passed. The six intake journeys passed again after the final display/filter updates.
- Postman assets matched OpenAPI; package integrity passed 285 checks; tracked diff whitespace checks passed.

Earlier failed runs were corrected rather than treated as passing evidence.

Meaningful scenarios include stale/concurrent profile updates; schema adoption and invalid retained catalogs; self-reported facts and advisor disputes; scope forgery, secretary/organization-only denial, explicit capabilities and pooled connections; worker revocation during extraction, leases/crash recovery, retry deduplication; sanitized filenames and file limits; PDF, DOCX, text, Markdown, scanned/encrypted/malformed inputs and the harmless EICAR signature; and onboarding/configuration/document browser journeys at 360/768/1280 widths.

## Operational limitations

This remains synthetic local development with English OCR. Document extraction ends at needs_review and is never publication or an academic recommendation. New department configuration and all institutional program/catalog choices require authorized input. Advisor confirmation is not SIS verification. No academic correctness, OCR accuracy, capacity, production security, or legal sufficiency benchmark is claimed.

Docker is required for the real worker. Signature downloads require internet and are subject to upstream CDN cooldowns; failed or unverified updates do not extend freshness. Stale/missing signatures fail closed. Resource limits can reject large/complex documents; errors provide a replacement/retry path. Private filesystem orphans can remain after rollback or cancellation; retention/deletion automation is intentionally deferred pending an approved policy.

See [intake contract](decisions/intake-contract.md) and the [local run guide](../README.md). B05/T018 and general notifications remain Inprogress for later resources. No recommendation/form resources were invented merely to consume profile-change events.
