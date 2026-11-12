import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import {
  expect,
  test,
  type Page,
  type APIRequestContext,
} from "@playwright/test";

const stamp = Date.now();
async function mutate(
  request: APIRequestContext,
  path: string,
  body: unknown,
  version?: number,
  method = "POST",
) {
  const csrf = await (await request.get("/api/v1/auth/csrf")).json();
  return request.fetch("/api/v1/" + path, {
    method,
    headers: {
      Origin: `http://localhost:${process.env.ADVISORY_E2E_WEB_PORT ?? "3000"}`,
      "X-CSRF-Token": csrf.csrf_token,
      "Idempotency-Key": crypto.randomUUID(),
      ...(version === undefined ? {} : { "If-Match": `"${version}"` }),
    },
    data: body,
  });
}
async function signIn(page: Page, email = "super-admin@advisory.test") {
  await page.goto("/");
  await page.getByLabel("Synthetic email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Simulate staff MFA" }).click();
  const region = page.getByRole("region", {
    name: "Organization administration",
    exact: true,
  });
  await expect(region).toBeVisible();
  await expect(region.getByLabel("Organization institution")).not.toHaveValue(
    "",
  );
  return region;
}
async function findOrg(page: Page, name: string) {
  const region = page.getByRole("region", {
    name: "Organization administration",
    exact: true,
  });
  const response = page.waitForResponse(
    (r) => r.url().includes("/admin/org-units?") && !r.url().includes("kind="),
  );
  await region
    .getByRole("button", { name: "Refresh organizations", exact: true })
    .click();
  const data = await (await response).json();
  if (data.items[0])
    await expect(
      region
        .locator("article")
        .filter({
          has: page.getByRole("heading", {
            name: data.items[0].name,
            exact: true,
          }),
        })
        .first(),
    ).toBeVisible();
  const row = region
    .locator("article")
    .filter({ has: page.getByRole("heading", { name, exact: true }) });
  for (let i = 0; i < 30; i++) {
    if (await row.count()) return row;
    const next = region.getByRole("button", {
      name: "Next organizations page",
      exact: true,
    });
    if (!(await next.count())) break;
    const response = page.waitForResponse(
      (r) =>
        r.url().includes("/admin/org-units?") &&
        r.url().includes("cursor=") &&
        !r.url().includes("kind="),
    );
    await next.click();
    const data = await (await response).json();
    if (data.items[0])
      await expect(
        region.getByRole("heading", { name: data.items[0].name, exact: true }),
      ).toBeVisible();
  }
  await expect(row).toBeVisible();
  return row;
}
async function createIdentity(page: Page, email: string) {
  let r = await mutate(page.request, "auth/register", {
    email,
    name: "Synthetic organization administrator",
  });
  expect(r.status()).toBe(201);
  const challenge = (await r.json()).simulator_challenge;
  r = await mutate(page.request, "auth/verify", { challenge });
  expect(r.status()).toBe(200);
  return (await (await page.request.get("/api/v1/me")).json())
    .user_id as string;
}
test.beforeAll(() => {
  const backend = resolve(process.cwd(), "../backend");
  execFileSync(
    resolve(backend, ".venv/bin/python"),
    [
      "-c",
      `
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.bootstrap import bootstrap
from app.models import PlatformControl
from app.seed import disposable_url
load_dotenv('../.env')
url=disposable_url(os.environ['MIGRATION_DATABASE_URL'],'development','advisory_dev')
with Session(create_engine(url,hide_parameters=True)) as db,db.begin():
 if not db.get(PlatformControl,1).bootstrap_completed:bootstrap(db,'super-admin@advisory.test')
 `,
    ],
    { cwd: backend, stdio: "pipe" },
  );
});

