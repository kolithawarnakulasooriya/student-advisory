# Release 0.4 — Retrieval, cited answers and advisor guidance

## Delivered scope

| Tasks | Delivered behavior |
| --- | --- |
| T025–T026 | Immutable exact-span chunks and embedding configurations; complete index builds; reviewed publication, atomic replacements/rebuilds, withdrawal and authorized historical citations |
| T027 | Versioned typed evidence-backed rules, bounded department terminology/clarifications, global prompt style controls, recorded evaluation and authorized activation/rollback |
| T028–T030 | SQL-filtered full-text/vector retrieval, RRF, private ONNX reranking, pinned local Ollama and vLLM-compatible/test adapters, quote-first validated dispositions and safe clarification/human escalation |
| T031–T032 | Membership-bound conversations, immutable student questions, leased generation attempts, current context validation, explicit retries, buffered validated answers, restricted Markdown and evidence drawers |
| T033–T035 | Separate visible advisor guidance, private notes and explicit private drafts; zero automatic guidance replies; active guidance on subsequent turns; reviewed advisor-authored draft publication |
| T037–T038 subset | Idempotent durable human-help receipts, status/history, current-advisor routing and manager fallback, audited lifecycle transitions and staff queue |

Additive migrations 0016–0022 preserve prior records. Forced RLS covers all new records; the worker cannot SELECT staff notes. Backend modules, generated OpenAPI/frontend types/Postman, source/advising/governance/case screens, private inference Compose profile and CI model gate are included. See the [advising contract](decisions/advising-contract.md) for exact state, authority and consumer boundaries.

Case notification/email/business-calendar portions remain Inprogress. B05/T018 retain unfinished future-resource portions. Comprehensive plan validation, saved plans, signatures, real identity and cloud deployment remain later releases.

## Measured synthetic model evidence

The frozen [retrieval fixture](../evals/retrieval-v1.json) derives from the repository's catalog, private-evidence, injection/replacement and withdrawal scenarios. It contains labeled applicability negatives and positive/unsupported queries. Recall@10 and reciprocal rank are measured separately from answer generation; the fixture is a tiny regression set, not an institutional pilot or a production accuracy benchmark.

Observed local runs use Apple M1 CPU, an approximately 4 GiB Docker budget, one active heavy job, one loaded Ollama model/request, 4,096 chat-context tokens and 512 output tokens. Chat is qwen3:0.6b; embeddings are nomic-embed-text:v1.5, 768 dimensions; the distinct ONNX CPU reranker is cross-encoder/ms-marco-MiniLM-L6-v2. Exact hashes, revisions and license/card references are in [the model manifest](../infra/inference/models.lock.json); tested container/build inputs are in [the runtime manifest](../infra/inference/runtime.lock.json).

The final four-document run ranked the applicable catalog first for both supported queries (Recall@10=1 and MRR@10=1 across those two queries), with zero excluded catalog/program/private-student candidates reaching reranking. Positive reranker scores were 7.1023 and 4.3563; the unsupported refund query scored -11.2893 and admitted no excerpt. Four fixtures indexed in 8.706 seconds. The cited answer and guidance-aware follow-up took 18.831 and 21.589 seconds; exception and unsupported-query dispositions took 0.161 and 1.556 seconds. The durable case remained open. See [sanitized actual results](../evals/results/release-0.4-m1.json) for the dataset hash, exact runtime fingerprint and separate retrieval/generation measurements.

A Docker stats sample during generation showed Ollama at 1.09 GiB/2 GiB and about two CPU cores, the gateway at 199.3 MiB/512 MiB, PostgreSQL at 192.8 MiB and Mailpit at 34.1 MiB. This is a sampled observation, not a peak-memory or throughput benchmark. English only; limits require measurement on each host.

An initial real-model run incorrectly selected a prerequisite excerpt for a waiver question. No arbitrary model-written claim was rendered. The implementation now routes exception/waiver/bypass requests to human review on the server and applies the measured relevance admission floor to unrelated questions. Later real runs demonstrated supported cited answers and guidance-aware follow-up, plus safe exception/unsupported abstention. The small model is not trusted to approve policy exceptions or establish academic eligibility.

## Verification record

Observed checks before final delivery include:

- Real PostgreSQL ordinary backend suite: 173 passed, four opt-in external-tool tests skipped in that run. The final focused advising run passed 30 tests, including the last event-revision, skip-guidance and supersession hardening.
- Strict mypy for 37 application modules, Ruff, additive Alembic upgrade/drift check, generated OpenAPI/frontend contract checks and Postman generation.
- Frontend lint/types, 22 component tests and production build.
- All 37 browser tests passed, including the new journey through real scan/extraction, indexing/publication, keyboard question submission, citation drawer, zero-job guidance, note isolation, durable case and former-advisor access loss; chat layouts at 360/768/1280 pixels.
- Separate actual Ollama/ONNX gate: cited answer, exception/unsupported abstention, guidance-aware follow-up and durable case. Deterministic tests do not substitute for this gate.

Real parser gates passed all three tests (format/scanner/OCR, database commit and DOCX expansion). Package integrity passed 310 checks; generated contracts/Postman matched, whitespace checks passed, and frontend production dependency audit reported zero vulnerabilities. CI includes actual private-container preparation and the real Ollama gate, uploading only sanitized synthetic metrics and public runtime identity. Hosted CI has not been run by pushing this local implementation.

## Operating limits and assumptions

Use [the local run guide](../README.md). Inference is opt-in; disabled or unavailable inference fails closed. Preparation downloads public artifacts separately. Startup checks hashed build inputs, explicit build identity, model digests, tokenizer/ONNX hashes and dimensions. Ollama has no host port or external network. The token-protected gateway is loopback only; no gateway token or raw endpoint enters the browser.

Student facts remain reported/confirmed according to their provenance; advisor confirmation does not become SIS verification. Missing course completion remains unknown. Rules and source metadata require authorized human review; semantic correctness is not established merely by a passing schema/reference evaluation. Point checks do not provide complete plan validation or course availability.

Workers use bounded leases/retries and current authority/context checks outside model calls. A model-manifest change is supervised maintenance: generation refuses mismatched spaces until a complete compatible index is activated or the prior pinned runtime is restored. Resource contention can delay work; model timeout, scanner failure and stale context have explicit retry/replacement paths. Only reviewed published applicable evidence supports institutional excerpts. Historical citations retain identity and show withdrawal; retention/deletion automation remains pending policy decisions.

No legal conclusion, institutional approval, production readiness, live student data, notification delivery, email SLA, GPU fit or cloud deployment result is claimed.
