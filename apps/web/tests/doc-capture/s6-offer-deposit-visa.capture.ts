import { createHmac, randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Locator, type Page } from "@playwright/test";

import { shoot, signIn, toTop } from "./shoot";

// S6 (docs/documentation-plan.md): DOC-APP-006..009 on "Aarav Mehta — University of Birmingham" (stage Offer, from s5).
// The deposit payment: the real Razorpay test checkout is opened and captured, then closed; the payment itself is
// completed with a signed Razorpay test webhook (exactly what Razorpay sends after a real payment), because driving
// Razorpay's own hosted window is outside this app. Runs after s5-applications.
const APP = "applications";
const STUDENT = "Aarav Mehta";
const UNI = "University of Birmingham";
const staffEmail = (key: string) => JSON.parse(readFileSync(String(process.env.DOCS_STAFF_FILE), "utf8"))[key] as string;
const day = (offset: number) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
};
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
async function selectByText(select: Locator, text: string) {
  const value = await select.locator("option", { hasText: text }).first().getAttribute("value");
  await select.selectOption(value ?? "");
}
function samplePdf(name: string): string {
  const dir = path.resolve(__dirname, "../../test-results/doc-capture-files");
  mkdirSync(dir, { recursive: true });
  const file = path.join(dir, name);
  const body = "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n";
  writeFileSync(file, body);
  return file;
}
async function upload(page: Page, type: string, file: string) {
  const form = page.locator("form").filter({ has: page.getByRole("button", { name: "Upload document" }) }).first();
  await form.getByRole("combobox", { name: "Student" }).fill(STUDENT);
  await page.getByRole("option", { name: new RegExp(`^${STUDENT}`) }).first().click();
  await selectByText(form.getByLabel("Document type"), type);
  await selectByText(form.getByLabel(/^Application/), UNI);
  await form.getByLabel(/^File/).setInputFiles(file);
  await form.getByRole("button", { name: "Upload document" }).click();
  await expect(page.getByText("Document uploaded. It is waiting for review.")).toBeVisible();
}
const openApp = async (page: Page) => {
  await page.goto("/overseas/agent/applications");
  await page.getByRole("button", { name: `View ${STUDENT} — ${UNI}` }).click();
  await expect(page.getByRole("heading", { name: "Status history" })).toBeVisible();
};

