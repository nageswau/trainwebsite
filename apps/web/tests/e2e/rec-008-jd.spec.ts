import { expect, test, type Page } from "@playwright/test";

// rec-008 (AC1-AC3, JD6): the seeded recruiter opens a new requirement, creates its JD from the prefilled form, uploads a PDF as
// version 2 (a PNG is refused), downloads it, and copies the JD's role onto the requirement after confirming.

async function signIn(page: Page, email: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/recruiter/dashboard");
}

const RECRUITER = "placement@edusphere.local";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

test("a recruiter creates, uploads and applies a JD", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const title = `Python Developer ${stamp}`;
  await signIn(page, RECRUITER);

  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Rec008 ${stamp} Labs` } });
  expect(company.ok()).toBeTruthy();
  const companyId = (await company.json()).company.id as string;
  const created = await page.request.post("/api/v1/recruiter/requirements", {
    data: { company_id: companyId, title, location: "Hyderabad", vacancies: 3, experience_min_months: 0, experience_max_months: 24 },
  });
  expect(created.ok()).toBeTruthy();
  const requirementId = (await created.json()).requirement.id as string;

  await page.goto(`/recruiter/requirements/${requirementId}`);
  const jd = page.getByRole("region", { name: /Job description \(JD\)/ });
  await expect(jd.getByText("No JD yet.")).toBeVisible();

  await jd.getByRole("button", { name: "Create JD" }).click();
  await expect(jd.getByLabel("Job role *")).toHaveValue(title); // prefilled from the requirement
  await expect(jd.getByLabel("Experience", { exact: true })).toHaveValue("0–2 years");
  await jd.getByLabel("Job role *").fill(`Senior ${title}`);
  await jd.getByLabel("Responsibilities").fill("Own the payments API");
  await jd.getByRole("button", { name: "Save JD" }).click();
  await expect(jd.getByText("JD saved as version 1.")).toBeVisible();
  await expect(jd.getByText(/JD-\d{6} · version 1/)).toBeVisible();
  await expect(jd.getByText("Own the payments API")).toBeVisible();

  const file = jd.getByLabel("Upload a new JD file (new version)");
  await file.setInputFiles({ name: "photo.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n0000") });
  await jd.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(jd.getByRole("alert")).toContainText("Upload a PDF or DOCX file");
  await file.setInputFiles({ name: "Senior JD.pdf", mimeType: "application/pdf", buffer: PDF });
  await jd.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(jd.getByText("JD file uploaded as version 2.")).toBeVisible();
  await expect(jd.getByText(/JD-\d{6} · version 2/)).toBeVisible();
  await expect(jd.getByText("Own the payments API")).toBeVisible(); // the fields carry forward
  await expect(jd.getByText("Current", { exact: true })).toHaveCount(1);

  const download = await page.request.get(`/api/v1/recruiter/requirements/${requirementId}/jd/2/file`);
  expect(download.status()).toBe(200);
  expect(await download.body()).toEqual(PDF);

  await jd.getByRole("button", { name: "Update requirement from JD" }).click();
  await expect(jd.getByRole("list", { name: "Changes" })).toContainText(`Job title: ${title} → Senior ${title}`);
  await jd.getByRole("button", { name: "Yes, update requirement" }).click();
  await expect(page.getByText("Requirement updated from the JD.")).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: new RegExp(`Senior ${title}`) })).toBeVisible();
  await expect(jd.getByText("The requirement already matches this JD.")).toBeVisible();
});
