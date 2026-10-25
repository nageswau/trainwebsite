import { expect, test } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-037 (DEC-SCOPE-271, MT1-MT9): the Overseas Admin writes a counselor template; a counselor sends it to a walk-in student over
// WhatsApp from the student 360's Activities tab and records the student's reply by hand; the Overseas Admin reads the log read-only.
// Requires the stack running with `python -m app.seed` applied.

const ADMIN = ["overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard"] as const;

test("a template is sent to a student, a reply is recorded and the admin reads the log (ccrm-037)", async ({ page, context }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  const unique = Date.now();
  const template = `Welcome ${unique}`;
  const student = `Messaged Student ${unique}`;

  await signIn(page, ...ADMIN);
  await page.getByRole("link", { name: "Message templates" }).click();
  await expect(page).toHaveURL(/\/overseas\/admin\/message-templates$/);
  await expect(page.getByRole("heading", { name: "Message templates", level: 2 })).toBeVisible();
  await page.getByLabel("Template name (required)").fill(template);
  await page.getByLabel("Message (required)").fill("Hi {name}, this is {counselor}. Ask me anything.");
  await page.getByRole("button", { name: "Create template" }).click();
  await expect(page.getByRole("cell", { name: template })).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  await signInAsFreshCounselor(page, "ccrm037");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: student, email: `ccrm037-s-${unique}@example.local`, phone: "98765 43210" } });
  expect(created.status()).toBe(201);
  const studentId = (await created.json()).student.id as string;
  await page.goto(`/overseas/counselor/students/${studentId}?tab=activities`);
  const card = page.locator(".card").filter({ has: page.getByRole("heading", { name: "Communication" }) });
  await expect(card.getByText("No messages sent yet.")).toBeVisible();

  await card.getByRole("button", { name: "Send WhatsApp" }).click();
  const composer = card.getByRole("group", { name: "WhatsApp message" });
  await composer.getByLabel("Template").selectOption({ label: template });
  await expect(composer.getByLabel("Message")).toHaveValue(`Hi ${student}, this is ccrm037 Counselor. Ask me anything.`);
  const popup = context.waitForEvent("page");
  await composer.getByRole("link", { name: /Open WhatsApp/ }).click();
  const wa = await popup;
  expect(wa.url()).toContain("919876543210");
  await wa.close();
  await composer.getByRole("button", { name: "Yes, record as sent" }).click();
  await expect(card.getByText(`WhatsApp to ${student} recorded.`)).toBeVisible();

  await card.getByRole("button", { name: "Record a reply" }).click();
  const form = card.getByRole("form", { name: "Record a reply" });
  await form.getByLabel("Reply").fill("Thank you, I will send my transcripts.");
  await form.getByRole("button", { name: "Save reply" }).click();
  await expect(card.getByText("Reply recorded.")).toBeVisible();
  const log = card.getByRole("list", { name: "Messages" });
  await expect(log.getByRole("listitem")).toHaveCount(2);
  await expect(log.getByRole("listitem").filter({ hasText: "WhatsApp reply received" })).toContainText("Recorded by ccrm037 Counselor");
  await page.reload();
  await expect(card.getByRole("list", { name: "Messages" }).getByRole("listitem")).toHaveCount(2);
  expect(errors).toEqual([]);
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, ...ADMIN);
  await page.goto(`/overseas/admin/students/${studentId}?tab=activities`);
  const adminCard = page.locator(".card").filter({ has: page.getByRole("heading", { name: "Communication" }) });
  await expect(adminCard.getByRole("list", { name: "Messages" }).getByRole("listitem")).toHaveCount(2);
  await expect(adminCard.getByRole("button", { name: "Send WhatsApp" })).toHaveCount(0);
  await expect(adminCard.getByRole("button", { name: "Record a reply" })).toHaveCount(0);
  const refused = await page.request.post(`/api/v1/counselor/students/${studentId}/messages`, { data: { channel: "whatsapp", body: "Hi" } });
  expect(refused.status()).toBe(403);
});

test("the Communication card fits a phone screen without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signInAsFreshCounselor(page, "ccrm037m");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: "Phone Student", email: `ccrm037-m-${Date.now()}@example.local` } });
  const studentId = (await created.json()).student.id as string;
  await page.goto(`/overseas/counselor/students/${studentId}?tab=activities`);
  await expect(page.getByRole("heading", { name: "Communication" })).toBeVisible();
  await expect(page.getByText("No usable mobile number for Phone Student.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
