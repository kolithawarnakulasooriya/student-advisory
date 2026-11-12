import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import StaffWorkspace from "../app/staff-workspace";
import type { Me } from "../lib/api";
import { ApiError } from "../lib/api";
const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PUT: vi.fn(),
  PATCH: vi.fn(),
}));
vi.mock("../lib/staff-api", () => ({
  staffApi: mocks,
  revision: (n: number) => ({ "If-Match": `"${n}"` }),
}));
const base: Me = {
  user_id: "actor",
  email: "manager@advisory.test",
  name: "Synthetic Manager",
  verified: true,
  account_state: "active",
  membership_state: "active",
  mfa_required: false,
  recent_auth: true,
  grant_epoch: 1,
  active_scope: "dept-a",
  active_grants: [],
  memberships: [],
  scopes: [],
  capabilities: [],
  expires_at: "2026-11-12T00:00:00Z",
  identity_mode: "synthetic",
  administration_capabilities: [],
  organization_grants: [],
  organization_epochs: {},
  platform_grants: [],
  student_memberships: [],
};
const refreshMe = vi.fn(async () => {});
const clearInvitation = vi.fn();
const row = {
  id: "request-a",
  user_id: "new-student",
  org_unit_id: "dept-a",
  requested_role: "student",
  justification: "Synthetic enrollment request",
  status: "pending",
  decision_reason: null,
  version: 1,
  name: "Synthetic Requester",
  email: "new@advisory.test",
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.POST.mockResolvedValue({ data: { status: "saved" } });
  mocks.GET.mockImplementation(async (path: string) => ({
    data: path.endsWith("membership-options")
      ? {
          items: [{ id: "dept-a", name: "Synthetic Department A" }],
          next_cursor: null,
          total: 1,
        }
      : path.endsWith("eligible-advisors")
        ? {
            items: [
              {
                id: "advisor-a",
                user_id: "advisor",
                name: "Synthetic Advisor",
                email: "advisor@advisory.test",
                capacity: null,
                assigned_count: 1,
              },
            ],
            next_cursor: null,
            total: 1,
          }
        : {
            items: path.endsWith("membership-requests") ? [row] : [],
            total: path.endsWith("membership-requests") ? 1 : 0,
            next_cursor: null,
          },
  }));
});
it("lets verified accounts request membership without granting privileges", async () => {
  render(
    <StaffWorkspace
      me={base}
      refreshMe={refreshMe}
      invitation=""
      clearInvitation={clearInvitation}
    />,
  );
  await screen.findByText("Synthetic Department A");
  fireEvent.click(screen.getByText("Request a membership"));
  fireEvent.change(screen.getByLabelText("Justification"), {
    target: { value: "Synthetic request" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Submit membership request" }),
  );
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith("/api/v1/membership-requests", {
      body: {
        org_unit_id: "dept-a",
        requested_role: "student",
        justification: "Synthetic request",
      },
    }),
  );
  expect(screen.queryByRole("button", { name: "Memberships" })).toBeNull();
});
it("requires an advisor and a reason before approval", async () => {
  render(
    <StaffWorkspace
      me={{ ...base, capabilities: ["student.approve"] }}
      refreshMe={refreshMe}
      invitation=""
      clearInvitation={clearInvitation}
    />,
  );
  const approve = await screen.findByRole("button", {
    name: "Approve student",
  });
  expect(approve).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Primary advisor"), {
    target: { value: "advisor-a" },
  });
  fireEvent.click(approve);
  expect(
    await screen.findByRole("alert", { name: "Workflow error" }),
  ).toHaveTextContent("Enter a reason");
  expect(mocks.POST).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Reason for staff action"), {
    target: { value: "Synthetic approval" },
  });
  fireEvent.click(approve);
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith(
      "/api/v1/membership-requests/{rid}/approve",
      {
        params: { path: { rid: "request-a" } },
        headers: { "If-Match": '"1"' },
        body: { reason: "Synthetic approval", advisor_grant_id: "advisor-a" },
      },
    ),
  );
});
it("keeps secretary enrollment separate from student records", async () => {
  render(
    <StaffWorkspace
      me={{
        ...base,
        capabilities: [
          "student.approve",
          "membership.read",
          "assignment.manage",
          "audit.own",
        ],
      }}
      refreshMe={refreshMe}
      invitation=""
      clearInvitation={clearInvitation}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Memberships" }));
  await screen.findByText(
    "Enrollment metadata only. Secretary permissions do not include student records.",
  );
  expect(screen.queryByRole("button", { name: "Students" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Users" })).toBeNull();
});
it("reports stale approval without claiming success", async () => {
  mocks.POST.mockRejectedValue(
    new ApiError(
      409,
      "STALE_REVISION",
      "This item changed. Refresh and review it again.",
    ),
  );
  render(
    <StaffWorkspace
      me={{ ...base, capabilities: ["student.approve"] }}
      refreshMe={refreshMe}
      invitation=""
      clearInvitation={clearInvitation}
    />,
  );
  await screen.findByRole("button", { name: "Approve student" });
  fireEvent.change(screen.getByLabelText("Primary advisor"), {
    target: { value: "advisor-a" },
  });
  fireEvent.change(screen.getByLabelText("Reason for staff action"), {
    target: { value: "Synthetic decision" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Approve student" }));
  expect(
    await screen.findByRole("alert", { name: "Workflow error" }),
  ).toHaveTextContent("Refresh and review");
  expect(
    screen.queryByText(
      "Saved. Permissions and state were checked by the server.",
    ),
  ).toBeNull();
});
it("keeps invitation tokens out of rendered text", async () => {
  render(
    <StaffWorkspace
      me={base}
      refreshMe={refreshMe}
      invitation="opaque-secret-token"
      clearInvitation={clearInvitation}
    />,
  );
  expect(screen.queryByText("opaque-secret-token")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));
  await waitFor(() =>
    expect(mocks.POST).toHaveBeenCalledWith("/api/v1/invitations/accept", {
      body: { token: "opaque-secret-token" },
    }),
  );
  expect(clearInvitation).toHaveBeenCalledOnce();
});
