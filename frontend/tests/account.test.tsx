import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "../app/page";
import { ApiError, get, post, type Me } from "../lib/api";
vi.mock("../lib/api", async (original) => ({
  ...(await original<typeof import("../lib/api")>()),
  get: vi.fn(),
  post: vi.fn(),
}));
const getMock = vi.mocked(get);
const postMock = vi.mocked(post);
function actor(overrides: Partial<Me> = {}): Me {
  return {
    user_id: "user-a",
    email: "student-a@advisory.test",
    name: "Synthetic Student",
    verified: true,
    account_state: "active",
    membership_state: "active",
    mfa_required: false,
    recent_auth: true,
    grant_epoch: 1,
    active_scope: "dept-a",
    active_grants: [
      {
        id: "grant",
        institution_id: "institution",
        org_unit_id: "dept-a",
        role: "student",
        status: "active",
      },
    ],
    memberships: [],
    capabilities: ["org.read", "workspace.view"],
    scopes: [
      {
        id: "dept-a",
        institution_id: "institution",
        name: "Synthetic Department A",
        kind: "department",
        timezone: "UTC",
      },
    ],
    expires_at: "2026-11-12T00:00:00Z",
    identity_mode: "synthetic",
    ...overrides,
  };
}
beforeEach(() => {
  vi.resetAllMocks();
});
describe("account journeys", () => {
  it("drops a revoked scope and resolves the remaining memberships", async () => {
    getMock
      .mockResolvedValueOnce(actor())
      .mockRejectedValueOnce(
        new ApiError(404, "NOT_FOUND", "Resource not found."),
      )
      .mockResolvedValue(
        actor({
          membership_state: "awaiting_membership",
          active_scope: null,
          active_grants: [],
          scopes: [],
          capabilities: [],
        }),
      );
    render(<Home />);
    await screen.findByRole("heading", { name: "Student workspace" });
    fireEvent.focus(window);
    expect(await screen.findByText("Awaiting membership")).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Student workspace" }),
    ).toBeNull();
  });

  it("shows a recoverable signed-out state", async () => {
    getMock.mockRejectedValue(
      new ApiError(401, "SESSION_REQUIRED", "Sign in to continue."),
    );
    render(<Home />);
    expect(
      await screen.findByRole("button", { name: "Sign in" }),
    ).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "Create a new synthetic account" }),
    );
    expect(screen.getByLabelText("Display name")).toBeRequired();
  });
  it("uses server-derived role and active scope", async () => {
    getMock.mockResolvedValue(actor());
    render(<Home />);
    expect(
      await screen.findByRole("heading", { name: "Student workspace" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Active department")).toHaveValue("dept-a");
    expect(
      screen.queryByRole("heading", { name: "Manager workspace" }),
    ).toBeNull();
  });
  it("keeps pending identities out of role workspaces", async () => {
    getMock.mockResolvedValue(
      actor({
        membership_state: "pending",
        active_grants: [],
        scopes: [],
        active_scope: null,
        capabilities: [],
      }),
    );
    render(<Home />);
    expect(await screen.findByText("Pending approval")).toBeVisible();
    expect(screen.queryByLabelText("Active department")).toBeNull();
  });
  it("clears the workspace when the session expires", async () => {
    getMock
      .mockResolvedValueOnce(actor())
      .mockRejectedValue(
        new ApiError(
          401,
          "SESSION_EXPIRED",
          "Your session expired. Sign in again.",
        ),
      );
    render(<Home />);
    await screen.findByRole("heading", { name: "Student workspace" });
    fireEvent.focus(window);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your session expired",
    );
    expect(
      screen.queryByRole("heading", { name: "Student workspace" }),
    ).toBeNull();
  });
  it("requires explicit staff MFA and verifies server state afterwards", async () => {
    getMock
      .mockResolvedValueOnce(
        actor({ mfa_required: true, scopes: [], capabilities: [] }),
      )
      .mockResolvedValue(actor());
    postMock.mockResolvedValue({ status: "done" });
    render(<Home />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Simulate staff MFA" }),
    );
    await screen.findByRole("heading", { name: "Student workspace" });
    expect(postMock).toHaveBeenCalledWith("/api/v1/auth/simulator/step-up");
  });
  it("clears scoped data after confirmed logout", async () => {
    getMock.mockResolvedValue(actor());
    postMock.mockResolvedValue({ status: "done" });
    render(<Home />);
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "You have signed out",
    );
    expect(screen.queryByText("student-a@advisory.test")).toBeNull();
  });
  it("shows connection recovery without retaining the protected workspace", async () => {
    getMock.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<Home />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Cannot connect",
    );
    expect(
      screen.getByRole("button", { name: "Retry connection" }),
    ).toBeVisible();
  });
});
