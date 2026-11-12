import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

async function signIn(page: Page, account: string, staff = false) {
  await page.goto("/");
  await page
    .getByLabel("Synthetic email", { exact: true })
    .fill(`${account}@advisory.test`);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  if (staff)
    await page.getByRole("button", { name: "Simulate staff MFA" }).click();
  const region = page.getByRole("region", {
    name: "Student onboarding and documents",
    exact: true,
  });
  await expect(region).toBeVisible();
  return region;
}

test("student saves, resumes, reviews and completes onboarding", async ({
  page,
}) => {
  const region = await signIn(page, "student-a");
  await region
    .getByRole("combobox", {
      name: "Program (required to complete)",
      exact: true,
    })
    .selectOption("Synthetic Program");
  await region
    .getByRole("button", { name: "Save profile draft", exact: true })
    .click();
  await expect(
    region.getByText("Draft saved. You can return later.", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    region.getByRole("combobox", {
      name: "Program (required to complete)",
      exact: true,
    }),
  ).toHaveValue("Synthetic Program");
  await region
    .getByRole("combobox", {
      name: "Catalog Year (required to complete)",
      exact: true,
    })
    .selectOption("2026");
  await region
    .getByRole("button", { name: "Review profile", exact: true })
    .focus();
  await page.keyboard.press("Enter");
  await expect(
    region.getByRole("heading", { name: "Review your profile", exact: true }),
  ).toBeVisible();
  await region
    .getByLabel("I reviewed my facts and confirmed my catalog year.")
    .check();
  await region
    .getByRole("button", { name: "Confirm and complete profile", exact: true })
    .click();
  await expect(
    region.getByText("Profile setup complete.", { exact: true }),
  ).toBeVisible();
  await region
    .getByRole("button", { name: "Show profile history", exact: true })
    .click();
  await expect(
    region.getByText(/Profile revision .*complete/).first(),
  ).toBeVisible();
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
});

test("manager configures questions without overwriting existing profiles", async ({
  page,
}) => {
  const region = await signIn(page, "manager", true);
  await region
    .getByRole("button", { name: "Onboarding configuration", exact: true })
    .click();
  await expect(
    region.getByRole("heading", {
      name: "Department onboarding configuration",
    }),
  ).toBeVisible();
  const before = await (await page.request.get("/api/v1/me")).json();
  const response = await page.request.get(
    `/api/v1/departments/${before.active_scope}/onboarding-schemas`,
  );
  const version = (await response.json()).version;
  const programChoices = region
    .getByRole("group", { name: "Question 2", exact: true })
    .getByRole("textbox", {
      name: "Allowed choices (comma separated)",
      exact: true,
    });
  await programChoices.fill("Synthetic Program, Synthetic Alternate Program");
  await programChoices.press("Enter");

  await expect(
    region.getByText("Department schema saved and activated.", { exact: true }),
  ).toBeVisible();
  const after = await (
    await page.request.get(
      `/api/v1/departments/${before.active_scope}/onboarding-schemas`,
    )
  ).json();
  expect(after.version).toBe(version + 1);
  const active = after.schemas.find(
    (s: { id: string }) => s.id === after.active_schema_id,
  );
  expect(
    active.definition.fields.find((q: { key: string }) => q.key === "program")
      .choices,
  ).toContain("Synthetic Alternate Program");
});

test("advisor uploads, sees scan failure, retries and reviews real extraction", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const region = await signIn(page, "advisor-a", true);
  await expect(region.getByLabel("Academic student")).not.toHaveValue("");
  await region.getByRole("button", { name: "Documents", exact: true }).click();
  const title = `Synthetic browser evidence ${Date.now()}`;
  await region.getByLabel("Document title", { exact: true }).fill(title);
  await region
    .getByLabel("Or paste document text")
    .fill(
      "Synthetic browser document evidence. No institutional requirements.",
    );
  await region
    .getByRole("button", { name: "Submit document", exact: true })
    .click();
  await expect(
    region.getByText(
      "Document received. Processing begins when the worker is running.",
      { exact: true },
    ),
  ).toBeVisible();
  const row = region
    .locator("article")
    .filter({ has: page.getByRole("heading", { name: title, exact: true }) });
  await expect(row).toBeVisible();
  const cwd = resolve(process.cwd(), "../backend");
  const uv = process.env.UV_BIN ?? "uv";
  // Run until this new source is claimed, allowing previously queued synthetic documents.
  for (let i = 0; i < 30; i++) {
    execFileSync(uv, ["run", "python", "-m", "app.ingest_worker", "--once"], {
      cwd,
      env: {
        ...process.env,
        SCANNER_DATABASE_PATH: resolve(
          process.cwd(),
          "../local-data/unavailable-scanner-fixture",
        ),
      },
      stdio: "pipe",
      timeout: 30_000,
    });
    await page.waitForTimeout(150);
    const sources = await (
      await page.request.get("/api/v1/sources?limit=100")
    ).json();
    const source = sources.items.find(
      (s: { metadata: { title: string } }) => s.metadata.title === title,
    );
    if (source?.state === "failed") break;
  }
  await expect(row.getByText(/SCANNER|scanner unavailable/i)).toBeVisible({
    timeout: 10_000,
  });
  await row
    .getByRole("button", { name: `Retry ${title}`, exact: true })
    .click();
  await expect(
    region.getByText("Retry queued.", { exact: true }),
  ).toBeVisible();
  execFileSync(uv, ["run", "python", "-m", "app.ingest_worker", "--once"], {
    cwd,
    stdio: "pipe",
    timeout: 60_000,
  });
  await expect(row.getByText(/needs review/)).toBeVisible({ timeout: 15_000 });
  await row
    .getByRole("button", {
      name: `Review extracted text for ${title}`,
      exact: true,
    })
    .click();
  await expect(region.locator("pre")).toContainText(
    "Synthetic browser document evidence",
  );
  const data = await (
    await page.request.get("/api/v1/sources?limit=100")
  ).json();
  const source = data.items.find(
    (s: { metadata: { title: string } }) => s.metadata.title === title,
  );
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signIn(page, "student-b");
  expect(
    (await page.request.get(`/api/v1/sources/${source.id}`)).status(),
  ).toBe(404);
});

for (const width of [360, 768, 1280]) {
  test(`onboarding fits ${width}px and labels support keyboard use`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const region = await signIn(page, "student-a");
    await expect(
      region.getByRole("group", { name: "Academic facts", exact: true }),
    ).toBeVisible();
    await region
      .getByRole("button", { name: "Save profile draft", exact: true })
      .focus();
    await expect(
      region.getByRole("button", { name: "Save profile draft", exact: true }),
    ).toBeFocused();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
  });
}
