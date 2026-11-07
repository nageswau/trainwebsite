import { expect, test, type Page } from "@playwright/test";

// pob-015 (DEC-SCOPE-426): the seeded college BDM adds a college; the seeded recruiter shares one of their open vacancies with it (AC1:
// it appears on the college's timeline), records the TPO's reply, and finds the drive and the batch on the campus calendar (AC3). The
// college's BDM sees the share and its reply on the organization page. No sideways scroll on a phone.
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

function nextMonth(): { month: string; day: string } {
  const d = new Date();
  const first = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1));
  const month = `${first.getUTCFullYear()}-${String(first.getUTCMonth() + 1).padStart(2, "0")}`;
  return { month, day: `${month}-10` };
}

test("a recruiter shares a vacancy with a college and sees its campus dates", async ({ page }) => {
  test.setTimeout(150_000);
  const tag = Date.now().toString(36);
  const { month, day } = nextMonth();
  await signIn(page, BDM);
  const created = await page.request.post("/api/v1/bdm/organizations", {
    data: { org_type: "college", name: `POB15 College ${tag}`, city: "Kochi", state: "Kerala", contacts: [{ name: "Ms Iyer", role: "placement_officer", is_primary: true }] },
  });
  expect(created.status(), await created.text()).toBe(201);
  const org = (await created.json()).organization;

  await signIn(page, RECRUITER);
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `POB15 Co ${tag} Ltd` } });
  expect(company.ok(), await company.text()).toBeTruthy();
  const companyId = (await company.json()).company.id;
  const title = `POB15 Java ${tag}`;
  const made = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: companyId, title, location: "Pune" } });
  expect(made.ok(), await made.text()).toBeTruthy();
  const requirement = (await made.json()).requirement;
  if (requirement.status === "new") {
    expect((await page.request.post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { data: { status: "requirement_received" } })).ok()).toBeTruthy();
  }
  const drive = await page.request.post("/api/v1/recruiter/drives", {
    data: { company_id: companyId, college_org_id: org.id, requirement_ids: [requirement.id], drive_date: day, job_role: `Drive role ${tag}`, vacancies: 5 },
  });
  expect(drive.status(), await drive.text()).toBe(201);
  const batch = await page.request.post(`/api/v1/recruiter/colleges/${org.id}/batches`, { data: { pass_out_year: Number(month.slice(0, 4)), pass_out_date: day, student_count: 90 } });
  expect(batch.status(), await batch.text()).toBe(201);

  // AC1: share from the college page; it is listed at once and after a reload; a double submit is refused
  await page.goto(`/recruiter/colleges/${org.id}`);
  const form = page.getByRole("form", { name: "Share a vacancy" });
  await page.getByLabel("Find a vacancy").fill(title);
  await page.getByRole("button", { name: "Search vacancies" }).click();
  await form.getByLabel("Vacancy").selectOption({ label: `${requirement.requirement_code ?? requirement.code} · ${title} · POB15 Co ${tag} Ltd` });
  await form.getByLabel("Shared by").selectOption("whatsapp");
  await form.getByLabel("Notes (optional)").fill("Sent the JD to Ms Iyer");
  await form.getByRole("button", { name: "Record share" }).click();
  await expect(page.getByText("Vacancy share recorded.")).toBeVisible();
  await expect(page.locator("li strong", { hasText: title })).toBeVisible();
  await form.getByLabel("Vacancy").selectOption({ label: `${requirement.requirement_code ?? requirement.code} · ${title} · POB15 Co ${tag} Ltd` });
  await form.getByLabel("Shared by").selectOption("whatsapp");
  await form.getByRole("button", { name: "Record share" }).click();
  await expect(form.getByRole("alert")).toContainText("already recorded");

  await page.getByRole("button", { name: `Record the reply for ${title}` }).click();
  await page.getByLabel("Reply", { exact: true }).selectOption("interested");
  await page.getByRole("button", { name: "Save reply" }).click();
  await expect(page.getByText("Reply saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Interested", { exact: true })).toBeVisible();
  await expect(page.getByText("Sent the JD to Ms Iyer")).toBeVisible();

  // AC3: the drive and the batch are on the campus calendar, reached from the menu
  await page.goto("/recruiter/dashboard");
  await page.getByRole("link", { name: "Campus calendar", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Campus calendar" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "TPO partnerships" })).toBeVisible();
  await page.getByRole("link", { name: "Next month →" }).click();
  await page.waitForURL(/month=/);
  expect(page.url()).toContain(`month=${month}`);
  await expect(page.getByText(`Drive role ${tag}`)).toBeVisible();
  const ours = page.locator("li", { hasText: `POB15 College ${tag}` });
  await expect(ours.filter({ hasText: "Batch pass-out" })).toHaveCount(1);
  await page.setViewportSize({ width: 375, height: 800 });
  expect(await noSideScroll(page)).toBe(true);

  // the college's BDM reads the share and its reply on the organization page
  await signIn(page, BDM);
  await page.goto(`/bdm/organizations/${org.id}`);
  await expect(page.getByRole("heading", { name: "Vacancies shared" })).toBeVisible();
  await expect(page.locator("li strong", { hasText: title })).toBeVisible();
  await expect(page.getByText("Interested", { exact: true })).toBeVisible();
  await expect(page.getByRole("form", { name: "Share a vacancy" })).toBeVisible(); // V2: the college's assigned BDM is one of its writers
  expect(await noSideScroll(page)).toBe(true);
});
