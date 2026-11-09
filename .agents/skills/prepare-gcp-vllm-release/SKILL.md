---
name: prepare-gcp-vllm-release
description: Prepare or review this advisory platform deployment on Google Cloud GKE with private vLLM GPU inference. Use for infrastructure plans, workload identity, model pinning, networking, benchmarks, observability, rollout, restore, or rollback.
---

# Prepare a Google Cloud vLLM release

Read [the cloud guide](../../../docs/GOOGLE_CLOUD_DEVELOPMENT.md) and [official sources](../../../docs/SOURCES.md). Treat YAML files as unrendered templates.
1. Resolve environment/project, model license and immutable revision, image digest, GPU quota/availability, context and concurrency targets, private network, and budget.
2. Verify current flags and model/GPU compatibility on the pinned image. Benchmark memory, queueing, complete-answer latency, throughput, and failure modes.
3. Use dedicated workload identities, private SQL/storage/model services, scoped secrets, network enforcement, and service TLS/auth. Never expose vLLM publicly.
4. Render templates and validate against the target cluster. Reject placeholders and mock production settings. Keep secrets out of manifests and logs.
5. Prepare backward-compatible migrations, synthetic full-journey tests, canary rollout, monitoring, and actual backup/restore/rollback steps.
6. Distinguish authored, validated, applied, and observed outcomes. Apply only within authorized scope and after resolving any ambiguous environment.
Return plan, validation/benchmark evidence, cost inputs, security boundary verification, and rollback limitations. No model choice or hardware capacity is guaranteed by the template.
