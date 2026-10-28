import { expect, test, type Page } from "@playwright/test";

import { registerApprovedAgency } from "./helpers/agency";

// ccrm-051 (DEC-SCOPE-327): the Overseas Admin sets a 12% agent-Master commission on a course of a university whose own rate is 10%; an
// agency Master's Partner University detail shows "12.00% (course)" for it and "10.00% (university)" for the other course. A course
// form never shares ids with the university's agent commission card. Requires the stack seeded with `python -m app.seed`. Unique names
// per run (shared E2E DB).

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
}

async function addCourse(page: Page, title: string, percent?: string) {
  await page.getByRole("button", { name: "Add course" }).click();
  const form = page.getByRole("form", { name: "New course" });
  await form.getByLabel("Course title (required)").fill(title);
  await form.getByLabel("Level (required)").selectOption("PG");
  await form.getByLabel("Category (required)").fill("Computing");
  await form.getByLabel("Duration (required)").fill("1 year");
  const commission = form.getByRole("group", { name: "Agent Master commission" });
  await expect(commission).toBeVisible();
  if (percent) await commission.getByLabel("Percent", { exact: true }).fill(percent);
  const [saved] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/courses") && r.request().method() === "POST"),
    form.getByRole("button", { name: "Save course" }).click(),
  ]);
  expect(saved.status()).toBe(201);
  await expect(page.getByRole("status").filter({ hasText: "Course added." })).toBeVisible();
}

test("a course's 12% overrides the university's 10% for the Master; the other course falls back (AC1, AC2)", async ({ page, browser }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123");
  const country = (await (await page.request.get("/api/v1/lookups/countries?q=United Kingdom")).json()).items[0].id;
  const created = await page.request.post("/api/v1/partnership/universities", {
    data: { name: `CCRM051 University ${stamp}`, country_id: country, city: "London", overview: "An e2e overview.", agent_commission: { percent: "10" } },
  });
  expect(created.status()).toBe(201);
  const uni = (await created.json()).university;

  await page.goto(`/partnership/universities/${uni.id}`);
  await addCourse(page, `MSc Own Rate ${stamp}`, "12");
  await addCourse(page, `MSc Fallback ${stamp}`);
  const courses = page.getByRole("list", { name: "Courses" });
  await expect(courses.getByRole("listitem").filter({ hasText: `MSc Own Rate ${stamp}` })).toContainText("Agent Master commission12.00%");
  await expect(courses.getByRole("listitem").filter({ hasText: `MSc Fallback ${stamp}` })).not.toContainText("Agent Master commission");

  // Edit prefills, and the open form's inputs never duplicate the card's ids.
  await courses.getByRole("button", { name: `Edit MSc Own Rate ${stamp}` }).click();
  const edit = page.getByRole("form", { name: `Edit MSc Own Rate ${stamp}` });
  await expect(edit.getByRole("group", { name: "Agent Master commission" }).getByLabel("Percent", { exact: true })).toHaveValue("12.00");
  expect(await page.evaluate(() => {
    const ids = [...document.querySelectorAll("[id]")].map((e) => e.id);
    return ids.length === new Set(ids).size;
  })).toBe(true);
  await edit.getByRole("button", { name: "Cancel" }).click();

  expect((await page.request.post(`/api/v1/partnership/universities/${uni.id}/publish`)).status()).toBe(200);
  const masterPage = await (await browser.newContext()).newPage();
  const masterEmail = await registerApprovedAgency(masterPage, stamp, "ccrm051");
  await signIn(masterPage, masterEmail, "Sup3r-Secret-Pass!");
  await masterPage.goto(`/overseas/agent/partner-universities?id=${uni.id}`);
  const row = (title: string) => masterPage.getByRole("row").filter({ hasText: title });
  await expect(masterPage.getByRole("columnheader", { name: "Agent commission" })).toBeVisible();
  await expect(row(`MSc Own Rate ${stamp}`)).toContainText("12.00% (course)");
  await expect(row(`MSc Fallback ${stamp}`)).toContainText("10.00% (university)");

  await masterPage.setViewportSize({ width: 375, height: 800 });
  await expect(row(`MSc Own Rate ${stamp}`)).toBeVisible();
  expect(await masterPage.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
