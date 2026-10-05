import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Locator, type Page } from "@playwright/test";

import { shoot, signIn, toTop } from "./shoot";

// S7 (docs/documentation-plan.md): DOC-DOC-001..006 in "EduSphere Partner Agency". Runs after s6.
// Neha Sharma is assigned to Asha Staff (no permissions); Diya Nair is assigned to Bala Verifier (Verify documents) here.
const DOC = "documents";
const staffEmail = (key: string) => JSON.parse(readFileSync(String(process.env.DOCS_STAFF_FILE), "utf8"))[key] as string;
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
async function selectByText(select: Locator, text: string) {
  const value = await select.locator("option", { hasText: text }).first().getAttribute("value");
  await select.selectOption(value ?? "");
}
function file(name: string, pdf = true): string {
  const dir = path.resolve(__dirname, "../../test-results/doc-capture-files");
  mkdirSync(dir, { recursive: true });
  const f = path.join(dir, name);
  writeFileSync(f, pdf ? "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n" : "plain text, not a document\n");
  return f;
}
const uploadForm = (p: Page) => p.locator("form").filter({ has: p.getByRole("button", { name: "Upload document" }) }).first();
const requestForm = (p: Page) => p.locator("form").filter({ has: p.getByRole("button", { name: "Add request" }) }).first();
async function chooseStudent(p: Page, form: Locator, name: string) {
  await form.getByRole("combobox", { name: "Student" }).fill(name);
  await p.getByRole("option", { name: new RegExp(`^${name}`) }).first().click();
}
async function upload(p: Page, student: string, type: string, f: string, opts: { app?: string; description?: string; request?: string } = {}) {
  const form = uploadForm(p);
  await chooseStudent(p, form, student);
  await selectByText(form.getByLabel("Document type"), type);
  if (opts.description) await form.getByLabel(/^Description/).fill(opts.description);
  if (opts.app) await selectByText(form.getByLabel(/^Application/), opts.app);
  if (opts.request) await selectByText(form.getByLabel(/^Fulfils request/), opts.request);
  await form.getByLabel(/^File/).setInputFiles(f);
  await form.getByRole("button", { name: "Upload document" }).click();
}

