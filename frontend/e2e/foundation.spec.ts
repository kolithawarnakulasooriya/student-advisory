import { expect, test, type Page } from "@playwright/test";
async function signIn(page: Page, account: string, staff = false) {
  await page.goto("/");
  await page
    .getByLabel("Synthetic email", { exact: true })
    .fill(`${account}@advisory.test`);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  if (staff)
    await page.getByRole("button", { name: "Simulate staff MFA" }).click();
}
for (const [account, role] of [
  ["student-a", "Student"],
  ["advisor-a", "Advisor"],
  ["secretary", "Secretary"],
  ["manager", "Manager"],
  ["platform-admin", "Platform Admin"],
  ["super-admin", "Super Admin"],
]) {
  test(`${role} signs in and out`, async ({ page, context }) => {
    await signIn(page, account, account !== "student-a");
    await expect(
      page.getByRole("heading", { name: `${role} workspace`, exact: true }),
    ).toBeVisible();
    const cookies = await context.cookies();
    expect(
      cookies.find((c) => c.name === "advisory_session")?.httpOnly,
    ).toBeTruthy();
    expect(
      await page.evaluate(() => [localStorage.length, sessionStorage.length]),
    ).toEqual([0, 0]);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(
      page.getByRole("button", { name: "Sign in", exact: true }),
    ).toBeVisible();
    expect((await page.request.get("/api/v1/me")).status()).toBe(401);
  });
}
test("new account verifies without receiving a role", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Create a new synthetic account" })
    .click();
  await page.getByLabel("Display name").fill("Synthetic browser account");
  await page
    .getByLabel("Synthetic email", { exact: true })
    .fill(`browser-${Date.now()}@advisory.test`);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Verify your synthetic email" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Verify synthetic email", exact: true })
    .click();
  await expect(
    page.getByText("Awaiting membership", { exact: true }),
  ).toBeVisible();
  expect(
    (await (await page.request.get("/api/v1/me")).json()).active_grants,
  ).toEqual([]);
});
test("predefined identities reflect current membership state and recover", async ({
  page,
}) => {
  await signIn(page, "pending");
  // Operator walkthroughs can approve this persistent development fixture.
  // Deterministic pending-state denial remains covered in isolated DB/component tests.
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
  const pending = await (await page.request.get("/api/v1/me")).json();
  if (pending.membership_state === "pending") {
    await expect(
      page.getByText("Pending approval", { exact: true }),
    ).toBeVisible();
  } else if (pending.membership_state === "active") {
    await expect(
      page.getByRole("heading", { name: "Student workspace", exact: true }),
    ).toBeVisible();
  } else {
    await expect(
      page.getByText("Awaiting membership", { exact: true }),
    ).toBeVisible();
  }
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await signIn(page, "unverified");
  await expect(
    page.getByRole("heading", { name: "Verify your synthetic email" }),
  ).toBeVisible();
});
test("multi-scope roles switch without mixing workspaces", async ({ page }) => {
  await signIn(page, "multi-role", true);
  await expect(
    page.getByRole("heading", { name: "Advisor workspace", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Active department")
    .selectOption({ label: "Synthetic Department B" });
  await expect(
    page.getByRole("heading", { name: "Manager workspace", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Advisor workspace", exact: true }),
  ).toHaveCount(0);
});
test("expired session removes protected UI and offers sign-in", async ({
  page,
}) => {
  await signIn(page, "student-a");
  await expect(
    page.getByRole("heading", { name: "Student workspace", exact: true }),
  ).toBeVisible();
  await page.route("**/api/v1/me*", (route) =>
    route.fulfill({
      status: 401,
      json: {
        code: "SESSION_EXPIRED",
        message: "Your session expired. Sign in again.",
        field_errors: [],
        correlation_id: "synthetic",
      },
    }),
  );
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    page.getByRole("alert", { name: "Account error" }),
  ).toContainText("Your session expired");
  await expect(
    page.getByRole("heading", { name: "Student workspace", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
});
test("backend failure is recoverable", async ({ page }) => {
  await page.route("**/api/v1/me*", (route) => route.abort());
  await page.goto("/");
  await expect(
    page.getByRole("alert", { name: "Account error" }),
  ).toContainText("Cannot connect");
  await expect(
    page.getByRole("button", { name: "Retry connection" }),
  ).toBeVisible();
});
for (const width of [360, 768, 1280]) {
  test(`keyboard and layout at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: "Sign in", exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("link", { name: "Skip to content" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main")).toBeInViewport();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .getByLabel("Synthetic email", { exact: true })
      .fill("student-a@advisory.test");
    await page.getByLabel("Synthetic email", { exact: true }).press("Enter");
    await expect(
      page.getByRole("heading", { name: "Student workspace", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}
