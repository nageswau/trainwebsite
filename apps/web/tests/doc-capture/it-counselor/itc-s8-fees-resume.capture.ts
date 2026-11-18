import { writeFileSync } from "node:fs";
import path from "node:path";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { ITC_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// IT Counselor CRM S8 (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-FEE-001, FEE-002, ADM-008 (screens only), ADM-009, ADM-010,
// RES-001, RES-002, ADM-012, HO-004. Runs after itc-s7. Owner I3: NO payment, refund or correction is recorded -- the IT Admin payment
// forms are captured empty and never submitted. A discount request/approval changes the fee owed; it records no payment.
const root = ITC_ROOT;
const A = "docs.itc.a@example.test";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1800);
const sec = (p: Page, heading: string | RegExp) =>
  p.getByRole("heading", typeof heading === "string" ? { name: heading, exact: true } : { name: heading }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const pdf = (name: string, line: string) => {
  const file = path.join(path.dirname(process.env.DOCS_ITC_FILE!), name);
  const body = `BT /F1 18 Tf 72 720 Td (${line}) Tj ET`;
  writeFileSync(file, `%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length ${body.length}>>stream\n${body}\nendstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n`);
  return file;
};

test("IT Counselor CRM S8 fees, resume and HR", async ({ browser }) => {
  test.setTimeout(900_000);
  const a = await ctxPage(browser);
  await signIn(a, "itadmin@edusphere.local", "seed", /\/it\/admin\//, "/it/login");
  await a.goto("/it/admin/students");
  await settle(a);
  const idOf = async (name: string) => (await a.locator("tr", { hasText: name }).first().getByRole("link", { name: "Open" }).getAttribute("href"))!.split("/").pop()!;
  const ids = { arjun: await idOf("Docs IT Lead Arjun"), bhavna: await idOf("Docs IT Student Bhavna") };

  // ===== ADM-012 HR review rule (before any resume is shared) =====
  await a.goto("/it/admin/hr-reviews");
  await settle(a);
  const rule = a.getByLabel("HR reviewer for Docs Full Stack Python");
  console.log(`VERIFY ADM-012 options: ${(await rule.locator("option").allInnerTexts()).join(" | ")}`);
  const pv = await rule.locator("option", { hasText: "Priya HR" }).first().getAttribute("value");
  await rule.selectOption(pv!);
  await settle(a, 2000);
  await say(a, "ADM-012 rule");
  await shoot(a, "admin", "30-hr-review-rules.png", { root, element: sec(a, "Review assignment rules") });

  // ===== Counselor A: FEE-001, FEE-002, RES-001 =====
  const c = await ctxPage(browser);
  await signIn(c, A, "test", /\/it\/counselor\/dashboard/, "/it/login");
  const profile = async (key: "arjun" | "bhavna") => { await c.goto(`/it/counselor/students/${ids[key]}/profile`); await settle(c, 2500); };
  await profile("arjun");
  const fees = sec(c, "Fees and reminders");
  console.log(`VERIFY FEE-001 card: ${await text(fees)}`);
  await shoot(c, "fees", "01-fee-summary.png", { root, element: fees });
  const discOf = (p: Page) => p.getByRole("region", { name: "Discounts and waivers" }).first();
  const disc = discOf(c);
  await c.getByRole("button", { name: "Request discount" }).click();
  await settle(c, 800);
  await say(c, "FEE-002 empty");
  await c.getByLabel("Discount amount (INR)").fill("5000");
  await c.getByRole("button", { name: "Request discount" }).click();
  await settle(c, 800);
  await say(c, "FEE-002 no reason");
  await c.getByLabel("Reason", { exact: true }).fill("Early-bird offer for the November batch");
  await shoot(c, "fees", "02-discount-request-form.png", { root, element: disc });
  await c.getByRole("button", { name: "Request discount" }).click();
  await settle(c, 2000);
  await say(c, "FEE-002 requested");
  console.log(`VERIFY FEE-002 after: ${await text(disc)}`);
  await shoot(c, "fees", "03-discount-requested.png", { root, element: disc });

  // RES-001 resume v1 (not shared), v2 (shared with HR)
  const res = c.locator('section[aria-labelledby="student-resume-heading"]');
  await res.getByRole("button", { name: "Upload", exact: true }).click();
  await settle(c, 800);
  await say(c, "RES-001 no file");
  const share = res.getByRole("checkbox", { name: "Share with HR" });
  console.log(`VERIFY RES-001 share default: ${await share.isChecked()}`);
  await share.setChecked(false);
  await c.locator("#student-resume-file").setInputFiles(pdf("docs-arjun-resume-v1.pdf", "Docs IT Lead Arjun - Resume v1"));
  await shoot(c, "resume", "01-resume-upload.png", { root, element: res });
  await res.getByRole("button", { name: "Upload", exact: true }).click();
  await settle(c, 2500);
  await say(c, "RES-001 v1");
  await c.locator("#student-resume-file").setInputFiles(pdf("docs-arjun-resume-v2.pdf", "Docs IT Lead Arjun - Resume v2"));
  await share.setChecked(true);
  await shoot(c, "resume", "02-resume-new-version-share.png", { root, element: res });
  await res.getByRole("button", { name: "Upload", exact: true }).click();
  await settle(c, 3000);
  await say(c, "RES-001 v2");
  console.log(`VERIFY RES-001 card: ${await text(res)}`);
  await shoot(c, "resume", "03-resume-versions.png", { root, element: res });
  await c.reload();
  await settle(c, 2500);
  console.log(`VERIFY RES-002 card: ${await text(sec(c, /^HR review/))}`);
  await shoot(c, "resume", "04-hr-review-received.png", { root, element: sec(c, /^HR review/) });

  // Bhavna: a second discount request, to be rejected
  await profile("bhavna");
  await c.getByLabel("Discount amount (INR)").fill("3000");
  await c.getByLabel("Reason", { exact: true }).fill("Sibling already studying with EduSphere");
  await c.getByRole("button", { name: "Request discount" }).click();
  await settle(c, 2000);
  await say(c, "FEE-002 Bhavna requested");

  // ===== IT Admin: ADM-009 discount approvals, ADM-010 reminders, ADM-008 screens only =====
  await a.goto("/it/admin/payments");
  await settle(a, 2500);
  const q = sec(a, "Discount approvals");
  console.log(`VERIFY ADM-009 queue: ${await text(q)}`);
  await shoot(a, "admin", "31-discount-approvals.png", { root, element: q });
  await q.getByRole("button", { name: "Approve discount for Docs IT Lead Arjun" }).click();
  await settle(a, 2500);
  await say(a, "ADM-009 approved");
  await q.getByRole("button", { name: "Reject discount for Docs IT Student Bhavna" }).click();
  await settle(a, 1000);
  await say(a, "ADM-009 reject no note");
  await q.getByLabel("Note for Docs IT Student Bhavna").fill("The sibling offer applies from the next batch.");
  await shoot(a, "admin", "32-discount-reject-note.png", { root, element: q });
  await q.getByRole("button", { name: "Reject discount for Docs IT Student Bhavna" }).click();
  await settle(a, 2500);
  await say(a, "ADM-009 rejected");
  await shoot(a, "admin", "33-discount-decided.png", { root, element: q });

  const rem = sec(a, "Fee reminders");
  console.log(`VERIFY ADM-010 card: ${await text(rem)}`);
  const before = await rem.getByLabel("Days before the due date").inputValue();
  const after = await rem.getByLabel("Days after the due date").inputValue();
  await rem.getByLabel("Days after the due date").fill("1, 7, 120");
  await rem.getByRole("button", { name: "Update reminder schedule" }).click();
  await settle(a, 1200);
  await say(a, "ADM-010 invalid");
  await shoot(a, "admin", "34-fee-reminders-invalid.png", { root, element: rem });
  await rem.getByLabel("Days after the due date").fill(after);
  await rem.getByLabel("Days before the due date").fill(before);
  await rem.getByRole("button", { name: "Update reminder schedule" }).click();
  await settle(a, 2000);
  await say(a, "ADM-010 saved");
  await shoot(a, "admin", "35-fee-reminders.png", { root, element: rem });

  // ADM-008: screens only, nothing filled or submitted
  await a.goto("/it/admin/payments");
  await settle(a, 2500);
  await shoot(a, "admin", "36-payments-list.png", { root, element: a.locator("main .workspace").first() });
  for (const [h, f] of [
    ["Record enrolment payment", "37-record-payment-form.png"],
    ["Record fee adjustment", "38-fee-adjustment-form.png"],
    ["Correct a recorded payment", "39-correct-payment-form.png"],
    ["Create payment due", "40-create-payment-due-form.png"],
    ["Apply discount", "41-apply-discount-form.png"],
    ["Student access by payment", "42-student-access-by-payment.png"],
  ] as const) {
    console.log(`VERIFY ADM-008 ${h}: ${await text(sec(a, h))}`);
    await shoot(a, "admin", f, { root, element: sec(a, h) });
  }

  // Counselor sees the decisions
  await profile("arjun");
  console.log(`VERIFY FEE-002 Arjun after approval: ${await text(sec(c, "Fees and reminders"))}`);
  await shoot(c, "fees", "04-discount-approved.png", { root, element: sec(c, "Fees and reminders") });
  await profile("bhavna");
  console.log(`VERIFY FEE-002 Bhavna after rejection: ${await text(sec(c, "Fees and reminders"))}`);
  await shoot(c, "fees", "05-discount-rejected.png", { root, element: discOf(c) });

  // ===== HO-004: Priya HR works the review =====
  const h = await ctxPage(browser);
  await signIn(h, "hr@edusphere.local", "seed", /\/it\/hr\//, "/it/login");
  await h.goto("/it/hr/queue");
  await settle(h, 2500);
  console.log(`VERIFY HO-004 queue: ${await text(h.locator("main"))}`);
  await shoot(h, "handoffs", "10-hr-review-queue.png", { root });
  await h.getByRole("link", { name: /Docs IT Lead Arjun/ }).first().click();
  await settle(h, 3000);
  console.log(`VERIFY HO-004 student page: ${await text(h.locator("main"))}`);
  const card = sec(h, "Resume review");
  await card.getByLabel("Stage").selectOption({ label: "Under review" });
  const boxes = card.locator('input[type="checkbox"]');
  await boxes.nth(0).check();
  await boxes.nth(1).check();
  await card.getByLabel("Role preferences").fill("Python developer, Backend developer");
  await card.getByLabel(/Skill-gap notes/).fill("Add a Django project with tests; list SQL skills.");
  await shoot(h, "handoffs", "11-hr-review-form.png", { root, element: card });
  await card.getByRole("button", { name: "Save review" }).click();
  await settle(h, 2500);
  await say(h, "HO-004 under review");
  await card.getByLabel("Stage").selectOption({ label: "Changes requested" });
  await card.getByRole("button", { name: "Save review" }).click();
  await settle(h, 2500);
  await say(h, "HO-004 changes requested");
  await shoot(h, "handoffs", "12-hr-review-changes-requested.png", { root, element: card });

  // Counselor sees the HR stage
  await profile("arjun");
  console.log(`VERIFY RES-002 after HR: ${await text(sec(c, /^HR review/))}`);
  await shoot(c, "resume", "05-hr-review-changes-requested.png", { root, element: sec(c, /^HR review/) });
  await c.goto("/it/counselor/notifications");
  await settle(c);
  console.log(`VERIFY S8 notifications: ${await text(c.locator("main"))}`);
});
