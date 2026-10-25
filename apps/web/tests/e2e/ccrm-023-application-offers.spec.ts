import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-023 (DEC-SCOPE-245) -- the counselor records an offer from the Evaluate Applications card with an uploaded letter, records a
// second one (the first stays as superseded), then marks the current one expired. Requires the stack running with `python -m app.seed`
// applied. The spec makes its own counselor, walk-in student and application, so no seeded record changes.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");

test("the counselor records, supersedes and closes offers (ccrm-023)", async ({ page }) => {
  test.setTimeout(90_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const studentName = `Offer Records ${unique}`;

  await signInAsFreshCounselor(page, "ccrm023");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: studentName, email: `ccrm023-s-${unique}@example.local` } });
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
  await expect(card.getByText("No offer recorded yet.")).toBeVisible();

  const issued = new Date(Date.now() - 2 * 86_400_000).toISOString().slice(0, 10);
  await card.getByRole("button", { name: "Record offer" }).click();
  await card.getByLabel("Conditional", { exact: true }).check();
  await card.getByLabel("Issue date").fill(issued);
  await card.getByLabel(/^Conditions/).fill("IELTS 6.5 overall");
  await card.getByLabel("Currency").fill("gbp");
  await card.getByLabel("Tuition fee").fill("18500");
  await card.getByLabel("Upload the offer letter (PDF or image)").setInputFiles({ name: "offer.pdf", mimeType: "application/pdf", buffer: PDF });
  await card.getByRole("button", { name: "Save offer" }).click();
  await expect(card.getByText("Offer recorded.")).toBeVisible();
  await expect(card.getByText("Conditional offer", { exact: true }).first()).toBeVisible();
  await expect(card.getByText("GBP 18,500.00")).toBeVisible();

  await card.getByRole("button", { name: "Record new offer" }).click();
  await card.getByLabel("Unconditional", { exact: true }).check();
  await card.getByLabel("Issue date").fill(issued);
  await card.getByLabel("Offer letter", { exact: true }).selectOption({ label: "offer.pdf" });
  await card.getByRole("button", { name: "Save offer" }).click();
  await expect(card.getByText("Offer recorded.")).toBeVisible();
  await expect(card.getByText("Superseded")).toBeVisible();

  await card.getByRole("button", { name: "Close offer" }).click();
  await card.getByLabel("Outcome").selectOption("expired");
  await card.getByLabel("Reason").fill("Deadline passed without acceptance");
  await card.getByRole("button", { name: "Confirm" }).click();
  await expect(card.getByText("Offer marked expired.")).toBeVisible();

  await page.reload();
  const again = cardOf();
  await again.getByRole("button", { name: "Offers" }).click();
  await expect(again.getByRole("region", { name: "Offers" }).locator(":scope > ul > li")).toHaveCount(2); // offers only, not ccrm-024's nested conditions
  await expect(again.getByText(/Deadline passed without acceptance/)).toBeVisible();
  const listed = (await (await page.request.get(`/api/v1/workflows/overseas/applications/${appId}/offers`)).json()) as { offers: { status: string }[] };
  expect(listed.offers.map((o) => o.status)).toEqual(["expired", "superseded"]);
  expect(consoleErrors).toEqual([]);
});
