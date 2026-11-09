# Student advisory implementation package

This package defines a RAG-based academic advising platform with separate frontend and backend components, scoped admin/manager/secretary/advisor/student access, cited student recommendations, advisor participation, human escalation, and sequential student/advisor/manager form signatures. Google Cloud GKE hosts the application and private vLLM GPU inference.

It contains requirements, Codex development guidance, project workflows, and configuration templates. It does not contain the finished application, a provisioned cloud environment, or measured model performance.

## Start here

1. Read [the detailed PRD](docs/PRD.md) and its assumptions.
2. Review [access control](docs/ACCESS_CONTROL.md), [RAG design](docs/RAG_DESIGN.md), and [API/event contracts](docs/API_AND_EVENTS.md).
3. Follow [the implementation backlog](docs/IMPLEMENTATION_BACKLOG.md), beginning with B01.
4. Use [the Codex guide](docs/CODEX_GUIDE.md), root [AGENTS.md](AGENTS.md), and the nested [frontend](frontend/AGENTS.md) and [backend](backend/AGENTS.md) instructions.
5. Read [Google Cloud development](docs/GOOGLE_CLOUD_DEVELOPMENT.md) before adapting [the infrastructure templates](infra/README.md).

## Package contents

| Location | Purpose |
| --- | --- |
| docs/PRD.md | Detailed product requirements and acceptance targets |
| docs/ACCESS_CONTROL.md | Scope, relationship, revocation, and query enforcement |
| docs/RAG_DESIGN.md | Ingestion, hybrid retrieval, guidance, citations, evaluations |
| docs/API_AND_EVENTS.md | Payload examples and transactional event semantics |
| docs/GOOGLE_CLOUD_DEVELOPMENT.md | Cloud setup, private vLLM, CI/CD, monitoring and recovery |
| docs/IMPLEMENTATION_BACKLOG.md | 19 implementation slices with dependencies and exit evidence |
| docs/SOURCES.md | Official source register and version-sensitive references |
| AGENTS.md and frontend/backend instructions | Durable Codex project instructions |
| .codex/rules/development.rules | Six supplemental Starlark command guardrails |
| .codex/personas | Seven specialist briefs with explicit usage guidance |
| .codex/prompts | Implementation, review, and cloud-pilot task templates |
| .agents/skills | Five repo-scoped workflows for access, RAG, guidance, signatures, cloud |
| infra/k8s | Private vLLM and ingress NetworkPolicy templates |
| .env.example | Development variable contract with synthetic/mock defaults |
| evals/scenarios.jsonl | 24 synthetic behavioral seed scenarios, not a benchmark result |
| scripts/validate_package.py | Package consistency checker using Python and PyYAML |

## Key decisions

Secretary is a delegated department enrollment/assignment role. Advisor guidance is a typed human input that does not trigger an AI reply. Official requirements remain binding unless an authorized exception is recorded. Documents and retrieval settings update the RAG knowledge pipeline without training model weights. Initials/name capture is an authenticated electronic-signature workflow; institutional acceptance must be decided before real use.

All development data must be synthetic. Model/GPU choice, identity integration, signature policy, retention, and budget remain deployment inputs. The manifest templates contain deliberate REPLACE values and are not ready to apply.

## Verify package integrity

Install scripts/requirements-tooling.txt in an isolated Python environment, then run python3 scripts/validate_package.py. This validates the package's references, workflow frontmatter, eval schema, template properties, and embedded command-rule examples. It does not test an unbuilt app. See [validation evidence](docs/VALIDATION.md) for actual checks and limitations.
