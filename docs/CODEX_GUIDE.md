# Codex development workflow

## Package use
Place the contents of this package at the repository root before implementing the app. AGENTS.md is uppercase because it is the recognized instruction filename. frontend/AGENTS.md and backend/AGENTS.md apply when Codex works in those directories. Keep those directories when scaffolding; do not overwrite the instructions.

The .agents/skills directories contain repository-scoped workflow instructions. They are project assets and are not installed into a personal skill catalog. The .codex/personas Markdown files are selectable specialist briefs: explicitly read one in a task prompt. They do not automatically register agents or start parallel work. The .codex/prompts files are task templates, not built-in slash commands. This package does not claim a custom persona Markdown file or prompt filename is a native Codex API.

The .codex/rules/development.rules file uses Starlark prefix rules supported by Codex. Project-local loading depends on a trusted project configuration layer and the installed Codex version. Confirm the current documentation and effective loaded policy; the presence of this file alone does not prove enforcement. If project rules are unsupported, have the operator configure equivalent rules in the supported config layer. Do not silently alter global settings.

Rules match command prefixes. They are supplemental guardrails and can miss reordered flags, alternate CLIs, wrappers, shell composition, and direct API calls. Application RBAC and operator review do not depend on them. No broad allow rules are provided. Prompt rules concern cloud mutations or destructive operations; routine code and documentation work should proceed within the user's authorization.

## Validate rules in an environment with Codex CLI
```bash
codex execpolicy check --pretty --rules .codex/rules/development.rules -- terraform apply plan.out
codex execpolicy check --pretty --rules .codex/rules/development.rules -- git push --force origin main
codex execpolicy check --pretty --rules .codex/rules/development.rules -- git diff
```
Expected decisions: prompt, forbidden, and no matching rule respectively. No matching rule is not an unconditional permission grant; other configuration still governs. The package validator checks the restricted syntax and embedded examples but does not run the native Codex engine.

## Start a bounded implementation task
Use .codex/prompts/implement-slice.md. Ask Codex to read root and nested instructions, select one backlog item, and implement its full UI/API/data behavior. Use one persona when helpful; do not silently start parallel agents. Keep migrations reviewable, preserve synthetic data boundaries, and generate typed API clients from the contract.

Example task:

> Read AGENTS.md and the nested instructions. Implement B01 from docs/IMPLEMENTATION_BACKLOG.md. Read .codex/personas/backend-engineer.md and .codex/personas/frontend-engineer.md for their relevant perspectives. Create a working synthetic local application skeleton, lock dependencies, and add real lint/type/test scripts. Do not implement advisory answers yet. Report what runs and what remains unimplemented.

For authorization work, request the access-policy workflow. For RAG changes, use the retrieval workflow and frozen evals. For forms, use the signature workflow. For deployment work, use the cloud workflow. A specialist perspective cannot grant authority to deploy or read real records.

## Completion evidence
A change report names requirement IDs, migration/API effects, tests actually executed, evaluation results where relevant, and remaining risks. Never say deployed without observed deployment evidence. Never state that seed cases establish academic correctness. Do not show invented passing output for tools unavailable in the environment.

## Package integrity command
```bash
python3 -m pip install -r scripts/requirements-tooling.txt
python3 scripts/validate_package.py
```
This checks required assets, skill frontmatter, local Markdown links, eval seed schema, YAML template structure, and rule inline examples. It does not test an app, cloud connectivity, model quality, legal compliance, or live permission enforcement.
