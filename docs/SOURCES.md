# Official source register

References checked November 5, 2026. The architecture and product defaults are design proposals; official documentation supports the listed service capabilities, not a guarantee about this unbuilt application's performance or compliance. Consult the versioned documentation matching pinned tools before deployment.

| ID | Official reference | Use in this package |
| --- | --- | --- |
| S1 | [vLLM Docker deployment](https://docs.vllm.ai/en/stable/deployment/docker/) | Official serving image and deployment interface |
| S2 | [vLLM quickstart](https://docs.vllm.ai/en/stable/getting_started/quickstart/) | OpenAI-compatible inference interface |
| S3 | [GKE GPU serving with vLLM](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/serve-gemma-gpu-vllm) | Dedicated GPU inference deployment pattern |
| S4 | [Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity) | Workload identities for Google API access |
| S5 | [GKE network policy](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/network-policy) | Pod traffic restrictions and enforcement prerequisites |
| S6 | [Cloud SQL PostgreSQL extensions](https://docs.cloud.google.com/sql/docs/postgres/extensions) | Verify pgvector compatibility for selected database version |
| S7 | [Codex rules](https://learn.chatgpt.com/docs/agent-configuration/rules) and [repo skills](https://learn.chatgpt.com/docs/build-skills) | AGENTS guidance, Starlark prefix rules, repo skill discovery |
| S8 | [US Department of Education staff access guidance](https://studentprivacy.ed.gov/faq/under-ferpa-may-educational-agency-or-institution-disclose-education-records-any-its-employees) | Legitimate educational interest as a privacy design consideration |

Uploading sources to RAG, changing prompts, and tuning retrieval parameters do not modify neural-network weights. No training process is specified in the MVP. Choosing to fine-tune later requires separate data governance, model evaluation, licensing, and deployment decisions.