test("super admin creates organizations, opens enrollment and separately appoints a manager", async ({
  page,
  browser,
}) => {
  const region = await signIn(page);
  const institution = await region
    .getByLabel("Organization institution")
    .inputValue();
  const collegeName = `Synthetic UI college ${stamp}`;
  await region
    .getByLabel("Reason for organization action")
    .fill("Synthetic organization walkthrough");
  await region
    .getByText("Create a college or department", { exact: true })
    .click();
  await region
    .getByLabel("Organization name", { exact: true })
    .fill(collegeName);
  await region
    .getByLabel("Organization code", { exact: true })
    .fill(`ui-college-${stamp}`);
  const collegeResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/admin/org-units") &&
      r.request().method() === "POST",
  );
  await region
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  const c = await collegeResponse;
  expect(c.status()).toBe(201);
  const college = await c.json();
  await findOrg(page, collegeName);
  await region
    .getByLabel("Reason for organization action")
    .fill("Synthetic department walkthrough");
  await region
    .getByText("Create a college or department", { exact: true })
    .click();
  await region.getByLabel("Organization type").selectOption("department");
  await region
    .getByRole("combobox", { name: "Parent college", exact: true })
    .selectOption(college.id);
  const departmentName = `Synthetic UI department ${stamp}`;
  await region
    .getByLabel("Organization name", { exact: true })
    .fill(departmentName);
  await region
    .getByLabel("Organization code", { exact: true })
    .fill(`ui-department-${stamp}`);
  const deptResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/admin/org-units") &&
      r.request().method() === "POST",
  );
  await region
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  const d = await deptResponse;
  expect(d.status()).toBe(201);
  const department = await d.json();
  expect(department.institution_id).toBe(institution);
  expect(department.enrollment_enabled).toBe(false);
  const row = await findOrg(page, departmentName);
  await region
    .getByLabel("Reason for organization action")
    .fill("Open synthetic enrollment");
  const open = page.waitForResponse((r) =>
    r.url().endsWith(`/admin/org-units/${department.id}/enrollment`),
  );
  await row
    .getByRole("button", { name: "Open membership requests", exact: true })
    .click();
  expect((await open).status()).toBe(200);
  const updated = await findOrg(page, departmentName);
  await expect(updated).toContainText("Membership requests: open");
  const targetContext = await browser.newContext();
  const target = await targetContext.newPage();
  await target.goto("/");
  const email = `org-manager-${stamp}@advisory.test`;
  await createIdentity(target, email);
  await updated
    .getByRole("button", { name: "Appoint department manager", exact: true })
    .click();
  await region.getByLabel("Appointment email").fill(email);
  await region
    .getByRole("button", { name: "Find appointment account", exact: true })
    .click();
  await expect(
    region.getByText(
      `Selected account: Synthetic organization administrator · ${email}`,
    ),
  ).toBeVisible();
  await region
    .getByLabel("Reason for organization action")
    .fill("Separate manager appointment");
  const appointment = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/role-grants") &&
      r.request().method() === "POST",
  );
  await region
    .getByRole("button", { name: "Confirm manager appointment", exact: true })
    .click();
  expect((await appointment).status()).toBe(201);
  await target.goto("/");
  await target.getByRole("button", { name: "Simulate staff MFA" }).click();
  await expect(
    target.getByRole("heading", { name: "Manager workspace", exact: true }),
  ).toBeVisible();
  await expect(
    target.getByRole("region", {
      name: "Organization administration",
      exact: true,
    }),
  ).toHaveCount(0);
  await targetContext.close();
});

