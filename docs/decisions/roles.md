# Role and scope decisions — T001

Development defaults follow PRD sections 2–4. These decisions authorize synthetic development, not a real institutional pilot.

| Role | Scope and ceiling |
| --- | --- |
| Super admin | Platform appointment/security authority; later global sensitive reads require an audited purpose. No proxy signatures. |
| Platform admin | Explicit delegated operational, records, publication, or audit grants; no implied global access or super-admin appointment. |
| Manager | Explicit departments only; college appointment expands only to explicitly granted departments. May appoint advisors in that scope, never managers. |
| Secretary | Explicit delegated student enrollment and assignment capabilities; no advisor appointment, publication, transcript, or signing access. |
| Advisor | Active assignments within an active grant; old chat participation preserves no access. |
| Student | Own active department membership and records only. |

Release 0.1 exposes only self-account and explicitly granted organization metadata. Seeded super admins also receive explicit department grants for this foundation; global oversight is deferred until audit exists. Role labels never bypass the foundation boundary. Multiple roles stay attached to their own department.

One primary advisor per active student membership is the MVP default. Department transfers require new approval and a transactional assignment update; historical access and pending form handling remain institutional decisions. No transfer, appointment, delegation, or assignment operation is exposed in 0.1. Unresolved decisions grant no access.


## Release 0.2 operational defaults

Platform-wide super-admin authority is a separate explicit grant, installed by an audited one-time operator bootstrap or by an already authorized super admin. Legacy department labels remain scoped; migrations never promote them. Only global super admins suspend whole accounts. Managers and delegated staff change permitted memberships in their own scopes.

Secretary delegations are individually selected: student invitations, student approvals, student membership management, and assignments. No delegation permits student summaries, academic records, staff appointment, or platform administration. Reactivating a suspended student requires membership management and assignment authority. Platform-admin capability sets and appointment ceilings are explicit; a student ceiling cannot appoint advisors/managers/secretaries, and an advisor ceiling cannot appoint managers.

Activation requires an eligible primary advisor. If an advisor later becomes unavailable, close effective relationships, block their student access, and leave affected students active in the manager's reassignment queue. Capacity is optional per advisor/department; synthetic defaults have no configured limit. Real capacity rules remain an institutional input. Transfers and historical record access across new memberships remain deferred.

Manager self-service requests always route to a platform super admin. Delegated platform admins may manage or invite managers within an explicit manager ceiling, but cannot decide manager self-service requests.

## Organization administration (T061)

Explicit organization-administration grants delegate metadata management to verified active users at an institution or college root, without a required department membership. Only global super admins issue or change delegations. These grants add no operational scope, manager appointment or student-record authority. College grants include only college/child metadata; they never expand department records access. See [organization contract](organization-contract.md).
