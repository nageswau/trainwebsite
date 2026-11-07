import { expect, test, type Page } from "@playwright/test";

// pob-014 (DEC-SCOPE-425): the seeded college BDM adds a college; the seeded placement manager records a data permission naming the seeded
// recruiter; the recruiter imports the college's student list under it (AC1) and sees the student in the pool; the manager -- not named
// on the permission -- cannot open that student (AC2, 404). No sideways scroll on a phone.
const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const BDM = "bdm.college@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string, portal: "it" | "admin" = "it") {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

const iso = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);

test("an institution's students are imported under a permission and seen only by the people it names", async ({ page }) => {
  test.setTimeout(150_000);
  const tag = Date.now().toString(36);
  const college = `POB14 College ${tag}`;
  const student = `Pool Student ${tag}`;
  await signIn(page, BDM);
  const created = await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: college, city: "Kochi", state: "Kerala", contacts: [{ name: "Ms Iyer", designation: "TPO", role: "placement_officer", is_primary: true }] },
  });
  expect(created.status(), await created.text()).toBe(201);
  const orgId = (await created.json()).organization.id;

  // the manager records the permission (S4) and names the recruiter (S3)
  await signIn(page, MANAGER, "admin");
  await page.goto(`/recruiter/colleges/${orgId}`);
  const pool = page.getByRole("region", { name: "Institution student pool" });
  await pool.getByRole("button", { name: "Add a data permission" }).click();
  const form = pool.getByRole("form", { name: "Add a data permission" });
  await form.getByLabel("Agreement reference").fill(`MoU ${tag}`);
  await form.getByLabel("Valid from").fill(iso(-1));
  await form.getByLabel("Expires on").fill(iso(180));
  await form.getByLabel("Find a person").fill("Kiran");
  await form.getByLabel("Kiran Placement").check();
  await form.getByRole("button", { name: "Add permission" }).click();
  await expect(pool.getByText("Permission added.")).toBeVisible();
  await expect(pool.getByRole("table", { name: "Data permissions" }).getByText(`MoU ${tag}`)).toBeVisible();

  // AC1: the recruiter imports the list under it
  await signIn(page, RECRUITER);
  await page.goto(`/recruiter/colleges/${orgId}`);
  await page.getByRole("region", { name: "Institution student pool" }).getByRole("link", { name: "Import students" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/import\?/);
  await expect(page.getByText(`MoU ${tag}`, { exact: true })).toBeVisible();
  await page.getByLabel("Candidate source").selectOption({ index: 1 });
  await page.getByLabel("Basis for holding the details").selectOption({ index: 1 });
  await page.getByLabel("Students' notice or consent").selectOption("consented");
  const mobile = `9${Date.now().toString().slice(-9)}`;
  await page.getByLabel("Filled-in candidates file").setInputFiles({
    name: "students.csv", mimeType: "text/csv", buffer: Buffer.from(`name,mobile,qualification,passing_year\n${student},${mobile},B.Tech CSE,2027\n`),
  });
  await page.getByRole("button", { name: "Check file" }).click();
  await page.getByRole("button", { name: "Import 1 new candidate" }).click();
  await expect(page.getByText(`Imported for ${college} under MoU ${tag}.`)).toBeVisible();
  const href = await page.getByRole("table", { name: "Import report" }).getByRole("link").first().getAttribute("href");
  const candidateId = href!.split("/").pop()!;

  await page.goto(`/recruiter/colleges/${orgId}`);
  const students = page.getByRole("table", { name: "Students" });
  await expect(students.getByText(student)).toBeVisible();
  await expect(students.getByText("Not applied")).toBeVisible();
  await page.setViewportSize({ width: 375, height: 800 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });

  // AC2: the manager is not on the permission -- the student reads as missing and is not in the pool
  await signIn(page, MANAGER, "admin");
  expect((await page.request.get(`/api/v1/recruiter/candidates/${candidateId}`)).status()).toBe(404);
  await page.goto(`/recruiter/colleges/${orgId}`);
  await expect(page.getByRole("region", { name: "Institution student pool" }).getByText("No students to show.")).toBeVisible();
});