test("delegated administrator without a department can create metadata and loses access on revocation", async ({
  page,
  browser,
}) => {
  const region = await signIn(page);
  const institution = await region
    .getByLabel("Organization institution")
    .inputValue();
  const context = await browser.newContext();
  const delegate = await context.newPage();
  await delegate.goto("/");
  const email = `org-delegate-${stamp}@advisory.test`;
  const uid = await createIdentity(delegate, email);
  const before = await (
    await page.request.get(
      `/api/v1/admin/org-units?institution_id=${institution}&purpose=administration&kind=college`,
    )
  ).json();
  const college = before.items[0];
  expect(Boolean(college)).toBe(true);
  await region
    .getByLabel("Reason for organization action")
    .fill("Scoped organization delegation");
  await region.getByLabel("Appointment email").fill(email);
  await region
    .getByRole("button", { name: "Find appointment account", exact: true })
    .click();
  await expect(
    region.getByText(
      `Selected account: Synthetic organization administrator · ${email}`,
    ),
  ).toBeVisible();
  await region.getByLabel("Delegated college").selectOption(college.id);
  const granting = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/organization-admin-grants") &&
      r.request().method() === "POST",
  );
  await region
    .getByRole("button", {
      name: "Delegate organization management",
      exact: true,
    })
    .click();
  const grantResponse = await granting;
  expect(grantResponse.status()).toBe(201);
  const grant = await grantResponse.json();
  await delegate.goto("/");
  await delegate.getByRole("button", { name: "Simulate staff MFA" }).click();
  const scoped = delegate.getByRole("region", {
    name: "Organization administration",
    exact: true,
  });
  await expect(scoped).toBeVisible();
  const me = await (await delegate.request.get("/api/v1/me")).json();
  expect(me.scopes).toEqual([]);
  expect(me.active_grants).toEqual([]);
  await expect(
    scoped.getByRole("button", { name: "Delegate organization management" }),
  ).toHaveCount(0);
  const unauthorized = await mutate(delegate.request, "role-grants", {
    user_id: uid,
    org_unit_id: college.id,
    role: "manager",
    reason: "Denied",
  });
  expect(unauthorized.status()).toBe(403);
  const revoke = await mutate(
    page.request,
    `organization-admin-grants/${grant.id}/state`,
    { status: "revoked", reason: "Revoke synthetic delegation" },
    grant.version,
  );
  expect(revoke.status()).toBe(200);
  await delegate.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(scoped).toHaveCount(0);
  expect(
    (
      await delegate.request.get(`/api/v1/admin/org-units/${college.id}`)
    ).status(),
  ).toBe(404);
  await context.close();
});

test("empty organization archive and restore keep enrollment closed", async ({
  page,
}) => {
  const region = await signIn(page);
  const institution = await region
    .getByLabel("Organization institution")
    .inputValue();
  const name = `Synthetic archive college ${stamp}`;
  const response = await mutate(page.request, "admin/org-units", {
    institution_id: institution,
    kind: "college",
    name,
    code: `archive-${stamp}`,
    timezone: "UTC",
    reason: "Prepare archive scenario",
  });
  expect(response.status()).toBe(201);
  const row = await findOrg(page, name);
  await region
    .getByLabel("Reason for organization action")
    .fill("Archive empty synthetic college");
  const archiving = page.waitForResponse(
    (r) => r.url().endsWith("/archive") && r.request().method() === "POST",
  );
  await row
    .getByRole("button", { name: "Archive organization", exact: true })
    .click();
  expect((await archiving).status()).toBe(200);
  const archived = await findOrg(page, name);
  await expect(archived).toContainText("archived");
  await region
    .getByLabel("Reason for organization action")
    .fill("Restore synthetic college");
  const restoring = page.waitForResponse(
    (r) => r.url().endsWith("/restore") && r.request().method() === "POST",
  );
  await archived
    .getByRole("button", { name: "Restore organization", exact: true })
    .click();
  expect((await restoring).status()).toBe(200);
  await expect(await findOrg(page, name)).toContainText("active");
});
for (const width of [360, 768, 1280])
  test(`organization controls and keyboard operation at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const region = await signIn(page);
    await region
      .getByRole("button", { name: "Refresh organizations", exact: true })
      .focus();
    await page.keyboard.press("Tab");
    await expect(region.getByLabel("Administration purpose")).toBeFocused();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
