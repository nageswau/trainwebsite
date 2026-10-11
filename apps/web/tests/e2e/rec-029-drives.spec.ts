import { expect, test, type Page } from "@playwright/test";

// rec-029 (AC1, AC2; DR2, DR8, DR9): the seeded recruiter creates a campus drive for two requirements of a new company at a typed-in
// college, is stopped on attended > registered (AC2), adds two candidates through the drive and sees the funnel count them (AC1);
// the seeded placement manager reads the drive without any write control. The BDM-college picker and every funnel rule are covered by
// test_rec_029_drives.py and the component tests.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function pick(page: Page, label: string, text: string, option: RegExp) {
  await page.getByRole("combobox", { name: label }).fill(text);
  await page.getByRole("option", { name: option }).first().click();
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

test("a campus drive: create with two requirements, AC2 refused, candidates through the drive feed the funnel; the manager reads only", async ({ page }) => {
  test.setTimeout(150_000);
  const consoleErrors: string[] = [];
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  page.on("response", (r) => r.status() >= 500 && consoleErrors.push(`${r.status()} ${r.url()}`));
  const stamp = Date.now();
  const companyName = `E2E Rec029 ${stamp} Technologies`;
  const college = `E2E College ${stamp}`;
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");

  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: companyName } });
  expect(company.ok()).toBeTruthy();
  const companyId = (await company.json()).company.id as string;
  for (const title of [`GET ${stamp}`, `SDE ${stamp}`]) {
    const created = await page.request.post("/api/v1/recruiter/requirements", { data: { company_id: companyId, title, location: "Kochi", vacancies: 20 } });
    expect(created.ok()).toBeTruthy();
  }
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral");
  for (const name of [`Rahul ${stamp}`, `Anjali ${stamp}`]) {
    const created = await page.request.post("/api/v1/recruiter/candidates", { data: { name, email: `${name.split(" ")[0].toLowerCase()}${stamp}@example.com`, source_id: source.id } });
    expect(created.status()).toBe(201);
  }

  await page.getByRole("link", { name: "Campus Drives" }).click();
  await expect(page.getByRole("heading", { name: "Campus Drives" })).toBeVisible();
  await page.getByRole("button", { name: "+ New drive" }).click();
  await pick(page, "Company", companyName, new RegExp(companyName));
  await pick(page, "Add a job requirement", `GET ${stamp}`, new RegExp(`GET ${stamp}`));
  await pick(page, "Add a job requirement", `SDE ${stamp}`, new RegExp(`SDE ${stamp}`));
  await page.getByLabel("College name").fill(college);
  await page.getByLabel("Drive date").fill("2026-11-20");
  await page.getByLabel("Job role").fill("Graduate Engineer Trainee");
  await page.getByLabel("Vacancies").fill("40");
  await page.getByLabel("Students registered").fill("100");
  await page.getByLabel("Students attended").fill("120");
  await page.getByRole("button", { name: "Create drive" }).click();
  await expect(page.locator(".form-error[role=alert]")).toHaveText("Students attended cannot be more than students registered."); // AC2
  await page.getByLabel("Students registered").fill("200");
  await page.getByLabel("Students attended").fill("100");
  await page.getByRole("button", { name: "Create drive" }).click();
  await page.waitForURL(/\/recruiter\/drives\/[0-9a-f-]{36}$/);
  const driveUrl = page.url();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(`Graduate Engineer Trainee at ${college}`);
  const funnel = page.getByRole("list", { name: "Drive funnel" });
  await expect(funnel).toContainText("Registered200");

  for (const [requirement, candidate, status] of [[`GET ${stamp}`, `Rahul ${stamp}`, "Shortlisted"], [`SDE ${stamp}`, `Anjali ${stamp}`, "Sourced"]]) {
    await page.getByRole("button", { name: `Add candidate to ${requirement}` }).click();
    await pick(page, "Candidate", candidate, new RegExp(candidate));
    await page.getByLabel("Starting status").selectOption({ label: status });
    await page.getByRole("button", { name: "Add candidate", exact: true }).click();
    await expect(page.locator("p[role=status]")).toHaveText("Candidate added through this drive.");
  }
  await expect(funnel).toContainText("Shortlisted1"); // AC1: the drive-tagged applications
  const tagged = page.getByRole("list", { name: "Candidates from this drive" });
  await expect(tagged.getByRole("listitem")).toHaveCount(2);
  await page.reload();
  await expect(page.getByRole("list", { name: "Drive funnel" })).toContainText("Shortlisted1");

  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto(driveUrl);
  await expect(page.getByRole("list", { name: "Drive funnel" })).toContainText("Attended100");
  await expect(page.getByRole("button", { name: "Edit drive" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Add candidate/ })).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});
