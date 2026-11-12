import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import OrganizationWorkspace from "../app/organization-workspace";
import { ApiError, type Me } from "../lib/api";
const api = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PUT: vi.fn(),
  PATCH: vi.fn(),
}));
vi.mock("../lib/staff-api", () => ({
  staffApi: api,
  revision: (n: number) => ({ "If-Match": `"${n}"` }),
}));
const refreshMe = vi.fn(async () => {});
const me: Me = {
  user_id: "admin",
  email: "org-admin@advisory.test",
  name: "Synthetic administrator",
  verified: true,
  account_state: "active",
  membership_state: "awaiting_membership",
  mfa_required: false,
  recent_auth: true,
  grant_epoch: 1,
  active_scope: null,
  active_grants: [],
  memberships: [],
  capabilities: [],
  scopes: [],
  expires_at: "2026-11-12T00:00:00Z",
  identity_mode: "synthetic",
  platform_grants: [],
  student_memberships: [],
  administration_capabilities: ["organization.manage"],
  organization_grants: [
    {
      id: "grant",
      institution_id: "institution",
      scope_kind: "college",
      root_org_unit_id: "college",
      valid_until: null,
    },
  ],
  organization_epochs: { institution: 1 },
};
const college = {
  id: "college",
  institution_id: "institution",
  parent_id: null,
  name: "Synthetic College",
  code: "college",
  kind: "college",
  timezone: "UTC",
  status: "active",
  version: 1,
  enrollment_enabled: false,
};
const department = {
  ...college,
  id: "department",
  parent_id: "college",
  name: "Synthetic Department",
  code: "department",
  kind: "department",
};
beforeEach(() => {
  vi.clearAllMocks();
  api.POST.mockResolvedValue({ data: department });
  api.PATCH.mockResolvedValue({ data: department });
  api.GET.mockImplementation(
    async (
      path: string,
      args?: { params?: { query?: { kind?: string } } },
    ) => ({
      data: {
        items: path.endsWith("/institutions")
          ? [
              {
                id: "institution",
                code: "synthetic",
                name: "Synthetic Institution",
                organization_epoch: 1,
              },
            ]
          : path.endsWith("/admin/org-units")
            ? args?.params?.query?.kind === "college"
              ? [college]
              : [department]
            : [],
        total: 1,
        next_cursor: null,
      },
    }),
  );
});
it("college delegate can create departments without college creation or appointment powers", async () => {
  render(<OrganizationWorkspace me={me} refreshMe={refreshMe} />);
  await screen.findByRole("heading", { name: "Synthetic Department" });
  fireEvent.click(
    screen.getByText("Create a college or department", { exact: true }),
  );
  expect(screen.getByLabelText("Organization type")).toHaveValue("department");
  expect(screen.queryByRole("option", { name: "College" })).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Delegate organization management" }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Appoint department manager" }),
  ).toBeNull();
  fireEvent.change(screen.getByLabelText("Parent college", { exact: true }), {
    target: { value: "college" },
  });
  fireEvent.change(
    screen.getByLabelText("Organization name", { exact: true }),
    { target: { value: "New synthetic department" } },
  );
  fireEvent.change(
    screen.getByLabelText("Organization code", { exact: true }),
    { target: { value: "new-department" } },
  );
  fireEvent.change(screen.getByLabelText("Reason for organization action"), {
    target: { value: "Synthetic creation" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create organization" }));
  await waitFor(() =>
    expect(api.POST).toHaveBeenCalledWith("/api/v1/admin/org-units", {
      body: {
        institution_id: "institution",
        parent_id: "college",
        kind: "department",
        name: "New synthetic department",
        code: "new-department",
        timezone: "America/Chicago",
        reason: "Synthetic creation",
      },
    }),
  );
});
it("requires a reason before changing enrollment", async () => {
  render(<OrganizationWorkspace me={me} refreshMe={refreshMe} />);
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Open membership requests",
    }),
  );
  expect(
    await screen.findByRole("alert", { name: "Organization error" }),
  ).toHaveTextContent("Enter a reason");
  expect(api.PUT).not.toHaveBeenCalled();
});
it("discards stale edits and presents the server conflict", async () => {
  api.PATCH.mockRejectedValue(
    new ApiError(
      409,
      "STALE_REVISION",
      "Refresh and review this organization.",
    ),
  );
  render(<OrganizationWorkspace me={me} refreshMe={refreshMe} />);
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Edit organization",
    }),
  );
  fireEvent.change(screen.getByLabelText("Reason for organization action"), {
    target: { value: "Synthetic edit" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save organization" }));
  expect(
    await screen.findByRole("alert", { name: "Organization error" }),
  ).toHaveTextContent("Refresh and review");
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Save organization" }),
    ).toBeNull(),
  );
});
it("institution administration works without operational department membership", async () => {
  render(
    <OrganizationWorkspace
      me={{
        ...me,
        organization_grants: [
          {
            ...me.organization_grants[0],
            scope_kind: "institution",
            root_org_unit_id: null,
          },
        ],
      }}
      refreshMe={refreshMe}
    />,
  );
  await screen.findByRole("heading", { name: "Synthetic Department" });
  fireEvent.click(
    screen.getByText("Create a college or department", { exact: true }),
  );
  expect(screen.getByLabelText("Organization type")).toHaveValue("college");
  expect(screen.getByRole("option", { name: "College" })).toBeVisible();
});

it("ignores a history response received after an institution switch", async () => {
  const original = api.GET.getMockImplementation()!;
  let resolveHistory!: (value: unknown) => void;
  api.GET.mockImplementation(async (path: string, args?: unknown) => {
    if (path.endsWith("/history"))
      return new Promise((resolve) => {
        resolveHistory = resolve;
      });
    const result = await original(path, args);
    if (path.endsWith("/institutions"))
      return {
        data: {
          items: [
            {
              id: "institution",
              code: "one",
              name: "First synthetic institution",
              organization_epoch: 1,
            },
            {
              id: "second",
              code: "two",
              name: "Second synthetic institution",
              organization_epoch: 1,
            },
          ],
          total: 2,
          next_cursor: null,
        },
      };
    return result;
  });
  render(<OrganizationWorkspace me={me} refreshMe={refreshMe} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Organization history" }),
  );
  await waitFor(() => expect(resolveHistory).toBeTypeOf("function"));
  fireEvent.change(screen.getByLabelText("Organization institution"), {
    target: { value: "second" },
  });
  await act(async () => {
    resolveHistory({ data: { items: [], total: 0, next_cursor: null } });
  });
  expect(
    screen.queryByRole("region", { name: "Organization history" }),
  ).toBeNull();
});
