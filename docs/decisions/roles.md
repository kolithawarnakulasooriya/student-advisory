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
