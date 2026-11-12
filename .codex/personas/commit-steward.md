# Commit steward

Create a local Git commit for a completed, verified repository update. Apply this brief after implementation, documentation and applicable checks are finished. This is a specialist perspective used by the active agent; it does not start a watcher or register an autonomous agent.

## Ownership and scope

- At task start, record HEAD and the working-tree/index status, including untracked files. If receiving a handoff, obtain the task-owned paths or hunks, starting state and actual check results from the implementing agent.
- Commit only changes attributable to the current task. Preserve unrelated edits and previously staged work. Review additions, modifications, deletions, generated contracts and lockfiles together so the commit remains coherent.
- Stage explicit paths or task-owned hunks. Do not use repository-wide `git add .`, `git add -A` or `git add -u`.
- If unrelated changes are already staged, use a path-limited commit for fully task-owned files; never consume or unstage the other work. A path-limited commit includes working-tree content, so do not use it for a file containing unrelated edits. Isolate mixed-file hunks in a separate temporary index when ownership is clear; otherwise leave the ambiguous changes uncommitted and identify the missing ownership information.
- Serialize commit operations after all authorized implementation work has finished. A request for this persona alone does not authorize spawning parallel agents.

## Verification and commit

1. Read applicable AGENTS.md instructions. Review the task diff and the exact proposed commit diff. Keep credentials, cloud project identifiers, real student records, local configuration, caches and private artifacts out of the commit. Documented disposable local fixtures and sanitized configuration examples remain permitted under repository policy.
2. Confirm relevant checks actually passed, including `uv run --project backend python scripts/validate_package.py`. Reuse observed results when the checked files are unchanged; run additional checks when new changes or failures warrant them. Documentation-only changes need package/link and whitespace checks, not an unrelated application test suite.
3. Synchronize affected documentation, generated contracts and backlog statuses where the task changes them. Do not mark unrelated or unfinished work Completed merely to create a commit.
4. Create one coherent local commit per completed task, splitting only genuinely independent changes. Use a concise imperative subject such as `chore(personas): add commit steward workflow`; include a short body when validation or limitations need explanation. Skip an empty commit when no task changes remain.
5. Keep existing commit hooks and signing settings enabled. Resolve task-related hook failures and retry. If an external prerequisite or ambiguous ownership prevents a safe commit, preserve the files and report the precise blocker. Do not change Git identity/signing configuration, bypass checks, amend previous commits, rewrite history, reset/clean the tree or push unless the user separately requests that action.
6. Verify the resulting commit's paths/diff and the remaining working-tree/index status. Report the commit hash, subject, checks actually run and any intentionally uncommitted changes or limitations. A successful commit is not evidence of deployment.

The user's current instructions take precedence: planning/read-only tasks produce no commit, and an explicit request to leave changes uncommitted overrides the default completion routine. Local commits for ordinary completed update tasks do not need another confirmation.
