# Frontend instructions

Read ../AGENTS.md and ../docs/PRD.md sections 3, 5, 9, and 11. Build a Next.js TypeScript interface against a generated OpenAPI client. Use server-validated capabilities for navigation and actions; hidden controls are not authorization.

Keep student, advisor, manager, secretary, and admin workspaces distinct. Show the active department and scope. Invalidate query caches on department switch, logout, profile changes, assignment changes, and permission epoch changes. Never reuse student-specific responses across identities. Do not store transcripts or auth tokens in localStorage. Use secure cookie sessions with the agreed backend CSRF mechanism.

Display human advisor guidance with author and time. Posting guidance must not render a fabricated assistant typing state. Keep staff-only notes in separate components and API fields. Render Markdown with a restricted renderer and safe URL protocols; never inject raw HTML from documents or the model. Citation links call authorized API routes.

Implement loading, pending approval, empty, forbidden, stale revision, failed ingestion, no evidence, retry, and human case states. Show validated model answers only; progress events are allowed while the backend validates output. Preserve unsent text only in ephemeral memory unless the user opts into a separately approved persistence feature.

For forms, display the exact revision, course list, evidence, signer order, and intent text before initials/name entry. Submit ETag, idempotency key, and current revision. After a 409, discard the old preview and require review again. Never mark a form signed until the server confirms it. Never derive signature identity from a typed name.

Use semantic controls, keyboard access, focus management, useful validation, and screen-reader status announcements. Check 360/768/1280 px layouts. Test critical journeys with synthetic accounts for each role and cross-scope denial cases. Prefer behavior tests over snapshots of implementation details.

Current local commands: npm ci; npm run lint; npm run typecheck; npm run test; npm run test:e2e. These scripts and package-lock.json now exist. Follow ../README.md. Run type generation/build before E2E, not concurrently; Next.js manages next-env.d.ts.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->


Release 0.2 staff screens use the generated OpenAPI client through lib/staff-api.ts. Keep invitation fragments only in memory, remove them from browser history, and preserve them through local registration/verification. Clear scope/identity/permission-epoch state and keep secretary enrollment projections separate from student summaries. Auth failure must reset registration mode and finish the loading state so existing users can sign in again.

T061 uses organization-workspace.tsx and independent /me administration capabilities; it must work without a department membership. Scope selectors and organization grants never imply student-record or appointment authority. Refresh identity/metadata epochs after changes and clear stale edit state on conflict.


Release 0.3 uses intake-workspace.tsx with profile, schema and source workspaces. Use the generated client, clear student-specific state on scope/identity/epoch changes, preserve review-before-completion and catalog confirmation, and keep students read-only for document intake. Extracted text is plain text. Isolated browser runs may set ADVISORY_E2E_API_PORT and ADVISORY_E2E_WEB_PORT without replacing an operator's existing servers.
