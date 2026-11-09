---
name: build-advisory-retrieval
description: Build or change the student advisory RAG ingestion retrieval citation or abstention pipeline. Use for catalog applicability, source publication, embedding changes, prompt releases, or retrieval evaluation; not for model weight training.
---

# Build advisory retrieval

Read [the RAG contract](../../../docs/RAG_DESIGN.md) and [the seed scenarios](../../../evals/scenarios.jsonl).
1. Record the authorized scope, profile/catalog, active guidance, source release, prompt/model/embedding revisions, and token budget.
2. Apply ACL, publication, student, catalog, and effective-date constraints before candidate selection or reranking.
3. Preserve exact version/page/heading evidence and validate each institutional claim against permitted chunks. Keep structured academic checks outside free-form generation.
4. Use relevant active student-visible advisor guidance. Never include staff-only notes or treat ordinary guidance as an approved waiver.
5. Buffer and validate output. Clarify missing facts, abstain for missing/conflicting support, and offer a human case. Revalidate epochs before committing output.
6. Evaluate retrieval and generation separately on a frozen labeled set; report actual results and failures. Seed cases alone cannot establish the proposed pilot metrics.
7. For release changes, build a parallel version, compare, switch atomically, and retain compatible rollback assets.
Return configuration diff, dataset and metric definitions, negative scope evidence, failures, and release/rollback decision. Never turn test-only synthetic catalog facts into real advice.
