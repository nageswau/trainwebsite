import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-017 (AC1, AC3, P1, N1, E1, U2): the owning partnership manager adds "MSc Cyber Security, PG, 1 yr, Sep/Jan, £18,000, IELTS 6.5"
// with a commission from the university page, imports two more from a CSV, sees them on the Courses & Programs menu and deactivates one.
// An overseas_admin opening the same university sees the courses but no commission anywhere; once the university is published, the public
// catalogue lists only its active courses. The pages fit a phone. Throwaway accounts via the real admin API.

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc017-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc017-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U17-${stamp}`, reporting_head_user_id: head.id },
  });
  const admin = await post("/api/v1/admin/users", { role: "overseas_admin", division: "overseas", full_name: `E2E Overseas Admin ${stamp}`, email: `upc017-a-${stamp}@example.local` });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Course University ${stamp}`, country_id: countries.items[0].id, city: "London", overview: "A partner." });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [head, manager, admin]) await activateWithToken(page.request, user.development_welcome_token);
  return { manager, admin, university };
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("a manager maintains a university's courses; commission stays restricted; the catalogue shows active courses", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { manager, admin, university } = await setUp(page, stamp);
  const universityPage = `/partnership/universities/${university.id}`;
  const section = page.getByRole("region", { name: "Courses & programmes" });

  // P1 + AC1 + N1: the owning manager adds the backlog's course (validation first).
  await signIn(page, "/overseas/login", manager.email);
  await page.goto(universityPage);
  await expect(section.getByText("No courses recorded yet.")).toBeVisible();
  await section.getByRole("button", { name: "Add course" }).click();
  const form = section.getByRole("form", { name: "New course" });
  await form.getByLabel("Course title (required)").fill("MSc Cyber Security");
  await form.getByLabel("Level (required)").selectOption("PG");
  await form.getByLabel("Category (required)").fill("Computer Science");
  await form.getByLabel("Duration (required)").fill("1 year");
  await form.getByLabel("Sep", { exact: true }).check();
  await form.getByLabel("Jan", { exact: true }).check();
  await form.getByLabel("Tuition fee").fill("-18000");
  await form.getByLabel("Tuition currency").selectOption("GBP");
  await form.getByRole("button", { name: "Save course" }).click();
  await expect(form.locator(".form-error[role=alert]")).toHaveText("The tuition fee cannot be negative.");
  await form.getByLabel("Tuition fee").fill("18000");
  await form.getByLabel("English test").selectOption("IELTS");
  await form.getByLabel("Minimum score").fill("6.5");
  await form.getByLabel("Percentage").check();
  await form.getByLabel("Commission %").fill("12.5");
  await form.getByRole("button", { name: "Save course" }).click();
  await expect(section.locator("p[role=status]")).toHaveText("Course added.");
  const cyber = section.getByRole("listitem").filter({ hasText: "MSc Cyber Security" });
  for (const text of ["Jan, Sep", "GBP 18,000", "IELTS 6.5", "12.5%"]) await expect(cyber.getByText(text, { exact: true })).toBeVisible();

  // Q-21: two more from a CSV; a repeat of the first is reported as a duplicate.
  await section.getByRole("button", { name: "Import courses (CSV)" }).click();
  const csv = ["title,level,category,duration,intakes,tuition_amount,tuition_currency", "MBA,PG,Business,1 year,Sep,30000,GBP",
    "BSc Nursing,UG,Health,3 years,Sep;Jan,,", "MSc Cyber Security,PG,Computer Science,1 year,,,"].join("\n");
  await section.getByLabel("CSV file").setInputFiles({ name: "courses.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await section.getByRole("button", { name: "Import", exact: true }).click();
  await expect(section.getByText("2 added, 1 duplicate, 0 invalid.")).toBeVisible();
  await expect(section.getByRole("table", { name: "Rows not added" })).toContainText("already has a course with this title");
  await expect(section.getByRole("listitem").filter({ hasText: "BSc Nursing" })).toBeVisible();

  // E1: deactivating keeps the course in the master, marked inactive.
  await section.getByRole("button", { name: "Edit MBA" }).click();
  await section.getByRole("form", { name: "Edit MBA" }).getByLabel("Offered (active)").uncheck();
  await section.getByRole("form", { name: "Edit MBA" }).getByRole("button", { name: "Save course" }).click();
  await expect(section.locator("p[role=status]")).toHaveText("Course updated.");
  await expect(section.getByRole("listitem").filter({ hasText: "MBA" }).getByText("Inactive", { exact: true })).toBeVisible();

  // CO15: the menu page, filtered by this university, with the restricted column for the manager.
  await page.goto(`/partnership/courses?q=${encodeURIComponent(university.university_code)}`);
  const table = page.getByRole("region", { name: "Courses" });
  await expect(table.getByRole("row")).toHaveCount(3); // header + the two active courses
  await expect(table.getByRole("columnheader", { name: "Commission" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  await page.goto(universityPage);
  expect(await noSideScroll(page)).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 1280, height: 900 });

  // U2: an overseas_admin maintains courses but sees no commission anywhere.
  await signIn(page, "/overseas/login", admin.email);
  await page.goto(universityPage);
  await expect(section.getByRole("listitem").filter({ hasText: "MSc Cyber Security" })).toBeVisible();
  await expect(section.getByText(/commission/i)).toHaveCount(0);
  await section.getByRole("button", { name: "Edit MSc Cyber Security" }).click();
  await expect(section.getByRole("form", { name: "Edit MSc Cyber Security" }).getByText(/commission/i)).toHaveCount(0);
  await page.goto(`/partnership/courses?q=${encodeURIComponent(university.university_code)}`);
  await expect(page.getByRole("columnheader", { name: "Commission" })).toHaveCount(0);
  expect(await page.content()).not.toContain("12.5%");

  // AC3: published, the catalogue lists the active courses only, without commission.
  const publish = await page.request.post(`/api/v1/partnership/universities/${university.id}/publish`);
  expect(publish.ok(), await publish.text()).toBe(true);
  const catalogue = await page.request.get(`/api/v1/public/universities/${university.slug}`);
  const titles = (await catalogue.json()).courses.map((c: { title: string }) => c.title).sort();
  expect(titles).toEqual(["BSc Nursing", "MSc Cyber Security"]);
  expect(await catalogue.text()).not.toContain("commission");
});
