import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-048 (DEC-SCOPE-321) -- the counselor uploads the university deposit receipt from the student 360's Finance tab; the Overseas Admin
// replaces it; the student sees it in their Documents and cannot call the route. Uses the seeded demo counselor's application (a required
// deposit is recorded on it through ccrm-025's route first). Requires `python -m app.seed`.

const pdf = { name: "deposit-receipt.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n") };

test("counselor uploads, admin replaces the deposit receipt on the Finance tab; the student sees it (ccrm-048)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await signIn(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  const apps = await (await page.request.get("/api/v1/portal/overseas/counselor/applications")).json();
  const app = apps.rows[0];
  const deposit = await page.request.put(`/api/v1/workflows/overseas/applications/${app.id}/deposit`, {
    data: { required: true, payment_status: "pending", amount: "3000", currency: "GBP" },
  });
  expect(deposit.ok()).toBeTruthy();

  await page.goto(`/overseas/counselor/students/${app.student_id}?tab=finance`);
  const deposits = page.getByRole("region", { name: "University deposits" });
  const card = deposits.getByRole("listitem").filter({ hasText: app.university });
  const name = (action: string) => `${action} receipt for ${app.university}`;
  // a fresh seed has no receipt; a re-run on the same DB already has one
  const first = (await card.getByRole("button", { name: name("Replace") }).count()) ? "Replace" : "Upload";

  // no file chosen: told in words, nothing sent
  await card.getByRole("button", { name: name(first) }).click();
  await expect(card.locator(".form-error")).toHaveText("Choose a PDF, JPEG or PNG file first.");

  await card.getByLabel(`Deposit receipt file for ${app.university}`).setInputFiles(pdf);
  const [upload] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith(`/applications/${app.id}/deposit/receipt`)),
    card.getByRole("button", { name: name(first) }).click(),
  ]);
  expect(upload.status()).toBe(201);
  const receiptId = (await upload.json()).record.receipt.id;
  await expect(card.locator(".form-message")).toHaveText("Receipt uploaded. The student can see it in their Documents.");
  await expect(card.getByText(/^Receipt: Deposit receipt/)).toBeVisible();
  await expect(card.getByRole("button", { name: "Download Deposit receipt" })).toBeVisible();
  await expect(card.getByRole("button", { name: name("Replace") })).toBeVisible();

  // a refresh keeps it; the phone layout does not scroll sideways
  await page.reload();
  await expect(page.getByRole("region", { name: "University deposits" }).getByRole("button", { name: name("Replace") })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.request.post("/api/v1/auth/logout");

  // the student sees the receipt in their Documents, and cannot call the route
  await signIn(page, "student.overseas@edusphere.local", "Demo@123", "/overseas/student/dashboard");
  const documents = await (await page.request.get("/api/v1/portal/overseas/student/documents")).json();
  expect(JSON.stringify(documents)).toContain(receiptId);
  expect((await page.request.post(`/api/v1/workflows/overseas/applications/${app.id}/deposit/receipt`, { multipart: { file: pdf } })).status()).toBe(403);
  await page.request.post("/api/v1/auth/logout");

  // the Overseas Admin replaces it
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto(`/overseas/admin/students/${app.student_id}?tab=finance`);
  const adminCard = page.getByRole("region", { name: "University deposits" }).getByRole("listitem").filter({ hasText: app.university });
  await adminCard.getByLabel(`Deposit receipt file for ${app.university}`).setInputFiles({ ...pdf, name: "replacement.pdf" });
  const [replace] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith(`/applications/${app.id}/deposit/receipt`)),
    adminCard.getByRole("button", { name: name("Replace") }).click(),
  ]);
  expect(replace.status()).toBe(201);
  expect((await replace.json()).record.receipt.id).not.toBe(receiptId);
  await expect(adminCard.locator(".form-message")).toHaveText("Receipt uploaded. The student can see it in their Documents.");
  expect(consoleErrors).toEqual([]);
});
