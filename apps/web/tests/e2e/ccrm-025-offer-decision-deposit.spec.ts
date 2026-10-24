import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-025 (DEC-SCOPE-255) -- Appendix B "Student accepts University B": the counselor records an offer with a deposit, records the
// student's acceptance, then the deposit (prefilled from the offer, paid, with a receipt), and finally the student's decline, which closes
// the application. Requires the stack running with `python -m app.seed` applied; the spec makes its own counselor, student and application.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");
const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);

test("the counselor records acceptance, the deposit and a decline (ccrm-025)", async ({ page }) => {
  test.setTimeout(90_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const studentName = `Offer Decision ${unique}`;

  await signInAsFreshCounselor(page, "ccrm025");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: studentName, email: `ccrm025-s-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  const studentId = (await created.json()).student.id as string;
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string }[];
  const app = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: studentId, university_id: universities[0].id, intake: "Fall 2027" } });
  expect(app.status()).toBe(201);
  const appId = (await app.json()).id as string;

  await page.goto("/overseas/counselor/applications");
  const cardOf = () => page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: studentName }).first();
  const card = cardOf();
  await card.getByRole("button", { name: "Offers" }).click();
  await expect(card.getByText("No deposit recorded yet.")).toBeVisible();

  await card.getByRole("button", { name: "Record offer" }).click();
  await card.getByLabel("Conditional", { exact: true }).check();
  await card.getByLabel("Issue date").fill(day(-2));
  await card.getByLabel(/^Conditions/).fill("IELTS 6.5 overall");
  await card.getByLabel("Currency").fill("gbp");
  await card.getByLabel("Deposit amount").fill("3000");
  await card.getByLabel("Deposit deadline").fill(day(20));
  await card.getByLabel("Upload the offer letter (PDF or image)").setInputFiles({ name: "offer.pdf", mimeType: "application/pdf", buffer: PDF });
  await card.getByRole("button", { name: "Save offer" }).click();
  await expect(card.getByText("Offer recorded.")).toBeVisible();
  await expect(card.getByText("Considering")).toBeVisible();

  await card.getByRole("button", { name: "Record acceptance" }).click();
  await card.getByRole("button", { name: "Save acceptance" }).click();
  await expect(card.getByText("Offer accepted.")).toBeVisible();
  await expect(card.getByText("Accepted", { exact: true })).toBeVisible();

  await card.getByRole("button", { name: "Record deposit" }).click();
  await expect(card.getByLabel("Amount")).toHaveValue("3000.00");
  await expect(card.getByLabel("Currency")).toHaveValue("GBP");
  await card.getByLabel("Payment status").selectOption("paid_to_university");
  await card.getByLabel("Paid on").fill(day(0));
  await card.getByLabel("Upload a receipt (PDF or image, optional)").setInputFiles({ name: "receipt.pdf", mimeType: "application/pdf", buffer: PDF });
  await card.getByRole("button", { name: "Save deposit" }).click();
  await expect(card.getByText("Deposit saved.")).toBeVisible();

  await page.reload();
  const again = cardOf();
  await again.getByRole("button", { name: "Offers" }).click();
  await expect(again.getByText("Paid directly to the university")).toBeVisible();
  await expect(again.getByText("GBP 3,000.00", { exact: false }).first()).toBeVisible();

  await again.getByRole("button", { name: "Record decline" }).click();
  await again.getByLabel("Reason").fill("Chose another university");
  await again.getByRole("button", { name: "Save decline" }).click();
  await expect(page.getByText("Offer declined. The application is now closed.")).toBeVisible();

  const listed = (await (await page.request.get(`/api/v1/workflows/overseas/applications/${appId}/offers`)).json()) as { offers: { decision: string }[] };
  expect(listed.offers.map((o) => o.decision)).toEqual(["declined"]);
  const deposit = (await (await page.request.get(`/api/v1/workflows/overseas/applications/${appId}/deposit`)).json()) as { record: { payment_status: string; receipt: unknown } };
  expect(deposit.record.payment_status).toBe("paid_to_university");
  expect(deposit.record.receipt).not.toBeNull();
  expect(consoleErrors).toEqual([]);
});
