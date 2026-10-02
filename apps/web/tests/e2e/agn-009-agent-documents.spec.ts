import { expect, test, type Page } from "@playwright/test";

import { pickFromList } from "./helpers/pick";
import { signIn } from "./helpers/agency";

// AGN-009 -- an agency's documents for a student with no login: request (Additional) -> upload against it (fulfilled) -> Pending ->
// reject needs a reason -> history in order -> download; 320 px. Unique names per run (shared E2E DB). Requires `python -m app.seed`.
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
const PDF = { name: "lor.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n") };

async function addNoLoginStudent(page: Page, name: string) {
  await page.goto("/overseas/agent/students");
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();
}

test("a Master requests, uploads against the request, rejects with a reason and reads the history (AC1-AC5)", async ({ page }) => {
  test.setTimeout(120_000);
  const name = `E2E Docs ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await addNoLoginStudent(page, name);

  // Request -> shows under Additional (AC4).
  await page.goto("/overseas/agent/documents?view=additional");
  const requestForm = page.getByRole("form", { name: "Request a document" });
  await pickFromList(requestForm.getByRole("combobox", { name: "Student" }), name, new RegExp(`^${name} — no login$`));
  await requestForm.getByLabel("Document type").selectOption("LOR");
  await requestForm.getByLabel("Note for the file (optional)").fill("Signed by the principal");
  await requestForm.getByRole("button", { name: "Add request" }).click();
  await expect(requestForm.getByRole("status")).toHaveText("Request added to Additional documents.");
  const open = page.getByRole("list", { name: "Open requests" });
  await expect(open).toContainText(name);
  await expect(page.locator(".portal-nav").getByRole("link", { name: "Additional" })).toHaveAttribute("aria-current", "page");

  // Upload against it -> the request leaves Additional (AC4), the document is pending (AC1).
  const uploadForm = page.getByRole("form", { name: "Upload document" });
  await pickFromList(uploadForm.getByRole("combobox", { name: "Student" }), name, new RegExp(`^${name} — no login$`));
  await uploadForm.getByLabel("Document type").selectOption("LOR");
  await expect(uploadForm.getByLabel("Fulfils request (optional)")).toBeEnabled(); // the student's open requests load after the pick
  await uploadForm.getByLabel("Fulfils request (optional)").selectOption({ label: "LOR" });
  await uploadForm.getByLabel("File (PDF, JPEG or PNG)").setInputFiles(PDF);
  await uploadForm.getByRole("button", { name: "Upload document" }).click();
  await expect(uploadForm.getByRole("status")).toHaveText("Document uploaded. It is waiting for review.");
  await expect(open.filter({ hasText: name })).toHaveCount(0);

  await page.locator(".portal-nav").getByRole("link", { name: "Pending" }).click();
  const card = page.getByRole("list", { name: "Pending review" }).locator(".card", { hasText: name });
  await expect(card).toContainText("Pending review");

  // Reject needs a reason (AC3, client-side required; the server answers 422 too).
  await card.getByRole("button", { name: `Review LOR for ${name}` }).click();
  await card.getByLabel("Decision").selectOption("rejected");
  await card.getByRole("button", { name: "Save decision" }).click();
  await expect(card.getByLabel("Reason (required)")).toHaveJSProperty("validity.valueMissing", true);
  await card.getByLabel("Reason (required)").fill("Unsigned copy");
  await card.getByRole("button", { name: "Save decision" }).click();
  await expect(page.getByRole("status").filter({ hasText: `LOR for ${name}` })).toContainText("rejected.");
  await expect(card).toHaveCount(0); // left Pending

  // Uploaded view: status, reason, download, history in order (AC5).
  await page.locator(".portal-nav").getByRole("link", { name: "Uploaded" }).click();
  const uploaded = page.getByRole("list", { name: "Uploaded documents" }).locator(".card", { hasText: name });
  await expect(uploaded).toContainText("Rejected");
  await expect(uploaded).toContainText("Reason: Unsigned copy");
  const [popup] = await Promise.all([page.waitForEvent("popup"), uploaded.getByRole("button", { name: `Download LOR for ${name}` }).click()]);
  expect(popup.url()).not.toBe("about:blank");
  await popup.close();
  await uploaded.getByRole("button", { name: `History of LOR for ${name}` }).click();
  const steps = uploaded.getByRole("list", { name: `History of LOR for ${name}` }).getByRole("listitem");
  await expect(steps).toHaveCount(5);
  await expect(steps.nth(0)).toContainText("Requested");
  await expect(steps.nth(1)).toContainText("Uploaded");
  await expect(steps.nth(2)).toContainText("Request fulfilled");
  await expect(steps.nth(3)).toContainText("Rejected");
  await expect(steps.nth(4)).toContainText("Downloaded");
});

test("the Documents page has no horizontal scroll at 320 px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await page.goto("/overseas/agent/documents?view=uploaded");
  await expect(page.getByRole("heading", { name: "Documents", level: 2 })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
