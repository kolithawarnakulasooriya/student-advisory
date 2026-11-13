import {
  expect,
  test,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
const backend = resolve(process.cwd(), "../backend");
const origin = `http://localhost:${process.env.ADVISORY_E2E_WEB_PORT ?? "3000"}`;
async function mutate(
  request: APIRequestContext,
  path: string,
  body: unknown = {},
  version?: number,
  method = "POST",
) {
  const csrf = await (await request.get("/api/v1/auth/csrf")).json();
  return request.fetch("/api/v1/" + path, {
    method,
    headers: {
      Origin: origin,
      "X-CSRF-Token": csrf.csrf_token,
      "Idempotency-Key": crypto.randomUUID(),
      ...(version === undefined ? {} : { "If-Match": `"${version}"` }),
    },
    data: body,
  });
}
async function login(page: Page, email: string, staff = false) {
  await page.goto("/");
  await page.getByLabel("Synthetic email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  if (staff)
    await page.getByRole("button", { name: "Simulate staff MFA" }).click();
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeEnabled();
  if (staff)
    await expect(
      page.getByRole("region", {
        name: "Student onboarding and documents",
        exact: true,
      }),
    ).toBeVisible();
}
function worker(module: string, sourceVersion?: string) {
  execFileSync(
    process.env.UV_BIN ?? "uv",
    [
      "run",
      "python",
      "-m",
      module,
      "--once",
      ...(sourceVersion ? ["--source-version", sourceVersion] : []),
    ],
    {
      cwd: backend,
      env: { ...process.env, INFERENCE_PROVIDER: "mock" },
      stdio: "pipe",
    },
  );
}

test("publication, cited chat, advisor guidance, private notes and durable human help", async ({
  browser,
}) => {
  test.setTimeout(360_000);
  const mc = await browser.newContext(),
    sc = await browser.newContext(),
    ac = await browser.newContext();
  const manager = await mc.newPage(),
    student = await sc.newPage(),
    advisor = await ac.newPage();
  await login(manager, "manager@advisory.test", true);
  const me = await (await manager.request.get("/api/v1/me")).json();
  const advisors = await (
    await manager.request.get(
      `/api/v1/eligible-advisors?scope_id=${me.active_scope}`,
    )
  ).json();
  const advisorGrant = advisors.items.find(
    (a: { email: string }) => a.email === "advisor-a@advisory.test",
  );
  expect(advisorGrant).toBeTruthy();
  await student.goto("/");
  const registration = await mutate(student.request, "auth/register", {
    email: `release04-${Date.now()}@advisory.test`,
    name: "Synthetic release 04 browser student",
  });
  expect(registration.status()).toBe(201);
  const challenge = (await registration.json()).simulator_challenge;
  expect(
    (await mutate(student.request, "auth/verify", { challenge })).status(),
  ).toBe(200);
  const req = await mutate(student.request, "membership-requests", {
    org_unit_id: me.active_scope,
    requested_role: "student",
    justification: "Synthetic release 04 browser fixture",
  });
  expect(req.status()).toBe(201);
  const request = await req.json();
  const approval = await mutate(
    manager.request,
    `membership-requests/${request.id}/approve`,
    {
      advisor_grant_id: advisorGrant.id,
      reason: "Synthetic browser enrollment",
    },
    request.version,
  );
  expect(approval.status()).toBe(200);
  const membership = (await (await student.request.get("/api/v1/me")).json())
    .student_memberships[0];
  const p = await (
    await student.request.get(`/api/v1/students/${membership.id}/profile`)
  ).json();
  const facts: Record<string, { value: unknown }> = {
    program: { value: "Synthetic Program" },
    catalog_year: { value: "2026" },
  };
  for (const field of p.schema.definition.fields) {
    if (field.required && !facts[field.key])
      facts[field.key] = {
        value:
          field.kind === "choice"
            ? field.choices[0]
            : field.kind === "number"
              ? 0
              : field.kind === "courses"
                ? []
                : "Synthetic response",
      };
  }
  const saved = await mutate(
    student.request,
    `students/${membership.id}/profile`,
    {
      schema_id: p.schema.id,
      status: "complete",
      catalog_confirmed: true,
      facts,
    },
    p.version,
    "PATCH",
  );
  expect(saved.status()).toBe(200);
  const title = `Synthetic published browser evidence ${Date.now()}`;
  const uploaded = await mutate(
    manager.request,
    "sources/text",
    {
      institution_id: me.scopes.find(
        (s: { id: string }) => s.id === me.active_scope,
      ).institution_id,
      org_unit_id: me.active_scope,
      student_membership_id: membership.id,
      visibility: "student",
      metadata: {
        title,
        document_class: "policy",
        program: "Synthetic Program",
        catalog_start: 2026,
        catalog_end: 2026,
      },
      text: "Synthetic browser policy: SYN301 requires SYN201. This fixture is not an institutional requirement.",
    },
    0,
  );
  expect(uploaded.status()).toBe(201);
  const source = await uploaded.json();
  for (let i = 0; i < 40; i++) {
    worker("app.ingest_worker", source.source_version_id);
    const s = await (
      await manager.request.get(`/api/v1/sources/${source.id}`)
    ).json();
    if (s.state === "needs_review") break;
    expect(["failed", "cancelled"]).not.toContain(s.state);
  }
  await manager.reload();
  const mw = manager.getByRole("region", {
    name: "Student onboarding and documents",
    exact: true,
  });
  await mw.getByLabel("Academic student").selectOption(membership.id);
  await mw.getByRole("button", { name: "Documents", exact: true }).click();
  const card = mw.locator("article.source-card").filter({
    has: manager.getByRole("heading", { name: title, exact: true }),
  });
  await expect(card).toBeVisible();
  await card
    .getByLabel("Review or publication reason")
    .fill("Reviewed synthetic fixture scope and extraction");
  await card
    .getByRole("button", { name: "Review metadata and index", exact: true })
    .click();
  for (let i = 0; i < 40; i++) {
    worker("app.advising_worker");
    const pub = await (
      await manager.request.get(`/api/v1/sources/${source.id}/publication`)
    ).json();
    if (pub.builds.some((b: { state: string }) => b.state === "ready")) break;
  }
  await expect(
    card.getByRole("button", { name: "Publish reviewed build", exact: true }),
  ).toBeVisible();
  await card
    .getByRole("button", { name: "Publish reviewed build", exact: true })
    .click();
  await expect(
    card.getByText("Reviewed evidence published.", { exact: true }),
  ).toBeVisible();
  await student.reload();
  await student
    .getByRole("button", { name: "Advising and human help", exact: true })
    .click();
  const chat = student.getByRole("region", {
    name: "Cited advising chat",
    exact: true,
  });
  await chat
    .getByRole("button", { name: "Start advising conversation" })
    .click();
  await expect(chat.getByLabel("Your academic question")).toBeVisible();
  await chat
    .getByLabel("Your academic question")
    .fill("Which prerequisite is required for SYN301?");
  await expect(
    chat.getByRole("button", { name: "Ask a question", exact: true }),
  ).toBeEnabled();
  await chat
    .getByRole("button", { name: "Ask a question", exact: true })
    .focus();
  await student.keyboard.press("Enter");
  await expect(
    chat.getByText(
      "Question received. The response is queued for validation.",
      { exact: true },
    ),
  ).toBeVisible();
  const cid = await chat.getByLabel("Advising conversation").inputValue();
  for (let i = 0; i < 40; i++) {
    worker("app.advising_worker");
    const messages = await (
      await student.request.get(`/api/v1/conversations/${cid}/messages`)
    ).json();
    if (messages.items.some((m: { answers: unknown[] }) => m.answers.length))
      break;
  }
  await expect(
    chat.getByRole("region", { name: "Validated assistant answer" }),
  ).toBeVisible();
  await chat.getByRole("button", { name: `View evidence: ${title}` }).click();
  await expect(
    chat.getByRole("complementary", { name: "Evidence drawer" }),
  ).toContainText("SYN301 requires SYN201");
  await chat.getByRole("button", { name: "Close evidence" }).click();
  await login(advisor, "advisor-a@advisory.test", true);
  const aw = advisor.getByRole("region", {
    name: "Student onboarding and documents",
    exact: true,
  });
  await aw.getByLabel("Academic student").selectOption(membership.id);
  await aw.getByRole("button", { name: "Advising and human help" }).click();
  const ach = advisor.getByRole("region", {
    name: "Cited advising chat",
    exact: true,
  });
  await ach.getByLabel("Advising conversation").selectOption(cid);
  const before = await (
    await student.request.get(`/api/v1/conversations/${cid}/messages`)
  ).json();
  await ach
    .getByRole("button", { name: "Visible advisor guidance", exact: true })
    .click();
  await ach
    .getByLabel("Visible guidance text")
    .fill("Consider a three course term.");
  await ach.getByLabel("Preferred maximum courses").fill("3");
  await ach.getByRole("button", { name: "Post advisor guidance" }).click();
  await expect(
    ach.getByText(
      "Advisor guidance saved. No assistant response was requested.",
      { exact: true },
    ),
  ).toBeVisible();
  const after = await (
    await student.request.get(`/api/v1/conversations/${cid}/messages`)
  ).json();
  expect(after).toMatchObject({ total: before.total });
  expect(after.items.map((m: { jobs: unknown[] }) => m.jobs.length)).toEqual(
    before.items.map((m: { jobs: unknown[] }) => m.jobs.length),
  );
  await ach
    .getByRole("button", { name: "Staff-only notes", exact: true })
    .click();
  await ach.getByLabel("Private staff note").fill("PRIVATE_BROWSER_NOTE_04");
  await ach.getByRole("button", { name: "Save staff-only note" }).click();
  await expect(
    ach.getByText("Private staff note saved.", { exact: true }),
  ).toBeVisible();
  await expect(
    chat.getByText("Consider a three course term.", { exact: true }),
  ).toBeVisible();
  await expect(chat.getByText("PRIVATE_BROWSER_NOTE_04")).toHaveCount(0);
  await chat
    .getByRole("button", { name: "Request human help", exact: true })
    .click();
  await expect(
    chat.getByText(/Your advisor request was received/),
  ).toBeVisible();
  for (const width of [360, 768, 1280]) {
    await student.setViewportSize({ width, height: 900 });
    expect(
      await student.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    await expect(chat.getByLabel("Your academic question")).toBeVisible();
  }
  const assignment = await (
    await manager.request.get(`/api/v1/assignment-state/${membership.id}`)
  ).json();
  const advisor2 = advisors.items.find(
    (a: { email: string }) => a.email === "advisor-a2@advisory.test",
  );
  expect(advisor2).toBeTruthy();
  const moved = await mutate(
    manager.request,
    `students/${membership.id}/advisor`,
    {
      advisor_grant_id: advisor2.id,
      reason: "Synthetic browser access-loss check",
    },
    assignment.version,
    "PUT",
  );
  expect(moved.status()).toBe(200);
  await expect(ach.getByText("PRIVATE_BROWSER_NOTE_04")).toHaveCount(0);
  expect(
    (await advisor.request.get(`/api/v1/conversations/${cid}/notes`)).status(),
  ).toBe(404);
  await mc.close();
  await sc.close();
  await ac.close();
});

test("manager evaluates and activates bounded department settings", async ({
  page,
}) => {
  await login(page, "manager@advisory.test", true);
  const region = page.getByRole("region", {
    name: "Student onboarding and documents",
    exact: true,
  });
  const loaded = page.waitForResponse(
    (r) => r.url().includes("/knowledge/state") && r.status() === 200,
  );
  await region
    .getByRole("button", { name: "Evidence rules and releases", exact: true })
    .click();
  await loaded;
  await region.getByLabel("Release kind").selectOption("preferences");
  await region.getByLabel("Advisor label").fill("Academic advisor");
  await region
    .getByRole("button", { name: "Save release draft", exact: true })
    .click();
  await expect(
    region.getByText("Immutable release saved. Evaluate before activation.", {
      exact: true,
    }),
  ).toBeVisible();
  const row = region.locator("article").first();
  await row
    .getByRole("button", { name: "Evaluate release", exact: true })
    .click();
  for (let i = 0; i < 20; i++) {
    worker("app.advising_worker");
    if (
      await row
        .getByText("Passing recorded evaluation", { exact: false })
        .count()
    )
      break;
  }
  await expect(row.getByText(/Passing recorded evaluation/)).toBeVisible();
  await region
    .getByLabel("Activation or rollback reason")
    .fill("Synthetic browser configuration review");
  await row
    .getByRole("button", { name: "Activate evaluated version", exact: true })
    .click();
  await expect(
    region.getByText("Evaluated release activated.", { exact: true }),
  ).toBeVisible();
  for (const width of [360, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
  }
});
