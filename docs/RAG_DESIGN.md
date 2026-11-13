# Retrieval and generation design

## Contract
Inputs are an authorized student turn, a versioned academic profile, active student-visible advisor guidance, typed policy rules, and the applicable published knowledge release. Outputs are a validated answer, evidence references, assumptions, constraint outcomes, a saved plan proposal where relevant, and a human-help disposition. The model cannot modify roles, publish documents, send email, sign forms, or enroll a student.

## Ingestion
Validate file headers and size; quarantine; scan; extract text in a sandbox without network; OCR scanned pages where needed; preserve page/heading locators; obtain metadata review; chunk; embed; verify completeness; publish atomically. Suggested starting chunk size is 500–800 tokens with 80–120 overlap, measured against course catalogs. This is a tuning hypothesis, not a proven optimum. Keep a course description/prerequisite group together when possible. Retain source hash, extractor/chunker versions, embedding revision/dimension, and release ID.

Normalize pasted rules through a typed schema. Example fields: course_id, prerequisite_expression, minimum_grade, credit_limit, catalog_validity, and approving_owner. Keep human readable policy text as evidence. Never translate ambiguous prose into a binding machine rule without policy-owner review. A text instruction from a manager is neither executable code nor a role grant.

## Query pipeline
1. Authenticate the student and resolve institution, department, profile/catalog, assignment epoch, and active grants.
2. Collect active student-visible advisor guidance with chat/global-to-that-student scope; discard expired or superseded guidance. Keep staff-only notes entirely outside this path.
3. Resolve allowed published source versions with correct catalog/effective period. Historical catalog sources remain eligible for the student's catalog even if a newer catalog exists.
4. Run filtered PostgreSQL full-text and pgvector retrieval on authorized applicable chunks. Fuse ranks, then rerank only those candidates. Suggested initial retrieval sizes: 30 per channel, merged to 40, reranked to 10; tune using Recall@10 and citation support.
5. Assemble context with stable evidence IDs, exact excerpts, authority metadata, typed academic rules, known facts and uncertainty, and relevant advisor guidance. Reserve output tokens and respect total model context. Do not truncate away the rule or scope metadata.
6. Generate a structured answer using a tested chat template. Buffer the result for validation.
7. Validate schema, evidence IDs, excerpt support for course claims, prohibited actions, and deterministic constraints. On failure, allow one bounded repair; otherwise abstain and offer advisor escalation.
8. Revalidate grant/profile/guidance/knowledge epochs, persist message plus retrieval trace, and return only the validated answer. Discard stale output.

## Generation response schema
```json
{
  "status": "answered",
  "answer": "Plain language advice with source references",
  "claims": [{"text": "Requirement statement", "evidence_ids": ["chunk-42"]}],
  "assumptions": ["Current course enrollment is student reported"],
  "constraints": [{"rule_id": "rule-7", "result": "pass"}],
  "recommended_actions": ["Discuss the proposed term with your advisor"],
  "escalation": {"recommended": false, "reason_code": null},
  "context_version": "server-generated-context-id"
}
```
Allowed statuses: answered, needs_clarification, needs_advisor, blocked, and failed. A syntactically valid JSON answer is not proof of grounding. Evidence checking includes exact source association and support review, with human evaluation for ambiguous claims. The backend owns context_version and action execution.

## Advisor guidance examples
A student asks for a four-course term. Their advisor posts “Prioritize the required lab next term; keep the workload to three courses.” Persist this as student-visible guidance with no assistant reply. When the student next asks for a plan, propose a three-course plan including the lab only if eligibility and offering evidence support it. Cite the official lab rule and identify the advisor preference separately.

If the advisor writes “Skip the prerequisite” without an approved exception, do not treat that as a waiver. Explain the conflicting requirement and offer a case for an authorized exception decision. If the advisor stores a private concern as a staff-only note, neither the note nor a summary derived from it enters the student's answer.

## Releases and evaluation
A retrieval release records source set, prompt release, embedding/reranker revisions, chunk settings, chat model/digest, and evaluation results. Changes to any component trigger the relevant regression suite. Re-embedding builds a parallel index; compare, switch a release pointer, and keep rollback data. Never mix dimensions or embedding spaces in one query.

Use at least 200 labeled pilot questions, including answerable requirement questions, missing-data cases, conflicting catalogs, student-specific evidence, advisor preferences, policy conflicts, prompt injection, and cross-scope privacy attempts. Partition by student and catalog to avoid evaluation leakage. Measure retrieval separately from generation. Record false definitive answers, claim support, escalation quality, and subgroup/program coverage. Human reviewers approve policy-specific gold labels.

The small evals/scenarios.jsonl file in this package defines behavioral seed cases, not a 200-question benchmark and not measured results. The listed synthetic catalog facts must never be treated as institutional policy.

## Failure behavior
If vLLM is unavailable, show a temporary failure and a human-help action; preserve the student's question. If retrieval has no support, ask for missing facts or escalate. If the database cannot verify permissions, fail closed. If evidence is withdrawn during generation, discard and recompute against the current release. Do not fall back to the model's general memory for institution-specific requirements.


## Release 0.4 local implementation

The synthetic local implementation follows [the advising contract](decisions/advising-contract.md): exact filtered SQL retrieval, pinned 768-dimensional Nomic embeddings, ONNX CPU reranking and quote-first Qwen evidence selection. See [observed release evidence](RELEASE_0_4.md), [model manifest](../infra/inference/models.lock.json) and the frozen evals/retrieval-v1.json fixture. The local -8 reranker admission floor and tiny fixture results are starting regression controls, not pilot benchmarks. vLLM has adapter contract coverage only; cloud deployment, production calibration and comprehensive academic validation remain pending.
