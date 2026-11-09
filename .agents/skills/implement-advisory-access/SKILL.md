---
name: implement-advisory-access
description: Implement or review role scope and assignment authorization in this student advisory repository. Use for membership approvals, secretary delegation, advisor reassignment, record queries, citations, exports, workers, and revocation.
---

# Implement advisory access

Read [the access specification](../../../docs/ACCESS_CONTROL.md) and the PRD permission matrix before editing.
1. Identify actor, action, institution, org scope, student relationship, visibility, resource state, and recent-auth conditions.
2. Define explicit allow and deny cases. Include pending, suspended, wrong-scope, secretary, former-advisor, and multi-role actors.
3. Implement server-derived AuthContext, scoped query access, and centralized action checks. Add transaction-local RLS where applicable; test with a non-owner database role.
4. Apply the same boundary to metadata, counts, snippets, caches, storage URLs, jobs, notifications, and streams.
5. Increment access epochs and cancel or reauthorize in-flight work on relationship/grant changes.
6. Run meaningful negative integration tests, including pooled connections and revocation during generation.
Return requirement IDs, policy/query changes, observed test results, and any remaining data surface. Do not broaden a role to make a failing test pass.
