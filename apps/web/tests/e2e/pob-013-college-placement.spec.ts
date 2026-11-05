import { expect, test, type Page } from "@playwright/test";

// pob-013 (DEC-SCOPE-410): the seeded college BDM adds a college; the seeded recruiter finds it from the menu by course (AC3), adds a course,
// a batch and a calendar entry and logs a TPO meeting (AC1), and is refused the BDM-owned edit (AC2). No sideways scroll on a phone.
const RECRUITER = "placement@edusphere.local";
const BDM = "bdm.college@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("a recruiter finds a college by course and keeps its placement profile", async ({ page }) => {
  test.setTimeout(120_000);
  const tag = Date.now().toString(36);
  await signIn(page, BDM);
  const created = await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `POB13 College ${tag}`, city: "Kochi", state: "Kerala", courses: `Mechatronics${tag}`,
            contacts: [{ name: "Ms Iyer", designation: "TPO", role: "placement_officer", is_primary: true }] },
  });
  expect(created.status(), await created.text()).toBe(201);
  const org = (await created.json()).organization;

  await signIn(page, RECRUITER);
  await page.goto("/recruiter/dashboard");
  await page.getByRole("link", { name: "Colleges", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Colleges" })).toBeVisible();

  // AC3: search by course (the BDM's free-text courses count too)
  await page.getByLabel("Course").fill(`mechatronics${tag}`);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name: `POB13 College ${tag}` }).click();
  await expect(page.getByRole("heading", { name: `POB13 College ${tag}` })).toBeVisible();

  // AC1: a course, a batch, a calendar entry and a TPO meeting
  const course = page.getByRole("form", { name: "Add a course" });
  await course.getByLabel("Department (optional)").fill("Mechanical");
  await course.getByLabel("Course", { exact: true }).fill(`B.Tech Mechatronics ${tag}`);
  await course.getByRole("button", { name: "Add course" }).click();
  await expect(page.getByText("Course added.")).toBeVisible();

  const batch = page.getByRole("form", { name: "Add a batch" });
  await batch.getByLabel("Pass-out year").fill("2027");
  await batch.getByLabel("Course (optional)").selectOption({ label: `Mechanical · B.Tech Mechatronics ${tag}` });
  await batch.getByLabel("Students (optional)").fill("120");
  await batch.getByRole("button", { name: "Add batch" }).click();
  await expect(page.getByText("Batch added.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Graduating batches" }).getByText("120")).toBeVisible();

  const entry = page.getByRole("form", { name: "Add a calendar entry" });
  await entry.getByLabel("Title").fill("Pre-placement talk");
  await entry.getByLabel("Kind").selectOption("pre_placement_talk");
  await entry.getByLabel("Start date").fill("2026-12-01");
  await entry.getByRole("button", { name: "Add entry" }).click();
  await expect(page.getByText("Calendar entry added.")).toBeVisible();

  const log = page.getByRole("form", { name: "Log a TPO interaction" });
  await log.getByLabel("When").fill("2026-11-04T10:30");
  await log.getByLabel("With (optional)").selectOption({ label: "Ms Iyer" });
  await log.getByLabel("Summary").fill("Agreed the 2027 drive window");
  await log.getByRole("button", { name: "Log interaction" }).click();
  await expect(page.getByText("Interaction logged.")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Agreed the 2027 drive window")).toBeVisible();

  // AC3 by graduating year
  await page.goto("/recruiter/colleges");
  await page.getByLabel("Course").fill(`B.Tech Mechatronics ${tag}`);
  await page.getByLabel("Pass-out year").fill("2027");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("link", { name: `POB13 College ${tag}` })).toBeVisible();

  // AC2: the BDM-owned record and MoU stay the BDM's
  expect((await page.request.patch(`/api/v1/bdm/organizations/${org.id}`, { data: { name: "Renamed" } })).status()).toBe(403);
  expect((await page.request.get(`/api/v1/bdm/organizations/${org.id}/mou`)).status()).toBe(403);

  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(`/recruiter/colleges/${org.id}`);
  await expect(page.getByRole("heading", { name: "Placement" })).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
});
