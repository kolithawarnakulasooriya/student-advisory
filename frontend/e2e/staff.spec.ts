import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const backend = resolve(process.cwd(), "../backend");
const python = resolve(backend, ".venv/bin/python");
const stamp = Date.now();
async function signIn(page: Page, email: string, staff = false) {
  await page.goto("/");
  await page.getByLabel("Synthetic email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  if (staff)
    await page.getByRole("button", { name: "Simulate staff MFA" }).click();
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Membership and staff workflows" }),
  ).toBeVisible();
}
async function register(page: Page, email: string, navigate = true) {
  if (navigate) await page.goto("/");
  await page
    .getByRole("button", { name: "Create a new synthetic account" })
    .click();
  await page.getByLabel("Display name").fill("Synthetic workflow participant");
  await page.getByLabel("Synthetic email", { exact: true }).fill(email);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Verify synthetic email", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Membership and staff workflows" }),
  ).toBeVisible();
}
async function requestMembership(page: Page, role = "student") {
  await page.getByText("Request a membership", { exact: true }).click();
  await page
    .getByLabel("Requested department")
    .selectOption({ label: "Synthetic Department A" });
  await page.getByLabel("Requested role").selectOption(role);
  await page.getByLabel("Justification").fill("Synthetic workflow test");
  await page.getByRole("button", { name: "Submit membership request" }).click();
  await expect(
    page.getByText("Saved. Permissions and state were checked by the server.", {
      exact: true,
    }),
  ).toBeVisible();
}
async function chooseAdvisor(page: Page, email = "advisor-a@advisory.test") {
  const me = await (
    await page.request.get("/api/v1/me?purpose=administration")
  ).json();
  const list = await (
    await page.request.get(
      `/api/v1/eligible-advisors?scope_id=${me.active_scope}&purpose=administration`,
    )
  ).json();
  const selected = list.items.find((a: { email: string }) => a.email === email);
  expect(Boolean(selected)).toBe(true);
  await page
    .getByRole("combobox", { name: "Primary advisor", exact: true })
    .selectOption(selected.id);
}
async function findRow(page: Page, email: string, endpoint: string) {
  const response = page.waitForResponse(
    (r) => r.url().includes(endpoint) && r.request().method() === "GET",
  );
  await page
    .getByRole("button", { name: "Refresh workflow", exact: true })
    .click();
  const first = await (await response).json();
  await expect(
    page.getByText(
      `Showing ${first.items.length} of ${first.total} authorized items.`,
      { exact: true },
    ),
  ).toBeVisible();
  const row = page.locator("article").filter({ hasText: email });
  for (let i = 0; i < 20; i++) {
    if (await row.count()) return row;
    const next = page.getByRole("button", { name: "Next page", exact: true });
    if (!(await next.count())) break;
    const response = page.waitForResponse(
      (r) => r.url().includes(endpoint) && r.url().includes("cursor="),
    );
    await next.click();
    const data = await (await response).json();
    if (data.items[0]?.email)
      await expect(
        page
          .locator("article")
          .filter({ hasText: data.items[0].email })
          .first(),
      ).toBeVisible();
  }
  await expect(row).toBeVisible();
  return row;
}

async function approveStudent(page: Page, email: string) {
  await chooseAdvisor(page);
  await page
    .getByLabel("Reason for staff action")
    .fill("Synthetic enrollment approval");
  const row = await findRow(page, email, "/membership-requests");
  await row
    .getByRole("button", { name: "Approve student", exact: true })
    .click();
  await expect(
    page.getByText("Saved. Permissions and state were checked by the server.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    await findRow(page, email, "/membership-requests"),
  ).toContainText("approved");
}

test.beforeAll(() => {
  // Explicit disposable operator fixture step, never a migration or HTTP bootstrap bypass.
  execFileSync(
    python,
    [
      "-c",
      `
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.seed import disposable_url
from app.bootstrap import bootstrap
from app.models import PlatformControl
load_dotenv('../.env')
url=disposable_url(os.environ['MIGRATION_DATABASE_URL'],'development','advisory_dev')
with Session(create_engine(url,hide_parameters=True)) as db,db.begin():
 if not db.get(PlatformControl,1).bootstrap_completed:
  bootstrap(db,'super-admin@advisory.test')
`,
    ],
    { cwd: backend, stdio: "pipe" },
  );
});

test("student requests and manager activates with an advisor", async ({
  browser,
}) => {
  const studentContext = await browser.newContext();
  const managerContext = await browser.newContext();
  const student = await studentContext.newPage();
  const manager = await managerContext.newPage();
  const email = `browser-request-${stamp}@advisory.test`;
  await register(student, email);
  await requestMembership(student);
  await signIn(manager, "manager@advisory.test", true);
  await approveStudent(manager, email);
  await student.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    student.getByRole("heading", { name: "Student workspace", exact: true }),
  ).toBeVisible();
  await expect(
    student.getByText("Synthetic advisor-a", { exact: false }),
  ).toBeVisible();
  await studentContext.close();
  await managerContext.close();
});

