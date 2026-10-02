import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { pickFromList } from "./helpers/pick";

// AGN-010 -- offer details on an agency application for a student with no login: upload the offer letter against the application,
// record a conditional offer (stage moves to Offer), switch it to unconditional (history), the dashboard Offers KPI, the 422 for a
// deadline before the offer date, keyboard-only completion, 320 px. Unique names per run (shared E2E DB). Requires `python -m app.seed`.
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
const PDF = { name: "offer.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n") };
const isoDaysAgo = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);

async function studentWithApplication(page: Page, name: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();
  const universities = await (await page.request.get("/api/v1/public/universities")).json();
  await page.goto("/overseas/agent/applications");
  await pickFromList(page.getByRole("combobox", { name: "Linked student" }), name, new RegExp(`^${name} — no login$`));
  await page.locator("#agent-app-university").selectOption(universities.find((u: { slug: string }) => u.slug === "university-of-manchester").id);
  await page.getByRole("button", { name: /Create application/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Application created." })).toBeVisible();
}

async function openDetail(page: Page, name: string) {
  await page.goto("/overseas/agent/applications");
  await page.getByRole("list", { name: "Applications", exact: true }).getByRole("button", { name: new RegExp(`^View ${name} — `) }).click();
  return page.getByRole("region", { name: new RegExp(`^${name} — `) });
}

async function offersKpi(page: Page): Promise<number> {
  const payload = await (await page.request.get("/api/v1/portal/overseas/agent/dashboard")).json();
  return payload.metrics.find((m: { label: string }) => m.label === "Offers").value;
}

test("a Master records a conditional offer with its letter, then switches it to unconditional (AC01-AC05)", async ({ page }) => {
  test.setTimeout(150_000);
  const name = `E2E Offer ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await studentWithApplication(page, name);
  const before = await offersKpi(page);

  // The offer letter is an AGN-009 upload against the application.
  await page.goto("/overseas/agent/documents?view=uploaded");
  const upload = page.getByRole("form", { name: "Upload document" });
  await pickFromList(upload.getByRole("combobox", { name: "Student" }), name, new RegExp(`^${name} — no login$`));
  await upload.getByLabel("Document type").selectOption("Offer letter");
  const application = upload.getByLabel("Application (required for an offer letter)");
  await expect(application).toBeEnabled();
  await application.selectOption({ index: 1 });
  await upload.getByLabel("File (PDF, JPEG or PNG)").setInputFiles(PDF);
  await upload.getByRole("button", { name: "Upload document" }).click();
  await expect(upload.getByRole("status")).toHaveText("Document uploaded. It is waiting for review.");

  const detail = await openDetail(page, name);
  const offer = detail.getByRole("region", { name: "Offer", exact: true });
  await expect(offer.getByText("No offer recorded yet.")).toBeVisible();
  await offer.getByRole("button", { name: "Record offer" }).click();
  const form = offer.getByRole("form", { name: "Record offer" });
  await form.getByRole("radio", { name: "Conditional", exact: true }).check();
  await form.getByLabel("Offer date").fill(isoDaysAgo(2));
  await form.getByLabel(/Conditions/).fill("IELTS 6.5 overall\nFinal transcript");
  await form.getByLabel("Offer letter (optional)").selectOption({ label: "offer.pdf (Pending review)" });
  await form.getByRole("button", { name: "Save offer" }).click();
  await expect(detail.getByRole("status")).toHaveText("Offer saved.");
  await expect(offer.getByText("Conditional", { exact: true })).toBeVisible();
  await expect(offer.getByRole("button", { name: "Download offer.pdf" })).toBeVisible();
  await expect(detail.getByRole("list", { name: "Status history" })).toContainText("Offer recorded: Conditional");
  expect(await offersKpi(page)).toBe(before + 1);

  await offer.getByRole("button", { name: "Edit offer" }).click();
  const edit = offer.getByRole("form", { name: "Edit offer" });
  await edit.getByRole("radio", { name: "Unconditional", exact: true }).check();
  await expect(edit.getByLabel(/Conditions/)).toHaveCount(0);
  await edit.getByRole("button", { name: "Save offer" }).click();
  await expect(detail.getByRole("status")).toHaveText("Offer saved.");
  await expect(detail.getByRole("list", { name: "Status history" })).toContainText("Conditional → Unconditional");
  expect(await offersKpi(page)).toBe(before + 1); // the same offer, counted once
});

test("a deadline before the offer date is refused and the input is kept (AC01)", async ({ page }) => {
  const name = `E2E OfferBad ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await studentWithApplication(page, name);
  const detail = await openDetail(page, name);
  const items = (await (await page.request.get("/api/v1/workflows/overseas/agent/crm/applications?status=all&limit=100")).json()).items;
  const id = items.find((a: { student: string }) => a.student === name).id;
  const response = await page.request.put(`/api/v1/workflows/overseas/agent/crm/applications/${id}/offer`, {
    data: { offer_type: "unconditional", offer_date: isoDaysAgo(2), offer_deadline: isoDaysAgo(3) },
  });
  expect(response.status()).toBe(422);
  expect(JSON.stringify(await response.json())).toContain("Offer deadline cannot be before the offer date");
  await expect(detail.getByRole("region", { name: "Offer", exact: true }).getByText("No offer recorded yet.")).toBeVisible();
});

test("the offer form can be completed with the keyboard and fits 320 px", async ({ page }) => {
  const name = `E2E OfferKb ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await studentWithApplication(page, name);
  await page.setViewportSize({ width: 320, height: 800 });
  const detail = await openDetail(page, name);
  const offer = detail.getByRole("region", { name: "Offer", exact: true });
  await offer.getByRole("button", { name: "Record offer" }).focus();
  await page.keyboard.press("Enter");
  const form = offer.getByRole("form", { name: "Record offer" });
  await expect(form.getByRole("radio", { name: "Conditional", exact: true })).toBeFocused(); // QA-02: opening the form moves focus here
  await page.keyboard.press("ArrowDown"); // radio group: arrows move and select
  await expect(form.getByRole("radio", { name: "Unconditional", exact: true })).toBeChecked();
  await form.getByLabel("Offer date").fill(isoDaysAgo(1));
  await form.getByLabel("Offer date").press("Enter");
  await expect(detail.getByRole("status")).toHaveText("Offer saved.");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
