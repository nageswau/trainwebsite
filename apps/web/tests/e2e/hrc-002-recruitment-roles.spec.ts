import { expect, test, type Page } from "@playwright/test";

// hrc-002 (DEC-SCOPE-374): each recruitment role signs in at /it and lands on its own read-only dashboard (AC1); an interviewer is
// refused the candidate search (the - scenario); a super admin grants jobs.approve to the HR Manager on the permission screen (AC2,
// the + scenario) and the test restores it. Seeded demo accounts.
const PORTALS = [
  { email: "hr.manager@edusphere.local", path: "/it/hr-manager/dashboard", heading: "HR Manager Dashboard" },
  { email: "placement.officer@edusphere.local", path: "/it/placement-officer/dashboard", heading: "Placement Officer Dashboard" },
  { email: "interviewer@edusphere.local", path: "/it/interviewer/dashboard", heading: "Interviewer Dashboard" },
];
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string, division = "it") {
  await page.goto(`/${division === "global" ? "admin" : division}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

for (const portal of PORTALS) {
  test(`${portal.heading}: signs in at /it and lands on its own dashboard`, async ({ page }) => {
    await signIn(page, portal.email);
    await expect(page).toHaveURL(new RegExp(`${portal.path}$`));
    await expect(page.getByRole("heading", { name: portal.heading })).toBeVisible();
    await expect(page.getByRole("link", { name: "Dashboard" }).first()).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await noSideScroll(page)).toBe(true);
  });
}

test("the Placement Officer sees open requirements by Job ID; the interviewer sees none", async ({ page }) => {
  await signIn(page, "placement.officer@edusphere.local");
  await expect(page.getByRole("columnheader", { name: "Job ID" })).toBeVisible();
  await expect(page.getByRole("cell", { name: /^REQ-\d{6}$/ }).first()).toBeVisible();
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "interviewer@edusphere.local");
  await expect(page.getByText("No interviews are assigned to you yet.")).toBeVisible();
  await expect(page.getByRole("cell", { name: /^REQ-/ })).toHaveCount(0);
  await expect(page.getByText("No records yet")).toHaveCount(0); // QA-02: no empty table promising an action that does not exist
});

test("an IT admin is not offered the HR Manager role (QA-01)", async ({ page }) => {
  await signIn(page, "itadmin@edusphere.local");
  await page.goto("/it/admin/users");
  const role = page.getByLabel("Role", { exact: true });
  await expect(role.locator("option[value='placement_officer']")).toHaveCount(1);
  await expect(role.locator("option[value='hr_manager']")).toHaveCount(0);
});

test("an interviewer is refused the candidate search and other portals", async ({ page }) => {
  await signIn(page, "interviewer@edusphere.local");
  expect((await page.request.post("/api/v1/recruiter/candidates/search", { data: {} })).status()).toBe(403);
  await page.goto("/recruiter/find-candidates");
  await expect(page.getByRole("search", { name: "Find candidates" })).toHaveCount(0);
  for (const path of ["/it/hr-manager/dashboard", "/it/placement/dashboard"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: /HR Manager Dashboard|Placement Dashboard/ })).toHaveCount(0);
  }
});

// hrc-007 (DEC-SCOPE-380 A12) made jobs.approve the HR Manager's default, so the screen shows it held; switching it off is the change.
test("a super admin configures jobs.approve for the HR Manager on the permission screen", async ({ page }) => {
  await signIn(page, "superadmin@edusphere.local", "global");
  try {
    await page.goto("/admin/permissions");
    await page.getByLabel("Role", { exact: true }).selectOption("hr_manager");
    const approve = page.getByRole("checkbox", { name: /Vacancies.*approve/i });
    await expect(approve).toBeChecked();
    await approve.uncheck();
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Saved HR Manager: 1 change.")).toBeVisible();
    const stored = await (await page.request.get("/api/v1/admin/roles/hr_manager/permissions")).json();
    expect(stored.permissions).toEqual([]);
  } finally {
    const restore = await page.request.put("/api/v1/admin/roles/hr_manager/permissions", { data: { permissions: ["jobs.approve"] } });
    expect(restore.status()).toBe(200);
  }
});
