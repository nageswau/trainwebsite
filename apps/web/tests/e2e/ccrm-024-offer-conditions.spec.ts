import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-024 (DEC-SCOPE-261) -- offer conditions: a conditional offer's text becomes one open condition (C1), the counselor adds a second,
// Met is refused without evidence (C2), evidence is uploaded, the other is waived with a note, and the all-satisfied prompt opens Record
// offer as Unconditional (C4). Requires the stack running with `python -m app.seed` applied; the spec makes its own counselor, student and
// application.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");
const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);

test("the counselor tracks offer conditions to all satisfied (ccrm-024)", async ({ page }) => {
  test.setTimeout(90_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const studentName = `Offer Conditions ${unique}`;

  await signInAsFreshCounselor(page, "ccrm024");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: studentName, email: `ccrm024-s-${unique}@example.local` } });
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
  await card.getByRole("button", { name: "Record offer" }).click();
  await card.getByLabel("Conditional", { exact: true }).check();
  await card.getByLabel("Issue date").fill(day(-2));
  await card.getByLabel(/^Conditions/).fill("IELTS 6.5 overall");
  await card.getByLabel("Upload the offer letter (PDF or image)").setInputFiles({ name: "offer.pdf", mimeType: "application/pdf", buffer: PDF });
  await card.getByRole("button", { name: "Save offer" }).click();
  await expect(card.getByText("Offer recorded.")).toBeVisible();

  const conditions = card.getByRole("list", { name: "Conditions" });
  await expect(conditions.locator("span:not(.visually-hidden)", { hasText: /^IELTS 6\.5 overall$/ })).toBeVisible();
  await expect(card.getByText("Offer letter conditions: IELTS 6.5 overall")).toBeVisible();
  await expect(card.getByText(/0 of 1 conditions satisfied/)).toBeVisible();

  await card.getByRole("button", { name: "Add condition" }).click();
  await card.getByLabel("Condition", { exact: true }).fill("Final transcript");
  await card.getByLabel("Owner").selectOption("student");
  await card.getByLabel("Due date (optional)").fill(day(20));
  await card.getByRole("button", { name: "Save condition" }).click();
  await expect(card.getByText("Condition added.")).toBeVisible();
  await expect(card.getByText(/0 of 2 conditions satisfied/)).toBeVisible();

  await card.getByRole("button", { name: "Update condition IELTS 6.5 overall" }).click();
  await card.getByLabel("Status").selectOption("met");
  await card.getByRole("button", { name: "Save condition" }).click();
  await expect(card.getByText("Attach the evidence before marking the condition met.")).toBeVisible();
  await card.getByLabel("Upload evidence (PDF or image)").setInputFiles({ name: "ielts.pdf", mimeType: "application/pdf", buffer: PDF });
  await card.getByRole("button", { name: "Save condition" }).click();
  await expect(card.getByText("Condition updated.")).toBeVisible();
  await expect(card.getByText(/1 of 2 conditions satisfied/)).toBeVisible();

  await page.reload();
  const again = cardOf();
  await again.getByRole("button", { name: "Offers" }).click();
  await again.getByRole("button", { name: "Update condition Final transcript" }).click();
  await again.getByLabel("Status").selectOption("waived");
  await again.getByLabel(/^Note/).fill("University accepted the provisional transcript");
  await again.getByRole("button", { name: "Save condition" }).click();
  await expect(again.getByText(/2 of 2 conditions satisfied/)).toBeVisible();
  await expect(again.getByText(/All conditions satisfied/)).toBeVisible();
  await again.getByRole("button", { name: "Record unconditional offer" }).click();
  await expect(again.getByLabel("Unconditional", { exact: true })).toBeChecked();

  const listed = (await (await page.request.get(`/api/v1/workflows/overseas/applications/${appId}/offers`)).json()) as {
    offers: { conditions_summary: { all_satisfied: boolean }; condition_items: { status: string; evidence: unknown }[] }[];
  };
  expect(listed.offers[0].conditions_summary.all_satisfied).toBe(true);
  expect(listed.offers[0].condition_items.map((c) => c.status)).toEqual(["met", "waived"]);
  expect(JSON.stringify(listed)).not.toContain("file_url");
  expect(consoleErrors).toEqual([]);
});
