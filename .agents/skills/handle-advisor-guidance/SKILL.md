---
name: handle-advisor-guidance
description: Implement or review advisor participation in student chats. Use for prioritized guidance, advisor message routing, staff-only notes, explicit advisor drafts, and guidance supersession; prevent automatic assistant replies to advisor posts.
---

# Handle advisor guidance

Read PRD RG-04 and RG-05 in [the PRD](../../../docs/PRD.md).
1. Distinguish student_question, student_visible_guidance, staff_only_note, and explicit advisor_draft_request with typed handlers.
2. Verify the current assigned advisor and student/chat scope. Persist authorship, validity, version, and supersession.
3. For student-visible guidance, persist and notify without creating a generation job. For private notes, keep the data out of student-visible events and prompt assembly.
4. On a later student turn, load applicable active guidance and incorporate it as a planning priority after platform and official requirement controls.
5. If guidance conflicts with official policy without an authorized exception, explain the conflict and escalate.
6. Test zero assistant jobs after guidance, relevant follow-up use, expired/superseded guidance exclusion, wrong-advisor denial, and private-note non-disclosure.
Return event routing, prompt-context behavior, tests executed, and unresolved conflict examples. Do not create a fake AI acknowledgment to an advisor post.
