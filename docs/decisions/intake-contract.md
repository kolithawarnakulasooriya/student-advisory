# Release 0.3 local intake contract

This implements ON-01–04, KN-01–03 and the T021 portion of RG-08/FO-05 for synthetic local development. It does not establish institutional catalog requirements or deploy a pilot.

## Profiles and configuration

A profile belongs to a student membership, not a user/email. Department managers and explicitly delegated `profile.configure` administrators configure versioned academic questions, program/track choices, catalogs and terms. Organization metadata grants have no operational authority. Synthetic seeds supply examples; new departments require explicit configuration.

`GET /students/{mid}/profile` returns a profile ETag (`"0"` before the first save). PATCH appends a complete snapshot. Requests may supply a subset of facts; omitted facts are retained. Explicit null means unknown. Student identity, source, self-reported verification and recorded time are server-owned. College/department derive from membership. A completed course is never inferred from presence in a list or an absent completion flag. Grades are optional and should be supplied only for a stated prerequisite need.

New schemas never rewrite old profiles. Students explicitly adopt the active schema and review missing/invalid fields; prior values remain in history and retained values are checked against the new schema before completion. Completion requires required answers plus explicit catalog confirmation and profile review in the UI. Advisor confirmations/disputes append a new snapshot without modifying original facts. They are not SIS verification or waivers. Changed facts retire their previous reviews from the current projection, while immutable history retains them.

All profile/schema transitions require CSRF, current authority, recent authentication, idempotency and If-Match. Conflicts return 409 and require a fresh review. An idempotent response is returned only after current object authorization. Drafts are visible to authorized record readers and labeled incomplete.

`profile.changed` is inserted transactionally, with student membership as aggregate ID and profile revision as aggregate version. It contains routing metadata only. Context tokens bind membership, profile revision and relationship epoch. Future recommendation/form consumers must deduplicate by consumer/event ID, load authorized current data, compare context tokens, invalidate stale recommendations and flag pending forms for review. The `/profile/context` endpoint reports staleness. There are no recommendation/form consumers in this release because those resources do not yet exist.

## Sources and worker boundaries

Students read their own evidence but cannot upload in MVP. Assigned advisors upload student evidence only; managers manage their operational scope. Platform administrators need `source.read`/`source.manage` grants; student evidence additionally requires current student-record authority. Super-admin sensitive access requires an audited purpose. Schema/source grants never imply student-record access, and secretary/organization grants confer none of these powers.

One source has an immutable institution, org, visibility and student membership binding. Replacements and metadata edits create immutable versions; there is no scope-broadening edit. History, filenames, counts, processing status, extracted text and downloads share current authorization. Original files are downloaded as attachments through the API only after successful scanning/extraction. Archive is terminal for intake mutations and cancels new worker output through current-state checks. No source in Release 0.3 is published or retrieval-eligible.

Private quarantine and extracted artifacts live below `local-data/intake`, outside the frontend. Object keys are generated UUIDs; filenames are display metadata. Filesystem writes and database commits are separate: failed transactions or revoked jobs can leave private orphan files. No automatic destructive cleanup or retention policy is invented. Operators may remove the disposable local intake directory only as part of an intentional synthetic-environment reset; database reset itself does not delete arbitrary filesystem paths.

Run the host worker as a non-root local operator; root execution is rejected. Private-storage configuration under the frontend is rejected. The trusted host worker uses the dedicated non-owner `advisory_ingest` role, leases jobs and invokes Docker through argument arrays. The API has no Docker integration. Parsers receive one read-only file, no DB credentials or network, and a bounded temporary filesystem. Scan and extraction are separate disposable containers. Scanner signature updating has network access and mounts only the signature directory, never documents.

Defaults are operational limits, not measured throughput: 25 MiB input; 200 PDF pages; 8 MiB extracted JSON; 50 MiB expanded DOCX, 10 MiB per entry, 2,000 entries, maximum compression ratio 200; 240 seconds per stage; one CPU; 2 GiB scanner/768 MiB extractor memory; 64 processes; 256 MiB temporary storage. These require institutional review before real use. Oversized requests are bounded before multipart spooling. PDF/DOCX signatures are checked; encrypted, unsafe, malformed or unreadable documents fail clearly. Text/Markdown are UTF-8. OCR is English only, and every OCR artifact requires review.

Pipeline states are `uploaded → scanning → extracting → needs_review`, or `failed`/`cancelled`. No indexing/publication states are entered. The immutable version has up to three attempts. An expired worker lease becomes `failed/WORKER_INTERRUPTED`, permitting an authorized explicit retry; it cannot overwrite a newer attempt. Jobs recheck creator grants, membership relationship epochs, source state/version and current permissions before reads and final commit. Final commit is serialized with authority changes. Successful extraction and its outbox event commit together; retries cannot duplicate artifacts. Jobs cancelled by reassignment can be retried by a currently authorized actor.

Scanner signatures must have a fully verified update within 48 hours. The updater does not refresh the marker on failure or CDN cooldown, even if FreshClam exits zero. Keep the parser image and signatures current. Parser image IDs and extractor revision are recorded with artifacts. A local immutable image ID is resolved before each container launch.

## Assumptions and deferred decisions

Only synthetic `.test` identities and fixtures are supported. Live identity, SIS authority, real institutional programs/catalogs, retention/deletion approval, additional OCR languages, production storage, publication, embeddings, advising answers and form consumers are deferred. There are no academic-rule, OCR-accuracy, performance, legal-sufficiency or production-security claims.
