import { expect, test, type Page } from "@playwright/test";

// nehn-036 (DEC-SCOPE-284): a super admin picks the Law icon for one course in the course form and leaves another on Automatic ("Data
// Science"). Both show their icon on the university's course list and the Courses & Programs table, and -- once published -- on the public
// university page, on desktop and on a phone (no sideways scroll). The university and second course come from the real API.

async function signIn(page: Page) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const iconIn = (scope: ReturnType<Page["locator"]>) => scope.locator("svg.course-icon").first();

test("a chosen course icon and the automatic subject icon show in the master, the menu and the public page", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await signIn(page);
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const created = await page.request.post("/api/v1/partnership/universities", { data: { name: `E2E Icon University ${stamp}`, country_id: countries.items[0].id, city: "Leeds", overview: "A partner." } });
  expect(created.ok(), await created.text()).toBe(true);
  const { university } = await created.json();
  const auto = await page.request.post(`/api/v1/partnership/universities/${university.id}/courses`, { data: { title: "MSc Data Science", level: "PG", category: "Data Science", duration: "1 year" } });
  expect(auto.ok(), await auto.text()).toBe(true);

  await page.goto(`/partnership/universities/${university.id}`);
  const section = page.getByRole("region", { name: "Courses & programmes" });
  await section.getByRole("button", { name: "Add course" }).click();
  const form = section.getByRole("form", { name: "New course" });
  await form.getByLabel("Course title (required)").fill("LLM International Law");
  await form.getByLabel("Level (required)").selectOption("PG");
  await form.getByLabel("Category (required)").fill("Computer Science");
  await expect(iconIn(form)).toHaveAttribute("data-icon", "computing"); // Automatic previews the subject icon
  await form.getByLabel("Icon").selectOption("law");
  await expect(iconIn(form)).toHaveAttribute("data-icon", "law");
  await form.getByLabel("Duration (required)").fill("1 year");
  await form.getByRole("button", { name: "Save course" }).click();
  await expect(section.getByRole("status")).toHaveText("Course added.");
  await expect(iconIn(section.getByRole("listitem").filter({ hasText: "LLM International Law" }))).toHaveAttribute("data-icon", "law");
  await expect(iconIn(section.getByRole("listitem").filter({ hasText: "MSc Data Science" }))).toHaveAttribute("data-icon", "data");

  await page.goto(`/partnership/courses?q=${encodeURIComponent(university.university_code)}`);
  await expect(iconIn(page.getByRole("row").filter({ hasText: "LLM International Law" }))).toHaveAttribute("data-icon", "law");
  await expect(iconIn(page.getByRole("row").filter({ hasText: "MSc Data Science" }))).toHaveAttribute("data-icon", "data");

  const publish = await page.request.post(`/api/v1/partnership/universities/${university.id}/publish`);
  expect(publish.ok(), await publish.text()).toBe(true);
  await page.request.post("/api/v1/auth/logout"); // the public viewer (the signed-in public header overflows on its own -- not this feature)
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto(`/overseas/universities/${university.slug}`);
    const card = (title: string) => page.locator(".card").filter({ has: page.getByRole("heading", { name: title }) });
    await expect(iconIn(card("LLM International Law"))).toHaveAttribute("data-icon", "law");
    await expect(iconIn(card("MSc Data Science"))).toHaveAttribute("data-icon", "data");
    await expect(iconIn(card("MSc Data Science"))).toBeVisible();
    expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  }
});