test("invitation travels through Mailpit and is accepted by a verified identity", async ({
  browser,
  request,
}) => {
  const managerContext = await browser.newContext();
  const recipientContext = await browser.newContext();
  const manager = await managerContext.newPage();
  const recipient = await recipientContext.newPage();
  const email = `browser-invite-${stamp}@advisory.test`;
  await signIn(manager, "manager@advisory.test", true);
  await manager
    .getByRole("button", { name: "Invitations", exact: true })
    .click();
  await manager.getByLabel("Invitation email").fill(email);
  await chooseAdvisor(manager);
  await manager.getByRole("button", { name: "Send local invitation" }).click();
  await expect(
    manager.locator("article").filter({ hasText: email }),
  ).toContainText("pending");
  execFileSync(python, ["-m", "app.mail_worker", "--once"], {
    cwd: backend,
    stdio: "pipe",
  });
  const messages = await (
    await request.get("http://127.0.0.1:8025/api/v1/messages")
  ).json();
  const message = messages.messages.find((m: { To: { Address: string }[] }) =>
    m.To.some((to) => to.Address === email),
  );
  expect(Boolean(message)).toBe(true);
  const detail = await (
    await request.get(`http://127.0.0.1:8025/api/v1/message/${message.ID}`)
  ).json();
  const url = detail.Text.match(
    /http:\/\/localhost:3000\/#invitation=\S+/,
  )?.[0];
  expect(Boolean(url)).toBe(true);
  const token = url.split("#invitation=")[1];
  const urls: string[] = [];
  recipient.on("request", (r) => urls.push(r.url()));
  await recipient.goto(url);
  await register(recipient, email, false);
  await recipient
    .getByRole("button", { name: "Accept invitation", exact: true })
    .click();
  await expect(
    recipient.getByRole("heading", { name: "Student workspace", exact: true }),
  ).toBeVisible();
  expect(
    await recipient.evaluate(
      () =>
        location.hash === "" &&
        localStorage.length === 0 &&
        sessionStorage.length === 0,
    ),
  ).toBe(true);
  expect(urls.every((url) => !url.includes(token))).toBe(true);
  expect(
    await recipient
      .locator("body")
      .evaluate(
        (element, token) => !element.textContent?.includes(token),
        token,
      ),
  ).toBe(true);
  await managerContext.close();
  await recipientContext.close();
});

test("secretary sees enrollment metadata and no student records", async ({
  page,
}) => {
  await signIn(page, "secretary@advisory.test", true);
  await page.getByRole("button", { name: "Memberships", exact: true }).click();
  await expect(
    page.getByText(
      "Enrollment metadata only. Secretary permissions do not include student records.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Students", exact: true }),
  ).toHaveCount(0);
  const me = await (await page.request.get("/api/v1/me")).json();
  const members = await (
    await page.request.get(
      `/api/v1/memberships?scope_id=${me.active_scope}&limit=100`,
    )
  ).json();
  const target = members.items.find(
    (m: { email: string }) => m.email === "student-a@advisory.test",
  );
  expect(
    (
      await page.request.get(`/api/v1/students/${target.student_membership_id}`)
    ).status(),
  ).toBe(404);
});

test("reassignment clears an open former-advisor roster", async ({
  browser,
}) => {
  const managerContext = await browser.newContext();
  const advisorContext = await browser.newContext();
  const manager = await managerContext.newPage();
  const advisor = await advisorContext.newPage();
  await signIn(manager, "manager@advisory.test", true);
  const mgrMe = await (await manager.request.get("/api/v1/me")).json();
  const members = await (
    await manager.request.get(
      `/api/v1/memberships?scope_id=${mgrMe.active_scope}&limit=100`,
    )
  ).json();
  const target = members.items.find(
    (m: { email: string }) => m.email === "student-a@advisory.test",
  );
  const eligible = await (
    await manager.request.get(
      `/api/v1/eligible-advisors?scope_id=${mgrMe.active_scope}`,
    )
  ).json();
  const initialAdvisor = eligible.items.find(
    (a: { email: string }) => a.email === "advisor-a@advisory.test",
  );
  const state = await (
    await manager.request.get(
      `/api/v1/assignment-state/${target.student_membership_id}`,
    )
  ).json();
  const csrf = await (await manager.request.get("/api/v1/auth/csrf")).json();
  const reset = await manager.request.put(
    `/api/v1/students/${target.student_membership_id}/advisor`,
    {
      headers: {
        Origin: `http://localhost:${process.env.ADVISORY_E2E_WEB_PORT ?? "3000"}`,
        "X-CSRF-Token": csrf.csrf_token,
        "Idempotency-Key": crypto.randomUUID(),
        "If-Match": `"${state.version}"`,
      },
      data: {
        advisor_grant_id: initialAdvisor.id,
        reason: "Prepare synthetic reassignment scenario",
      },
    },
  );
  expect(reset.status()).toBe(200);
  await signIn(advisor, "advisor-a@advisory.test", true);
  await expect(
    await findRow(advisor, "student-a@advisory.test", "/students"),
  ).toBeVisible();
  await manager
    .getByRole("button", { name: "Memberships", exact: true })
    .click();
  await chooseAdvisor(manager, "advisor-a2@advisory.test");
  await manager
    .getByLabel("Reason for staff action")
    .fill("Synthetic reassignment");
  const row = await findRow(manager, "student-a@advisory.test", "/memberships");
  await row.getByRole("button", { name: "Assign selected advisor" }).click();
  await expect(
    manager.getByText(
      "Saved. Permissions and state were checked by the server.",
      { exact: true },
    ),
  ).toBeVisible();
  const updated = await findRow(
    manager,
    "student-a@advisory.test",
    "/memberships",
  );
  await expect(updated).toContainText("Synthetic advisor-a2");
  expect(
    (
      await advisor.request.get(
        `/api/v1/students/${target.student_membership_id}`,
      )
    ).status(),
  ).toBe(404);
  await advisor.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    advisor.getByText("student-a@advisory.test", { exact: true }),
  ).toHaveCount(0);
  await managerContext.close();
  await advisorContext.close();
});

