import { expect, test, type Page } from "@playwright/test";

// pob-024 (DEC-SCOPE-432; AC1-AC3): the seeded recruiter accepts an offer -> one placement in "Joining pending" with an "Open placement"
// link; a client confirmation is recorded; the candidate joins -> an invoice draft (unpriced here: no fee terms, so the amount is
// entered on issue); issuing it shows the invoice in Receivables. The manager reads the placement (no confirmation writes). Phone width
// holds. The notices (AC4), scope and the commercial gate are covered by test_pob_024_placements.py and the component tests.

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
}

const istToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

test("placement: accept -> record, confirm, join -> draft, issue -> receivables; manager reads; mobile", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const name = `E2E Placed ${stamp}`;
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  await signIn(page, "it", "placement@edusphere.local");

  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Pob024 ${stamp} Ltd` } });
  expect(company.ok()).toBeTruthy();
  const created = await page.request.post("/api/v1/recruiter/requirements", {
    data: { company_id: (await company.json()).company.id, title: `Java Developer ${stamp}`, location: "Pune", vacancies: 2 },
  });
  expect(created.ok()).toBeTruthy();
  const requirementId = (await created.json()).requirement.id as string;

  await page.goto("/recruiter/candidates/new");
  await page.locator("#cand-name").fill(name);
  await page.locator("#cand-mobile").fill(`9${String(stamp).slice(-9)}`);
  await page.locator("#cand-source_id").selectOption({ index: 1 });
  await page.locator("#cand-lawful_basis").selectOption("provided_for_placement");
  await page.getByRole("button", { name: "Add candidate" }).click();
  await page.waitForURL(/\/recruiter\/candidates\/[0-9a-f-]{36}/);
  const candidateId = page.url().split("/").at(-1)?.split("?")[0];
  const added = await page.request.post(`/api/v1/recruiter/requirements/${requirementId}/candidates`, { data: { candidate_id: candidateId, status: "shortlisted" } });
  const applicationId = (await added.json()).application.id as string;
  expect((await page.request.post(`/api/v1/recruiter/applications/${applicationId}/status`, { data: { status: "selected" } })).ok()).toBeTruthy();
  const offer = await page.request.post(`/api/v1/recruiter/applications/${applicationId}/offer`, { data: { position: "Java Developer", compensation: 600000, currency: "INR" } });
  const offerId = (await offer.json()).offer.id as string;
  const accepted = await page.request.post(`/api/v1/recruiter/offers/${offerId}/status`, { data: { status: "accepted" } });
  const placementId = (await accepted.json()).offer.placement_id as string;
  expect(placementId).toBeTruthy();

  // AC1: one placement, listed as Joining pending
  await page.goto("/recruiter/placements");
  await expect(page.getByRole("list", { name: "Placements" }).getByRole("link", { name })).toBeVisible();
  await page.getByRole("list", { name: "Placements" }).getByRole("link", { name }).click();
  await page.waitForURL(`**/recruiter/placements/${placementId}`);
  const client = page.getByRole("region", { name: "Client confirmation" });
  await client.getByRole("button", { name: "Record confirmation" }).click();
  await client.getByLabel("Confirmed by").fill("HR - Priya");
  await client.getByLabel("How").selectOption("email");
  await client.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Client confirmation saved.");
  await expect(page.getByText("A draft is created when the candidate joins.")).toBeVisible();

  // AC2: joining makes the draft; AC3: issuing feeds the receivables
  const joined = await page.request.put(`/api/v1/recruiter/offers/${offerId}/joining`, { data: { joining_status: "joined", actual_joining_date: istToday(), confirmed_by: "HR" } });
  expect(joined.ok()).toBeTruthy();
  await page.reload();
  const invoice = page.getByRole("region", { name: "Invoice" });
  await expect(invoice.getByText("Draft to review")).toBeVisible();
  await expect(invoice.getByText("Enter on issue")).toBeVisible();
  await invoice.getByRole("button", { name: "Issue invoice" }).click();
  const form = page.getByRole("form", { name: "Issue invoice" });
  await expect(form.getByLabel("Amount (₹)")).toHaveValue(""); // no fee terms: the hire is unpriced, so the amount is entered on issue
  await form.getByLabel("Amount (₹)").fill("75000");
  const number = `E2E-PL-${stamp}`;
  await form.getByLabel("Invoice number").fill(number);
  await form.getByRole("button", { name: "Issue invoice" }).click();
  await expect(page.getByRole("status")).toHaveText("Invoice issued. It now shows in Receivables.");
  await page.goto("/recruiter/receivables");
  await expect(page.getByText(number)).toBeVisible();

  // the manager reads, without confirmation writes; phone width holds
  await page.context().clearCookies();
  await signIn(page, "admin", "placement.manager@edusphere.local");
  await page.goto(`/recruiter/placements/${placementId}`);
  await expect(page.getByRole("region", { name: "Placement" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Record confirmation" })).toHaveCount(0);
  await page.setViewportSize({ width: 375, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  expect(consoleErrors).toEqual([]);
});
