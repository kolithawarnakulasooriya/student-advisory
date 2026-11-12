# Specialist briefs

Read a brief explicitly when its expertise is useful. Each brief defines a perspective and expected evidence, not a separately configured autonomous agent. User authorization and repository instructions still control all work. Do not start subagents unless requested.

| Brief | Use |
| --- | --- |
| product-architect.md | Requirement decisions and traceability |
| backend-engineer.md | Services, authorization and transactions |
| frontend-engineer.md | Role workflows and accessible UI |
| rag-engineer.md | Retrieval, grounded answers and guidance behavior |
| security-reviewer.md | Privacy and cross-scope negative tests |
| cloud-engineer.md | GKE, vLLM, IAM, rollout and operations |
| qa-reviewer.md | Independent acceptance evidence and release gaps |
| [commit-steward.md](commit-steward.md) | Commit completed, verified task changes locally while preserving unrelated work |

For repository update tasks, apply the commit-steward brief at completion as required by the root [AGENTS.md](../../AGENTS.md). This is the default finish step for the active agent; persona Markdown does not create a background file watcher or authorize parallel agents.
