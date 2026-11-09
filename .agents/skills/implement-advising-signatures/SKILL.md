---
name: implement-advising-signatures
description: Implement or review student advisor and manager form signatures in this advisory repository. Use for form creation, immutable revisions, returns, signer reassignment, holds, stale previews, and concurrent signing.
---

# Implement advising signatures

Read PRD FO-01 through FO-07 and [the signing contract](../../../docs/API_AND_EVENTS.md).
1. Freeze template, plan, academic facts, evidence, guidance, and expected signers into a canonical revision. Keep artifact durability/checksum separate from canonical content hash.
2. Require full preview, current ETag, authenticated eligible signer, recent auth, affirmative intent, consent version, and initials/name.
3. Enforce student then advisor then manager with a transaction, unique revision/step constraint, idempotency, audit, and outbox.
4. Create a successor revision for material edits or signer changes and require all signatures again. Preserve prior signed content.
5. Hold pending forms for relevant policy, profile, or eligibility changes; revalidate before release. Never edit a completed form.
6. Test stale preview, skipped step, wrong signer, duplicate parallel submissions, return/resubmit, reassignment, and unauthorized artifact download.
Return state guards, hash/artifact decisions, concurrency evidence, and unresolved institutional signature policy. Do not claim that a content hash authenticates a signer or proves legal validity.