test("manager request needs a platform super-admin decision", async ({
  browser,
}) => {
  const applicantContext = await browser.newContext();
  const adminContext = await browser.newContext();
  const applicant = await applicantContext.newPage();
  const admin = await adminContext.newPage();
  const email = `browser-manager-${stamp}@advisory.test`;
  await register(applicant, email);
  await requestMembership(applicant, "manager");
  await signIn(admin, "super-admin@advisory.test", true);
  await admin
    .getByLabel("Reason for staff action")
    .fill("Synthetic manager appointment");
  const row = await findRow(admin, email, "/membership-requests");
  await row
    .getByRole("button", { name: "Approve manager", exact: true })
    .click();
  await expect(
    admin.getByText(
      "Saved. Permissions and state were checked by the server.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    await findRow(admin, email, "/membership-requests"),
  ).toContainText("approved");
  await applicant.evaluate(() => window.dispatchEvent(new Event("focus")));
  await applicant.getByRole("button", { name: "Simulate staff MFA" }).click();
  await expect(
    applicant.getByRole("heading", { name: "Manager workspace", exact: true }),
  ).toBeVisible();
  await applicantContext.close();
  await adminContext.close();
});

for (const width of [360, 768, 1280]) {
  test(`staff controls and keyboard access at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await signIn(page, "secretary@advisory.test", true);
    const tab = page.getByRole("button", { name: "Memberships", exact: true });
    await tab.focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByText(
        "Enrollment metadata only. Secretary permissions do not include student records.",
      ),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}

test("account suspension invalidates an open session and reactivation restores no grants", async ({
  browser,
}) => {
  const studentContext = await browser.newContext();
  const managerContext = await browser.newContext();
  const adminContext = await browser.newContext();
  const student = await studentContext.newPage();
  const manager = await managerContext.newPage();
  const admin = await adminContext.newPage();
  const email = `browser-suspend-${stamp}@advisory.test`;
  await register(student, email);
  await requestMembership(student);
  await signIn(manager, "manager@advisory.test", true);
  await approveStudent(manager, email);
  await student.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    student.getByRole("heading", { name: "Student workspace", exact: true }),
  ).toBeVisible();
  await signIn(admin, "super-admin@advisory.test", true);
  await admin.getByRole("button", { name: "Users", exact: true }).click();
  await admin.getByLabel("Search exact verified email").fill(email);
  const row = admin.locator("article").filter({ hasText: email });
  await expect(row).toBeVisible();
  await admin
    .getByLabel("Reason for staff action")
    .fill("Synthetic account security review");
  await row
    .getByRole("button", { name: "Suspend account", exact: true })
    .click();
  await expect(
    row.getByRole("button", { name: "Reactivate account only", exact: true }),
  ).toBeVisible();
  expect((await student.request.get("/api/v1/me")).status()).toBe(401);
  await student.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    student.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await row
    .getByRole("button", { name: "Reactivate account only", exact: true })
    .click();
  await expect(
    row.getByRole("button", { name: "Suspend account", exact: true }),
  ).toBeVisible();
  expect((await student.request.get("/api/v1/me")).status()).toBe(401);
  await signIn(student, email);
  await expect(
    student.getByText("Awaiting membership", { exact: true }),
  ).toBeVisible();
  const me = await (await student.request.get("/api/v1/me")).json();
  expect(me.active_grants).toEqual([]);
  expect(
    me.memberships.every((g: { status: string }) => g.status === "suspended"),
  ).toBe(true);
  await studentContext.close();
  await managerContext.close();
  await adminContext.close();
});