test("S7 documents", async ({ browser }) => {
  test.setTimeout(300_000);
  const ctx = await browser.newContext();
  const m = await ctx.newPage();
  m.on("dialog", (d) => d.accept());
  await signIn(m, "agent@edusphere.local");

  // Diya Nair -> Bala Verifier (so a staff member with "Verify documents" has a student).
  await m.goto("/overseas/agent/students");
  await m.getByLabel("Search students").fill("Diya");
  await m.getByRole("button", { name: "Assign Diya Nair", exact: true }).click();
  await selectByText(m.getByLabel("Assign to"), "Bala Verifier");
  await m.getByRole("button", { name: "Save assignment" }).click();
  await expect(m.getByText("Diya Nair assigned to")).toBeVisible();

  // --- DOC-DOC-002 upload ---
  await m.goto("/overseas/agent/documents");
  await toTop(m.getByRole("heading", { name: "Pending review" }));
  await shoot(m, DOC, "01-documents-pending.png");
  await upload(m, "Neha Sharma", "Other", file("loan-letter.pdf"));
  await m.waitForTimeout(700);
  console.log(`VERIFY DOC-002 other without description: ${(await uploadForm(m).innerText()).replace(/\s+/g, " ").slice(0, 600)}`);
  await toTop(m.getByRole("heading", { name: "Upload document" }).first());
  await shoot(m, DOC, "04-upload-other-description.png");
  await uploadForm(m).getByLabel(/^Description/).fill("Bank loan sanction letter");
  await selectByText(uploadForm(m).getByLabel(/^Application/), "University of Manchester");
  await toTop(m.getByRole("heading", { name: "Upload document" }).first());
  await shoot(m, DOC, "03-upload-form.png");
  await uploadForm(m).getByRole("button", { name: "Upload document" }).click();
  await expect(m.getByText("Document uploaded. It is waiting for review.")).toBeVisible();
  await shoot(m, DOC, "05-upload-success.png");

  await m.reload();
  await upload(m, "Neha Sharma", "Passport", file("neha-passport.txt", false));
  await m.waitForTimeout(1200);
  await say(m, "DOC-002 wrong file type");
  await toTop(m.getByRole("heading", { name: "Upload document" }).first());
  await shoot(m, DOC, "06-upload-wrong-type.png");
  await m.reload();
  await upload(m, "Neha Sharma", "Offer letter", file("offer.pdf"));
  await m.waitForTimeout(1200);
  console.log(`VERIFY DOC-002 offer letter without application: ${(await uploadForm(m).innerText()).replace(/\s+/g, " ").slice(-300)}`);
  await m.reload();
  await upload(m, "Neha Sharma", "Passport", file("neha-passport.pdf"), { app: "University of Manchester" });
  await expect(m.getByText("Document uploaded. It is waiting for review.")).toBeVisible();
  await m.reload();
  await upload(m, "Diya Nair", "Transcripts", file("diya-transcripts.pdf"), { app: "Technical University of Munich" });
  await expect(m.getByText("Document uploaded. It is waiting for review.")).toBeVisible();

  // --- DOC-DOC-004 review (Master) ---
  await m.reload();
  await m.getByRole("button", { name: "Review Passport for Neha Sharma" }).click();
  console.log(`VERIFY DOC-004 review form: ${(await m.locator("form").filter({ has: m.getByRole("button", { name: "Save decision" }) }).innerText()).replace(/\s+/g, " ")}`);
  await m.getByLabel("Decision").selectOption({ label: "Rejected" });
  await m.getByRole("button", { name: "Save decision" }).click();
  await m.waitForTimeout(800);
  await say(m, "DOC-004 reject without reason");
  await shoot(m, DOC, "08-review-reason-required.png");
  await m.getByLabel(/^Reason/).fill("The scan is blurred. Please upload a clearer colour copy of the photo page.");
  await shoot(m, DOC, "07-review-form-master.png");
  await m.getByRole("button", { name: "Save decision" }).click();
  await expect(m.getByText("for Neha Sharma: rejected.")).toBeVisible();
  await m.getByRole("button", { name: "Review Bank loan sanction letter for Neha Sharma" }).click();
  await m.getByLabel("Decision").selectOption({ label: "Changes required" });
  await m.getByLabel(/^Reason/).fill("Please add the page with the bank's seal and signature.");
  await m.getByRole("button", { name: "Save decision" }).click();
  await expect(m.getByText("for Neha Sharma: changes required.")).toBeVisible();

  // --- DOC-DOC-001 uploaded view, reasons; download ---
  await m.goto("/overseas/agent/documents?view=uploaded");
  await expect(m.getByText("Reason:").first()).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Uploaded documents" }));
  await shoot(m, DOC, "02-documents-uploaded.png");
  const [popup] = await Promise.all([
    m.waitForEvent("popup", { timeout: 10_000 }).catch(() => null),
    m.getByRole("button", { name: "Download Passport for Neha Sharma" }).click(),
  ]);
  console.log(`VERIFY DOC-001 download opened a tab: ${Boolean(popup)}`);
  if (popup) await Promise.race([popup.close({ runBeforeUnload: false }), new Promise((r) => setTimeout(r, 3000))]).catch(() => {});

  // --- DOC-DOC-003 replace file ---
  await m.getByRole("button", { name: "Replace file of Passport for Neha Sharma" }).click();
  await m.getByLabel(/^New file/).setInputFiles(file("neha-passport-clear.pdf"));
  await shoot(m, DOC, "09-replace-file.png");
  await m.getByRole("button", { name: "Upload new file" }).click();
  await m.waitForTimeout(1000);
  await say(m, "DOC-003 replaced");
  await shoot(m, DOC, "10-replace-success.png");

  // --- DOC-DOC-005 history ---
  await m.getByRole("button", { name: "History of Passport for Neha Sharma" }).click();
  await m.waitForTimeout(1000);
  await shoot(m, DOC, "11-document-history.png");

  // --- DOC-DOC-006 requests ---
  await m.goto("/overseas/agent/documents?view=additional");
  const rq = requestForm(m);
  await chooseStudent(m, rq, "Neha Sharma");
  await selectByText(rq.getByLabel("Document type"), "SOP");
  await rq.getByLabel(/^Note for the file/).fill("One page; mention the healthcare analytics interest discussed in counseling.");
  await toTop(m.getByRole("heading", { name: "Request a document" }));
  await shoot(m, DOC, "12-request-form.png");
  await rq.getByRole("button", { name: "Add request" }).click();
  await expect(m.getByText("Request added to Additional documents.")).toBeVisible();
  await chooseStudent(m, rq, "Neha Sharma");
  await selectByText(rq.getByLabel("Document type"), "SOP");
  await rq.getByRole("button", { name: "Add request" }).click();
  await m.waitForTimeout(900);
  await say(m, "DOC-006 duplicate request");
  await chooseStudent(m, rq, "Neha Sharma");
  await selectByText(rq.getByLabel("Document type"), "LOR");
  await rq.getByRole("button", { name: "Add request" }).click();
  await expect(m.getByText("Request added to Additional documents.")).toBeVisible();
  await m.reload();
  await toTop(m.getByRole("heading", { name: /Additional documents/ }).last());
  await shoot(m, DOC, "13-additional-requests.png");
  await m.getByRole("button", { name: /^Cancel request.*LOR/ }).first().click();
  await m.waitForTimeout(900);
  await say(m, "DOC-006 cancelled");
  await shoot(m, DOC, "14-request-cancelled.png");
  await upload(m, "Neha Sharma", "SOP", file("neha-sop.pdf"), { request: "SOP" });
  await expect(m.getByText("Document uploaded. It is waiting for review.")).toBeVisible();
  await m.reload();
  console.log(`VERIFY DOC-006 after fulfil: ${(await m.locator("main").innerText()).split("Additional documents").pop()?.replace(/\s+/g, " ").slice(0, 300)}`);
  await ctx.close();

  // --- Staff with Verify documents (Bala) and without (Asha) ---
  let sctx = await browser.newContext();
  let s = await sctx.newPage();
  await signIn(s, staffEmail("b"), "test");
  await s.goto("/overseas/agent/documents");
  await s.getByRole("button", { name: "Review Transcripts for Diya Nair" }).click();
  await shoot(s, DOC, "15-review-staff-verify.png");
  await s.getByRole("button", { name: "Mark verified" }).click();
  await expect(s.getByText("for Diya Nair: verified.")).toBeVisible();
  await sctx.close();
  sctx = await browser.newContext();
  s = await sctx.newPage();
  await signIn(s, staffEmail("a"), "test");
  await s.goto("/overseas/agent/documents");
  console.log(`VERIFY DOC-004 staff without permission sees Review: ${await s.getByRole("button", { name: /^Review / }).count()}`);
  await toTop(s.getByRole("heading", { name: "Pending review" }));
  await shoot(s, DOC, "16-staff-no-verify.png");
  await sctx.close();
});
