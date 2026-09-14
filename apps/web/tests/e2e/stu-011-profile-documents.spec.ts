import { test, expect } from "@playwright/test";

// STU-011 -- Profile and document management. Requires the stack running via
// `docker compose up` with `python -m app.seed` already applied.

test("student edits profile and uploads a document (STU-011-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/profile");

  const documentsCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Documents" }) });
  await documentsCard.getByLabel("Document type").fill("Resume");
  await documentsCard.getByLabel("File").setInputFiles({ name: "resume.txt", mimeType: "text/plain", buffer: Buffer.from("STU-011 E2E resume content") });
  await documentsCard.getByRole("button", { name: "Upload document" }).click();
  await expect(documentsCard.getByText("Document uploaded.")).toBeVisible();
  // The shared seeded demo student accumulates one list item per E2E run (same pattern
  // as RAID I-03) -- assert at least one match exists, not exactly one.
  await expect(documentsCard.getByText(/Resume -- resume.txt/).first()).toBeVisible();
});

test("invalid file type on document upload is rejected with a clear message (STU-011-AC02)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/profile");
  const documentsCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Documents" }) });
  await documentsCard.getByLabel("Document type").fill("Malware");
  await documentsCard.getByLabel("File").setInputFiles({ name: "bad.exe", mimeType: "application/x-msdownload", buffer: Buffer.from("not a real exe") });
  await documentsCard.getByRole("button", { name: "Upload document" }).click();
  await expect(documentsCard.locator(".form-error")).toBeVisible();
});

test("an uploaded document has a real, working download button (RAID.md I-16)", async ({ page }) => {
  // RAID.md I-16: tester feedback said uploaded documents had no download option -- the
  // list rendered as inert plain text with no action at all. Confirms the real fix.
  await page.goto("/it/login");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/profile");
  const documentsCard = page.locator(".action-card", { has: page.getByRole("heading", { name: "Documents" }) });
  const uniqueType = `I16 Download Check ${Date.now()}`;
  await documentsCard.getByLabel("Document type").fill(uniqueType);
  await documentsCard.getByLabel("File").setInputFiles({ name: "download-check.txt", mimeType: "text/plain", buffer: Buffer.from("STU-011 download check content") });
  await documentsCard.getByRole("button", { name: "Upload document" }).click();
  await expect(documentsCard.getByText("Document uploaded.")).toBeVisible();

  const row = documentsCard.locator("li", { hasText: uniqueType });
  const [downloadPage] = await Promise.all([
    page.waitForEvent("popup"),
    row.getByRole("button", { name: "Download" }).click(),
  ]);
  await downloadPage.waitForLoadState();
  expect(downloadPage.url()).toMatch(/local-files|amazonaws|storage/);
  await downloadPage.close();
});

test("profile page requires authentication", async ({ page }) => {
  await page.goto("/it/student/profile");
  await expect(page).toHaveURL(/\/it\/login/);
});
