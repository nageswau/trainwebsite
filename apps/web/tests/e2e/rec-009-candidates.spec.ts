import { expect, test, type Page } from "@playwright/test";

// rec-009 (AC1-AC4, Q-07): a recruiter adds Rahul (source Edusphere students, detail = the course), the same mobile is blocked with the
// existing candidate shown, a resume is uploaded as a version, and the list shows the source; HR reads but has no write controls.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

test("a recruiter adds a candidate, is stopped on a duplicate, uploads a resume; HR reads only", async ({ page }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  const mobile = `9${String(stamp).slice(-9)}`;
  const name = `Rahul ${stamp}`;
  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  await page.getByRole("link", { name: "Candidate Master" }).first().click();
  await page.waitForURL("**/recruiter/candidates");
  await page.getByRole("link", { name: "+ Add candidate" }).click();
  await page.waitForURL("**/recruiter/candidates/new");

  // The form's own required check sends nothing.
  await page.getByRole("button", { name: "Add candidate" }).click();
  await expect(page.getByText("Enter the name, source and a mobile number or an email.")).toBeVisible();

  await page.getByLabel(/^Name/).fill(name);
  await page.getByLabel(/^Mobile/).fill(mobile);
  await page.getByLabel(/^Total experience/).fill("30");
  await page.getByLabel(/^Preferred role/).fill("Python Developer");
  await page.getByLabel("Source *").selectOption({ label: "Edusphere students" });
  await page.getByLabel(/^Source detail/).fill("Edusphere Python Full Stack Course");
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { name, level: 2 })).toBeVisible();
  const code = (await page.getByText(/^CAN-\d{6}$/).textContent())!.trim();
  expect(code).toMatch(/^CAN-\d{6}$/);
  await expect(page.getByText("Edusphere Python Full Stack Course")).toBeVisible();
  await expect(page.getByText("2 yr 6 mo")).toBeVisible();

  // AC4: a resume version.
  await page.getByLabel("Upload resume").setInputFiles({ name: "rahul.pdf", mimeType: "application/pdf", buffer: PDF });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText("Resume version 1 uploaded.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Version 1 — rahul.pdf" })).toBeVisible();
  await expect(page.getByText("Current", { exact: true })).toBeVisible();

  // AC3 / Q-07: the same mobile in another format is blocked, and the panel opens the existing candidate.
  await page.goto("/recruiter/candidates/new");
  await page.getByLabel(/^Name/).fill(`Rahul again ${stamp}`);
  await page.getByLabel(/^Mobile/).fill(`+91 ${mobile.slice(0, 5)} ${mobile.slice(5)}`);
  await page.getByLabel("Source *").selectOption({ label: "Referral" });
  await page.getByRole("button", { name: "Add candidate" }).click();
  const panel = page.getByRole("region", { name: /already a candidate/i });
  await expect(panel).toBeVisible();
  await expect(panel.getByText(code)).toBeVisible();
  await panel.getByRole("link", { name: `Open ${code}` }).click();
  await expect(page.getByRole("heading", { name, level: 2 })).toBeVisible();

  // AC2 / S2-§13: the list shows the source.
  await page.goto(`/recruiter/candidates?q=${stamp}`);
  const row = page.getByRole("row", { name: new RegExp(name) });
  await expect(row).toContainText("Edusphere students");
  await expect(row).toContainText(code);
  await page.request.post("/api/v1/auth/logout");

  // HR reads: no add button, no edit, but the resume downloads.
  await signIn(page, "it", "hr@edusphere.local", "/it/hr/dashboard");
  await page.goto(`/recruiter/candidates?q=${stamp}`);
  await expect(page.getByRole("link", { name })).toBeVisible();
  await expect(page.getByRole("link", { name: "+ Add candidate" })).toHaveCount(0);
  await page.getByRole("link", { name }).click();
  await expect(page.getByRole("heading", { name, level: 2 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit" })).toHaveCount(0);
  await expect(page.getByLabel("Upload resume")).toHaveCount(0);
  const download = await page.request.get((await page.getByRole("link", { name: "Version 1 — rahul.pdf" }).getAttribute("href"))!);
  expect(download.status()).toBe(200);
});
