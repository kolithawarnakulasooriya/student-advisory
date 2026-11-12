#!/usr/bin/env python3
"""Validate specification-package integrity, not application functionality.
Uses Python stdlib and PyYAML. Run from any working directory.
"""
from pathlib import Path
import ast
import json
import re
import sys
try:
    import yaml
except ImportError:
    raise SystemExit('Install PyYAML in an isolated tooling environment to validate templates.')

ROOT = Path(__file__).resolve().parents[1]
errors = []
checks = 0

def check(condition, message):
    global checks
    checks += 1
    if not condition:
        errors.append(message)

required = ['README.md', 'AGENTS.md', 'frontend/AGENTS.md', 'backend/AGENTS.md',
    'docs/PRD.md', 'docs/ACCESS_CONTROL.md', 'docs/RAG_DESIGN.md',
    'docs/API_AND_EVENTS.md', 'docs/GOOGLE_CLOUD_DEVELOPMENT.md',
    'docs/CODEX_GUIDE.md', 'docs/IMPLEMENTATION_BACKLOG.md', 'docs/SOURCES.md',
    '.codex/rules/development.rules', 'evals/scenarios.jsonl']
for name in required:
    check((ROOT / name).is_file(), f'Missing required file: {name}')

skills = sorted((ROOT / '.agents/skills').glob('*/SKILL.md'))
check(len(skills) == 5, 'Expected five repository workflows')
for path in skills:
    text = path.read_text()
    parts = text.split('---', 2)
    check(len(parts) == 3 and text.startswith('---\n'), f'Missing frontmatter: {path}')
    if len(parts) != 3:
        continue
    meta = yaml.safe_load(parts[1])
    check(set(meta) == {'name', 'description'}, f'Unexpected skill metadata: {path}')
    check(meta['name'] == path.parent.name, f'Skill name mismatch: {path}')
    check(bool(re.fullmatch(r'[a-z0-9-]{1,63}', meta['name'])), f'Invalid skill name: {path}')
    check(len(meta['description']) > 40 and len(parts[2].strip()) > 100, f'Thin workflow: {path}')

# Walk source assets only; do not traverse dependency or build trees.
import os
ignored = {'local-data', '.git', 'node_modules', '.venv', '.next', '.cache', '.mypy_cache', '.pytest_cache', '.ruff_cache', 'playwright-report', 'test-results'}
markdown_paths = []
for directory, directories, files in os.walk(ROOT):
    directories[:] = [name for name in directories if name not in ignored and not name.startswith(".next-e2e-")]
    markdown_paths.extend(Path(directory) / name for name in files if name.endswith('.md'))
for path in markdown_paths:
    text = path.read_text()
    check(text.count('```') % 2 == 0, f'Unbalanced code fences: {path}')
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', text):
        if re.match(r'^[a-z]+:', target) or target.startswith('#'):
            continue
        file_part = target.split('#', 1)[0]
        check((path.parent / file_part).resolve().exists(), f'Broken local link in {path}: {target}')

scenarios = [json.loads(line) for line in (ROOT / 'evals/scenarios.jsonl').read_text().splitlines() if line.strip()]
check(len(scenarios) >= 20, 'Expected at least twenty behavioral seed cases')
check(len({s['id'] for s in scenarios}) == len(scenarios), 'Duplicate scenario IDs')
for s in scenarios:
    check(set(s) == {'id', 'category', 'setup', 'action', 'expected', 'requirement'}, f'Scenario shape: {s}')
    check(isinstance(s['expected'], list) and bool(s['expected']), f'Missing expectation: {s["id"]}')

# Restrict templates to expected schemas and safety properties. This is not server validation.
docs = list(yaml.safe_load_all((ROOT / 'infra/k8s/vllm.template.yaml').read_text()))
check({d['kind'] for d in docs} == {'ServiceAccount', 'Deployment', 'Service'}, 'Unexpected vLLM objects')
service = next(d for d in docs if d['kind'] == 'Service')
check(service['spec']['type'] == 'ClusterIP', 'vLLM must remain internal')
deployment = next(d for d in docs if d['kind'] == 'Deployment')
container = deployment['spec']['template']['spec']['containers'][0]
check(container['resources']['limits']['nvidia.com/gpu'] == '1', 'GPU template resource missing')
check('--disable-log-requests' in container['args'], 'Request logging must be disabled')
check('REPLACE' in container['image'], 'Template must clearly flag unresolved image')
check(any(e['name'] == 'VLLM_API_KEY' and 'valueFrom' in e for e in container['env']), 'No secret-based API key')
policy = yaml.safe_load((ROOT / 'infra/k8s/vllm-network-policy.template.yaml').read_text())
source = policy['spec']['ingress'][0]['from'][0]
check('namespaceSelector' in source and 'podSelector' in source, 'Caller needs both namespace and pod selector')

# Parse the documented Starlark subset and its inline prefix examples without executing code.
# Native Codex execpolicy validation is still required in the target environment.
rules_tree = ast.parse((ROOT / '.codex/rules/development.rules').read_text())
rule_count = 0
for statement in rules_tree.body:
    check(isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call), 'Unexpected rule statement')
    call = statement.value
    check(isinstance(call.func, ast.Name) and call.func.id == 'prefix_rule', 'Unexpected rule function')
    check(not call.args, 'Rules should use named fields')
    fields = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}
    pattern = fields['pattern']
    check(fields['decision'] in {'allow', 'prompt', 'forbidden'}, 'Invalid rule decision')
    def matches(command):
        import shlex
        argv = shlex.split(command)
        return len(argv) >= len(pattern) and all(
            argv[i] == token if isinstance(token, str) else argv[i] in token
            for i, token in enumerate(pattern))
    for command in fields.get('match', []):
        check(matches(command), f'Inline match failed: {command}')
    for command in fields.get('not_match', []):
        check(not matches(command), f'Inline not_match failed: {command}')
    rule_count += 1
check(rule_count == 6, 'Expected six command rules')
if errors:
    print('\n'.join(errors), file=sys.stderr)
    raise SystemExit(1)
print(f'PASS: {checks} package checks; {len(skills)} workflows; {len(scenarios)} seed cases; {rule_count} rules.')
print('Not tested here: application behavior, native Codex engine, Kubernetes server validation, GPU fit, cloud deployment, or legal sufficiency.')
