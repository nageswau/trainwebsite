import { test, expect, type Page } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-027 (DEC-SCOPE-262) -- Appendix B final row: the counselor confirms the student's enrolment with the confirmation document and the
// pre-enrolment checklist; a stage change never reaches Enrolled; another application records Non-arrival, which closes it. Requires the
// stack running with `python -m app.seed` applied; the spec makes its own counselor, students and applications.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");
const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);

async function applicationFor(page: Page, name: string, unique: number): Promise<string> {
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: name, email: `ccrm027-${name.split(" ")[0].toLowerCase()}-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string }[];
  const app = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: (await created.json()).student.id, university_id: universities[0].id, intake: "Fall 2027" } });
  expect(app.status()).toBe(201);
  return (await app.json()).id as string;
}

test("the counselor confirms enrolment with a document, and records non-arrival on another application (ccrm-027)", async ({ page }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const enrolling = `Confirmed ${unique}`;
  const absent = `Absent ${unique}`;

  await signInAsFreshCounselor(page, "ccrm027");
  const enrollingId = await applicationFor(page, enrolling, unique);
  const absentId = await applicationFor(page, absent, unique);

  await page.goto("/overseas/counselor/applications");
  const cardOf = (name: string) => page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: name }).first();
  for (const name of [enrolling, absent]) {
    const card = cardOf(name);
    await card.getByRole("button", { name: "Advance stage" }).click();
    await expect(card.getByLabel("Advance to").locator("option[value=enrolled]")).toHaveCount(0);
    await card.getByLabel("Advance to").selectOption("offer");
    await card.getByRole("button", { name: "Advance", exact: true }).click();
    await expect(card.getByRole("status")).toContainText("Application advanced");
  }

  const card = cardOf(enrolling);
  await card.getByRole("button", { name: "Enrolment", exact: true }).click();
  await expect(card.getByText("Enrolment not confirmed yet.")).toBeVisible();
  await card.getByRole("button", { name: "Confirm enrolment" }).click();
  await card.getByLabel("Enrolment date").fill(day(0));
  await card.getByLabel("Course start date").fill(day(14));
  await card.getByLabel("University student number (optional)").fill(`U-${unique}`);
  await card.getByRole("button", { name: "Continue" }).click();
  await expect(card.getByText("Attach the enrolment confirmation: pick an uploaded one or upload the file.")).toBeVisible();
  await card.getByLabel("Or upload the confirmation (PDF or image)").setInputFiles({ name: "confirmation.pdf", mimeType: "application/pdf", buffer: PDF });
  await card.getByLabel("The pre-enrolment checklist is complete").check();
  await card.getByRole("button", { name: "Continue" }).click();
  await card.getByRole("button", { name: "Yes, confirm enrolment" }).click();
  await expect(card.getByText("Enrolment confirmed.")).toBeVisible();

  await page.reload();
  const enrolled = cardOf(enrolling);
  await expect(enrolled.locator(".badge", { hasText: /^Enrolled$/ }).first()).toBeVisible(); // the stage, and ccrm-014's sub-status
  await expect(enrolled.getByRole("button", { name: "Advance stage" })).toHaveCount(0);
  await enrolled.getByRole("button", { name: "Enrolment", exact: true }).click();
  await expect(enrolled.getByText(`U-${unique}`)).toBeVisible();
  await expect(enrolled.getByRole("link", { name: "confirmation.pdf" })).toBeVisible();

  const other = cardOf(absent);
  await other.getByRole("button", { name: "Record outcome" }).click();
  const form = other.getByRole("form", { name: "Record outcome" });
  await form.getByLabel("Outcome", { exact: true }).selectOption("non_arrival");
  await form.getByLabel("Reason", { exact: true }).fill("Did not travel");
  await form.getByRole("button", { name: "Record outcome" }).click();
  await expect(other.getByText(/Outcome recorded: Non arrival/)).toBeVisible();
  await expect(other.getByText("This application is closed -- only the Overseas Admin can reopen it.")).toBeVisible();

  const view = async (id: string) => ((await (await page.request.get(`/api/v1/workflows/overseas/applications/${id}/enrollment`)).json()) as { enrollment: { confirmed: boolean } }).enrollment;
  expect((await view(enrollingId)).confirmed).toBe(true);
  expect((await view(absentId)).confirmed).toBe(false);
  expect(consoleErrors).toEqual([]);
});
