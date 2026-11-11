# Synthetic test data — T003 foundation subset

All account addresses end in `@advisory.test`. The operator-only seed command creates deterministic UUIDs, two departments in a synthetic college/institution, and a second institution used solely for isolation checks.

Accounts: student-a/student-b; advisor-a/advisor-b; secretary; manager; platform-admin; super-admin; multi-role; pending; unverified; revoked; suspended; other-institution. Staff must explicitly complete simulated MFA. The multi-role account advises in A and manages B. The super admin has explicit A/B foundation grants; platform admin is limited to A. New registrations receive no grants.

Pending and revoked describe grant states; suspended describes whole-account state. The unverified fixture has a preapproved synthetic student grant, which stays ineffective until verification. Fixture source: `backend/app/seed.py`; test databases use the same deterministic fixture identifiers.

T003 remains partial: catalog years, private sources, contradictory policy examples, and academic gold labels are deferred to their implementing releases. The existing eval seed cases are not reviewed academic policy or measured benchmark results.
