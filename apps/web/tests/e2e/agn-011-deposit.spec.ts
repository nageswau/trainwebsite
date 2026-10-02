import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { pickFromList } from "./helpers/pick";

// AGN-011 -- the deposit on an agency application for a student with no login. CI and local E2E run without Razorpay keys, so this
// covers AC6 (payment unavailable, nothing marked paid), recording and editing the deposit, the admin Agent deposits page and 320 px.
// A real Razorpay checkout needs TEST keys and is tagged @external (the PAY-001 precedent). Unique names per run (shared E2E DB).
// Requires `python -m app.seed`.
const stamp = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

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

async function openDeposit(page: Page, name: string) {
  await page.goto("/overseas/agent/applications");
  await page.getByRole("list", { name: "Applications", exact: true }).getByRole("button", { name: new RegExp(`^View ${name} — `) }).click();
  return page.getByRole("region", { name: new RegExp(`^${name} — `) }).getByRole("region", { name: "Deposit", exact: true });
}

test("a Master records a deposit; with Razorpay unconfigured the page says payment is unavailable and nothing is paid (AC6)", async ({ page }) => {
  test.setTimeout(120_000);
  const name = `E2E Deposit ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await studentWithApplication(page, name);

  const deposit = await openDeposit(page, name);
  await expect(deposit.getByText("No deposit recorded yet.")).toBeVisible();
  await deposit.getByRole("button", { name: "Record deposit" }).click();
  const form = deposit.getByRole("form", { name: "Record deposit" });
  await expect(form.getByLabel("Yes")).toBeFocused();
  await form.getByLabel("Yes").check();
  await form.getByLabel("Amount in ₹ (INR)").fill("50000");
  await form.getByRole("button", { name: "Save deposit" }).click();
  await expect(page.getByText("Deposit saved.")).toBeVisible();
  await expect(deposit.getByText("₹50,000.00")).toBeVisible();
  await expect(deposit.getByText("Awaiting payment")).toBeVisible();

  // The API says whether Razorpay is configured; CI has no keys, so the notice replaces the Pay button there.
  const list = await (await page.request.get("/api/v1/workflows/overseas/agent/crm/applications?limit=100")).json();
  const app = list.items.find((i: { student: string }) => i.student === name);
  const { application } = await (await page.request.get(`/api/v1/workflows/overseas/agent/crm/applications/${app.id}`)).json();
  if (application.payment_available) {
    test.info().annotations.push({ type: "note", description: "Razorpay keys are configured here; AC6 is covered by the API and component tests." });
    await expect(deposit.getByRole("button", { name: "Pay deposit" })).toBeVisible();
  } else {
    await expect(deposit.getByText("Online payment is unavailable right now. Nothing has been charged.")).toBeVisible();
    await expect(deposit.getByRole("button", { name: "Pay deposit" })).toHaveCount(0);
    const checkout = await page.request.post(`/api/v1/workflows/overseas/agent/crm/applications/${app.id}/deposit/checkout`, { headers: { "Idempotency-Key": crypto.randomUUID() } });
    expect(await checkout.json()).toEqual({ status: "configuration_required" });
  }
  await expect(deposit.getByText("Paid", { exact: true })).toHaveCount(0);
  expect(application.deposit.status).toBe("pending");
});

test("a Master edits the deposit to not required, keyboard only", async ({ page }) => {
  test.setTimeout(120_000);
  const name = `E2E Deposit Kbd ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await studentWithApplication(page, name);
  const deposit = await openDeposit(page, name);
  await deposit.getByRole("button", { name: "Record deposit" }).focus();
  await page.keyboard.press("Enter");
  const form = deposit.getByRole("form", { name: "Record deposit" });
  await page.keyboard.press("ArrowDown"); // Yes -> No within the radio group
  await expect(form.getByLabel("No")).toBeChecked();
  await form.getByRole("button", { name: "Save deposit" }).focus();
  await page.keyboard.press("Enter");
  await expect(deposit.getByText("Not required")).toBeVisible();
  await expect(deposit.getByRole("heading", { name: "Deposit" })).toBeFocused();
});

test("Overseas Admin opens Agent deposits from the sidebar", async ({ page }) => {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/dashboard");
  await page.getByRole("link", { name: "Agent deposits" }).first().click();
  await expect(page.getByRole("heading", { name: "Agent deposits", level: 2 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Paid", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(/No deposits with this status\.|Showing \d+/)).toBeVisible();
});

test("the deposit block fits a 320 px screen", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 320, height: 800 });
  const name = `E2E Deposit 320 ${stamp()}`;
  await signIn(page, "agent@edusphere.local", "Demo@123");
  await studentWithApplication(page, name);
  const deposit = await openDeposit(page, name);
  await deposit.getByRole("button", { name: "Record deposit" }).click();
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(320);
});
