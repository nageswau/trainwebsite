import { expect, test, type Page } from "@playwright/test";

// pob-012 (DEC-SCOPE-433): a recruiter records a vendor's bills and payments on the vendor's page (W2/W3/W9), the server's refusals land on
// their fields, and the vendor performance report and drill-down show "—" rates for a vendor with no submissions (+/−/E). No sideways scroll.
const RECRUITER = "placement@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const today = () => new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10); // the server's IST day

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function recordBill(section: ReturnType<Page["locator"]>, number: string, amount: string, kind = "payable") {
  await section.getByRole("button", { name: "Record bill" }).click();
  const form = section.getByRole("form", { name: "Record bill" });
  await form.getByLabel("Type").selectOption(kind);
  await form.getByLabel("Bill number").fill(number);
  await form.getByLabel("Bill date").fill(today());
  await form.getByLabel("Payment due").fill(today());
  await form.getByLabel("Amount (₹)").fill(amount);
  await form.getByRole("button", { name: "Save bill" }).click();
}

test("a vendor's bills and payments are recorded, and the performance report shows dashes for no submissions", async ({ page }) => {
  test.setTimeout(150_000);
  const name = `POB12 Vendor ${Date.now()} Pvt`;
  await signIn(page, RECRUITER);
  await page.goto("/recruiter/companies/new?vendor=1");
  await page.getByLabel("Company name").fill(name);
  await page.getByRole("button", { name: /save|add company|create/i }).first().click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}/);
  const vendorId = page.url().split("?")[0].split("/").pop()!;

  const section = page.locator("section", { has: page.getByRole("heading", { name: "Vendor commercials" }) });
  await expect(section.getByText("No bills yet.")).toBeVisible();
  const number = `VB-${Date.now()}`;
  await recordBill(section, number, "10000");
  await expect(section.getByText("Bill saved.")).toBeVisible();
  await expect(section.getByText(number, { exact: true })).toBeVisible();

  // The number is unique per vendor ignoring case: the coded 409 shows its message.
  await recordBill(section, number.toLowerCase(), "500");
  await expect(section.getByRole("alert")).toHaveText("This vendor already has a bill with this number");
  await section.getByRole("button", { name: "Back" }).click();

  // A payment over the outstanding amount is refused on its field; a valid one is saved.
  await section.getByRole("button", { name: `Record payment for ${number}` }).click();
  const pay = section.getByRole("form", { name: `Record payment for ${number}` });
  await pay.getByLabel("Payment date").fill(today());
  await pay.getByLabel("Amount (₹)").fill("10000.01");
  await pay.getByRole("button", { name: "Save payment" }).click();
  await expect(pay.getByText(/more than the ₹10,000.00 outstanding/)).toBeVisible();
  await pay.getByLabel("Amount (₹)").fill("4000");
  await pay.getByLabel(/Reference/).fill("NEFT 42");
  await pay.getByRole("button", { name: "Save payment" }).click();
  await expect(section.getByText("Payment saved.")).toBeVisible();
  await expect(section.getByText("Part paid", { exact: true })).toBeVisible();
  await expect(section.getByText(/Billed ₹10,000.00 · Paid ₹4,000.00 · Outstanding ₹6,000.00/)).toBeVisible();

  // A receivable raised by mistake is cancelled with a reason.
  const other = `VR-${Date.now()}`;
  await recordBill(section, other, "2500", "receivable");
  await expect(section.getByText("Bill saved.")).toBeVisible();
  await section.getByRole("button", { name: `Cancel bill ${other}` }).click();
  await section.getByLabel("Reason").fill("Raised twice");
  await section.getByRole("button", { name: "Cancel bill" }).click();
  await expect(section.getByText("Bill cancelled.")).toBeVisible();
  await expect(section.getByText("Cancelled: Raised twice")).toBeVisible();

  // The drill-down: no submissions, so every rate is "—" (never 0%), and the payment history ties to the bills.
  await section.getByRole("link", { name: "Vendor performance" }).click();
  await page.waitForURL(`**/recruiter/vendors/${vendorId}/performance`);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  const figures = page.getByRole("region", { name: "Figures" });
  await expect(figures.getByText("— (0)").first()).toBeVisible();
  await expect(figures.getByText("0%")).toHaveCount(0);
  await expect(page.getByText("No candidates shared with this vendor yet.")).toBeVisible();
  await expect(page.getByText(/We owe the vendor: billed ₹10,000.00 · paid ₹4,000.00 · outstanding ₹6,000.00/)).toBeVisible();

  // The report lists the vendor and links back to the drill-down; it fits a phone.
  await page.goto("/recruiter/vendors");
  await page.getByRole("link", { name: "Vendor performance" }).click();
  await page.waitForURL("**/recruiter/vendors/performance");
  await expect(page.getByRole("heading", { name: "Vendor performance" })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 800 });
  expect(await noSideScroll(page)).toBe(true);
  await page.goto(`/recruiter/vendors/${vendorId}/performance`);
  expect(await noSideScroll(page)).toBe(true);
});

test("an unknown vendor's performance is a plain not found", async ({ page }) => {
  await signIn(page, RECRUITER);
  await page.goto("/recruiter/vendors/00000000-0000-0000-0000-000000000000/performance");
  await expect(page.getByRole("heading", { name: "Vendor not found" })).toBeVisible();
});
