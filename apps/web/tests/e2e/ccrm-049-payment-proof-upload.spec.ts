import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-049 (DEC-SCOPE-324) -- the counselor uploads a payment's receipt / proof from the student 360's Finance tab; the Overseas Admin
// replaces it; the student sees it on their Payments page and in their Documents and cannot call the route. The Overseas Admin first
// records a paid manual fee (with its system receipt) for the seeded demo counselor's student. Requires `python -m app.seed`.

const pdf = { name: "bank-transfer.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n") };

test("counselor uploads, admin replaces a payment's proof on the Finance tab; the student sees it (ccrm-049)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await signIn(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  const studentId = (await (await page.request.get("/api/v1/portal/overseas/counselor/applications")).json()).rows[0].student_id;
  await page.request.post("/api/v1/auth/logout");

  // a fresh, uniquely named manual fee, recorded as paid (so it has its system receipt too)
  const kind = `proof_check_${Date.now()}`;
  const description = kind.replace(/_/g, " ").replace(/^p/, "P");
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  const created = await page.request.post("/api/v1/admin/payments", { data: { user_id: studentId, amount: 1500, currency: "GBP", reference_type: kind, status: "paid" } });
  expect(created.status()).toBe(201);
  const paymentId = (await created.json()).id;
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  await page.goto(`/overseas/counselor/students/${studentId}?tab=finance`);
  const row = page.getByRole("region", { name: "Fees and payments" }).getByRole("listitem").filter({ hasText: description });
  const name = (action: string) => `${action} receipt for ${description}`;
  await expect(row.getByText(/Receipt RCPT-/)).toBeVisible(); // the system receipt number, apart from any upload

  // no file chosen: told in words, nothing sent
  await row.getByRole("button", { name: name("Upload") }).click();
  await expect(row.locator(".form-error")).toHaveText("Choose a PDF, JPEG or PNG file first.");

  await row.getByLabel(`Payment receipt file for ${description}`).setInputFiles(pdf);
  const [upload] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith(`/payments/${paymentId}/proof`)),
    row.getByRole("button", { name: name("Upload") }).click(),
  ]);
  expect(upload.status()).toBe(201);
  const proofId = (await upload.json()).payment.proof.id;
  await expect(row.locator(".form-message")).toHaveText("Receipt uploaded. The student can see it in their Documents.");
  await expect(row.getByText(`Uploaded proof: ${description}`)).toBeVisible();
  await expect(row.getByRole("button", { name: `Download ${description}` })).toBeVisible();
  await expect(row.getByRole("button", { name: name("Replace") })).toBeVisible();

  // a refresh keeps it; tablet and phone layouts do not scroll sideways
  await page.reload();
  await expect(page.getByRole("region", { name: "Fees and payments" }).getByRole("button", { name: name("Replace") })).toBeVisible();
  for (const width of [768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.request.post("/api/v1/auth/logout");

  // the student: their Documents and the Payments page's "Uploaded proof" column; the route refuses them
  await signIn(page, "student.overseas@edusphere.local", "Demo@123", "/overseas/student/dashboard");
  expect(JSON.stringify(await (await page.request.get("/api/v1/portal/overseas/student/documents")).json())).toContain(proofId);
  await page.goto("/overseas/student/payments");
  await expect(page.getByRole("columnheader", { name: "Uploaded proof" })).toBeVisible();
  await expect(page.getByText(`${description} — download from Documents`)).toBeVisible();
  expect((await page.request.post(`/api/v1/counselor/students/${studentId}/payments/${paymentId}/proof`, { multipart: { file: pdf } })).status()).toBe(403);
  await page.request.post("/api/v1/auth/logout");

  // the Overseas Admin replaces it
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto(`/overseas/admin/students/${studentId}?tab=finance`);
  const adminRow = page.getByRole("region", { name: "Fees and payments" }).getByRole("listitem").filter({ hasText: description });
  await adminRow.getByLabel(`Payment receipt file for ${description}`).setInputFiles({ ...pdf, name: "replacement.pdf" });
  const [replace] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith(`/payments/${paymentId}/proof`)),
    adminRow.getByRole("button", { name: name("Replace") }).click(),
  ]);
  expect(replace.status()).toBe(201);
  expect((await replace.json()).payment.proof.id).not.toBe(proofId);
  await expect(adminRow.locator(".form-message")).toHaveText("Receipt uploaded. The student can see it in their Documents.");
  // AC6: the system receipt is still offered, under its own name
  await expect(adminRow.getByRole("button", { name: /^Download receipt RCPT-/ })).toContainText("System receipt");
  expect(consoleErrors).toEqual([]);
});