test("S6 offer, deposit, visa, enrollment", async ({ browser }) => {
  test.setTimeout(300_000);
  const ctx = await browser.newContext();
  const m = await ctx.newPage();
  m.on("dialog", (d) => d.accept());
  await signIn(m, "agent@edusphere.local");

  // Documents the offer and visa steps need (uploaded and verified through the Documents page).
  await m.goto("/overseas/agent/documents");
  await upload(m, "Offer letter", samplePdf("birmingham-offer-letter.pdf"));
  await upload(m, "Passport", samplePdf("aarav-passport.pdf"));
  await upload(m, "Financial documents", samplePdf("aarav-bank-statement.pdf"));
  await m.reload();
  for (const doc of ["Passport", "Financial documents"]) {
    await m.getByRole("button", { name: new RegExp(`^Review ${doc}.* for ${STUDENT}`) }).first().click();
    await m.getByLabel("Verified", { exact: true }).check().catch(() => {});
    await m.getByRole("button", { name: "Save decision" }).click();
    await expect(m.getByText(new RegExp(`for ${STUDENT}: verified\\.`))).toBeVisible();
  }

  // --- DOC-APP-006 offer ---
  await openApp(m);
  await m.getByRole("button", { name: "Record offer" }).click();
  await m.getByLabel("Conditional", { exact: true }).check();
  await m.getByLabel("Offer date").fill(day(-1));
  await m.getByRole("button", { name: "Save offer" }).click();
  await m.waitForTimeout(800);
  console.log(`VERIFY APP-006 conditional without conditions: ${(await m.locator("form").filter({ has: m.getByRole("button", { name: "Save offer" }) }).innerText()).replace(/\s+/g, " ")}`);
  await toTop(m.getByRole("heading", { name: "Offer", exact: true }));
  await shoot(m, APP, "20-offer-conditions-required.png");
  await m.getByLabel(/^Conditions/).fill("IELTS 6.5 overall with no band below 6.0\nFinal transcript showing 60% or above by 31 July 2027");
  await m.getByLabel("Offer deadline (optional)").fill(day(30));
  await selectByText(m.getByLabel(/^Offer letter/), "birmingham-offer-letter.pdf");
  await toTop(m.getByRole("heading", { name: "Offer", exact: true }));
  await shoot(m, APP, "21-offer-form.png");
  await m.getByRole("button", { name: "Save offer" }).click();
  await expect(m.getByText("Offer saved.")).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Offer", exact: true }));
  await shoot(m, APP, "22-offer-saved.png");

  // --- DOC-APP-007 deposit ---
  await m.getByRole("button", { name: "Record deposit" }).click();
  await m.getByLabel("Yes", { exact: true }).check();
  await m.getByLabel(/^Amount in/).fill("0");
  await m.getByRole("button", { name: "Save deposit" }).click();
  await m.waitForTimeout(600);
  console.log(`VERIFY APP-007 zero amount: ${(await m.locator("form").filter({ has: m.getByRole("button", { name: "Save deposit" }) }).innerText()).replace(/\s+/g, " ")}`);
  await toTop(m.getByRole("heading", { name: "Deposit", exact: true }));
  await shoot(m, APP, "23-deposit-amount-error.png");
  await m.getByLabel(/^Amount in/).fill("50000");
  await m.getByLabel(/^Due date/).fill(day(14));
  await shoot(m, APP, "24-deposit-form.png");
  await m.getByRole("button", { name: "Save deposit" }).click();
  await expect(m.getByText("Deposit saved.")).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Deposit", exact: true }));
  await shoot(m, APP, "25-deposit-awaiting-payment.png");

  const [checkout] = await Promise.all([
    m.waitForResponse((r) => r.request().method() === "POST" && r.url().includes("/deposit/checkout")),
    m.getByRole("button", { name: "Pay deposit" }).click(),
  ]);
  const order = await checkout.json();
  console.log(`VERIFY APP-007 checkout status ${checkout.status()} keys ${Object.keys(order).join(",")}`);
  const rzp = m.frameLocator("iframe.razorpay-checkout-frame");
  await rzp.locator("body").waitFor({ timeout: 20_000 }).catch(() => console.log("VERIFY APP-007 Razorpay frame did not appear"));
  await m.waitForTimeout(4000);
  await shoot(m, APP, "26-razorpay-checkout.png");
  // Close Razorpay's window with its own controls: dismiss the contact prompt, then the window, then confirm exit.
  for (let i = 0; i < 4; i++) {
    const closer = rzp.locator('[aria-label*="close" i], [data-testid*="close" i], button:has-text("×"), svg[aria-label*="close" i]').first();
    await closer.click({ timeout: 2500 }).catch(() => {});
    await rzp.getByRole("button", { name: /^(yes|exit|yes, exit|yes, cancel)/i }).first().click({ timeout: 1500 }).catch(() => {});
    await m.waitForTimeout(1200);
    if (!(await m.locator("iframe.razorpay-checkout-frame").isVisible().catch(() => false))) break;
  }
  console.log(`VERIFY APP-007 Razorpay window still open: ${await m.locator("iframe.razorpay-checkout-frame").isVisible().catch(() => false)}`);

  // Complete the test payment the way Razorpay does: a signed payment.captured webhook for the order.
  const orderId = String(order.provider_order_id ?? order.order_id ?? "");
  expect(orderId).not.toBe("");
  const body = JSON.stringify({
    event: "payment.captured",
    payload: { payment: { entity: { id: `pay_docs${Date.now()}`, order_id: orderId, status: "captured", amount: 5_000_000, currency: "INR" } } },
  });
  const sig = createHmac("sha256", String(process.env.DOCS_RAZORPAY_WEBHOOK_SECRET)).update(body).digest("hex");
  const hook = await m.request.post(`${process.env.DOCS_API_URL}/api/v1/payments/webhooks/razorpay`, {
    data: body,
    headers: { "content-type": "application/json", "x-razorpay-signature": sig, "x-razorpay-event-id": `evt_docs_${randomUUID()}` },
  });
  console.log(`VERIFY APP-007 webhook ${hook.status()} ${await hook.text()}`);
  await openApp(m);
  await expect(m.getByText(/Paid/).first()).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Deposit", exact: true }));
  await shoot(m, APP, "28-deposit-paid.png");

  // --- DOC-APP-008 visa ---
  await m.getByRole("button", { name: "Start visa case" }).click();
  await m.getByLabel("Visa application date (optional)").fill(day(-1));
  await m.getByLabel("Appointment date (optional)").fill(day(10));
  for (const doc of ["Passport", "Financial documents", "English test"]) await m.getByLabel(doc, { exact: true }).check();
  await toTop(m.getByRole("heading", { name: "Visa", exact: true }));
  await shoot(m, APP, "29-visa-start-form.png");
  await m.getByRole("button", { name: "Start visa case" }).click();
  await expect(m.getByText("Visa case started.")).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Visa", exact: true }));
  await shoot(m, APP, "30-visa-checklist.png");
  await m.getByRole("button", { name: "Move visa stage" }).click();
  await selectByText(m.getByLabel("Move to").last(), "Documentation");
  await m.getByRole("button", { name: "Move", exact: true }).click();
  await m.waitForTimeout(800);
  await say(m, "APP-008 checklist gate");
  await toTop(m.getByRole("heading", { name: "Visa", exact: true }));
  await shoot(m, APP, "31-visa-checklist-gate.png");
  await m.getByRole("button", { name: "Cancel" }).first().click().catch(() => {});
  await m.getByRole("button", { name: "Edit visa details" }).click();
  await m.getByLabel("English test", { exact: true }).uncheck();
  await m.getByLabel("Interview date (optional)").fill(day(12));
  await m.getByRole("button", { name: "Save visa details" }).click();
  await expect(m.getByText("Visa details saved.")).toBeVisible();
  await m.getByRole("button", { name: "Move visa stage" }).click();
  await selectByText(m.getByLabel("Move to").last(), "Decision");
  await m.getByRole("button", { name: "Move", exact: true }).click();
  await toTop(m.getByRole("heading", { name: "Visa", exact: true }));
  await shoot(m, APP, "32-visa-skip-confirm.png");
  await m.getByRole("button", { name: "Yes, move" }).click();
  await m.waitForTimeout(800);
  await m.getByRole("button", { name: "Record decision" }).first().click();
  await m.getByLabel("Approved", { exact: true }).check();
  await m.getByRole("button", { name: "Record decision" }).last().click();
  await toTop(m.getByRole("heading", { name: "Visa", exact: true }));
  await shoot(m, APP, "33-visa-decision-confirm.png");
  await m.getByRole("button", { name: "Yes, record decision" }).click();
  await expect(m.getByText("Visa decision recorded.")).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Visa", exact: true }));
  await shoot(m, APP, "34-visa-decision-recorded.png");

  // --- DOC-APP-009 enrollment ---
  await m.getByRole("button", { name: "Enroll student" }).click();
  await m.getByLabel("Enrollment date (required)").fill("2027-12-15");
  await m.getByLabel("University student ID (optional)").fill("2027-BHM-55120");
  await m.waitForTimeout(500);
  await toTop(m.getByRole("heading", { name: "Enrollment", exact: true }));
  await shoot(m, APP, "35-enrollment-form.png");
  await m.getByLabel("Enrollment date (required)").fill(day(0));
  await m.getByLabel("Note (optional)").last().fill("Enrolment confirmed by the university's admissions team by email.");
  await m.getByRole("button", { name: "Confirm enrollment" }).click();
  await toTop(m.getByRole("heading", { name: "Enrollment", exact: true }));
  await shoot(m, APP, "36-enrollment-confirm.png");
  await m.getByRole("button", { name: "Yes, confirm enrollment" }).click();
  await expect(m.getByText("Enrollment confirmed.")).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Enrollment", exact: true }));
  await shoot(m, APP, "37-enrolled.png");
  await m.goto("/overseas/agent/applications?status=enrolled");
  await shoot(m, APP, "38-filter-enrolled.png");
  await ctx.close();

  // --- Staff: enrollment is Master-only ---
  const sctx = await browser.newContext();
  const s = await sctx.newPage();
  await signIn(s, staffEmail("a"), "test");
  await s.goto("/overseas/agent/applications");
  await s.getByRole("button", { name: "View Neha Sharma — Monash University" }).click();
  await selectByText(s.getByLabel("Move to"), "Offer");
  await s.getByRole("button", { name: "Update status" }).click();
  await expect(s.getByText("Status updated to Offer.")).toBeVisible();
  await expect(s.getByText("An agency Master confirms enrollment.")).toBeVisible();
  await toTop(s.getByRole("heading", { name: "Enrollment", exact: true }));
  await shoot(s, APP, "39-enrollment-staff-note.png");
  await sctx.close();
});
