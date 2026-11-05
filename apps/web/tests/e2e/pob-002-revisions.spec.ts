import { expect, test, type Page } from "@playwright/test";

// pob-002 (DEC-SCOPE-405): a recruiter edits a requirement -- headcount 2 -> 3, the hiring process and the requirement's own payment
// terms -- and revision 2 shows the diff while revision 1 stays readable; the contract's terms show as "From the contract" until
// overridden; on a phone the open revision never scrolls sideways.

async function signIn(page: Page, email: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/recruiter/dashboard");
}

test("a requirement's edit becomes revision 2 with its diff", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await signIn(page, "placement@edusphere.local");
  const post = async (url: string, data: object) => {
    const response = await page.request.post(url, { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const { company } = await post("/api/v1/recruiter/companies", { name: `E2E Pob002 ${stamp} Pvt` });
  await post(`/api/v1/recruiter/companies/${company.id}/contracts`, { agreement_type: "Permanent hiring", fee_basis: "fixed", fee_value: "75000",
    payment_terms: "45 days from invoice", replacement_policy: "90 days free replacement" });
  const { requirement } = await post("/api/v1/recruiter/requirements", { company_id: company.id, title: `Pob002 ${stamp}`, location: "Pune", vacancies: 2 });

  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const terms = page.getByRole("region", { name: "Commercial terms" });
  await expect(terms.getByText("From the contract")).toHaveCount(3);
  const revisions = page.getByRole("region", { name: "Revisions" });
  await expect(revisions.getByText("The requirement as first recorded")).toBeVisible();

  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const form = page.getByRole("region", { name: "Edit details" });
  await form.getByLabel("Number of vacancies").fill("3");
  await form.getByLabel("Interview rounds").fill("Technical\nHR");
  await form.getByLabel("Expected turnaround (days)").fill("21");
  await form.getByLabel("Payment terms").fill("30 days after joining");
  await form.getByLabel("Reason for this revision (optional)").fill("Client added a seat");
  await form.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Changes saved.")).toBeVisible();
  await expect(terms.getByText("30 days after joining")).toBeVisible();
  await expect(terms.getByText("From the contract")).toHaveCount(2);

  await expect(revisions.getByText("Reason: Client added a seat")).toBeVisible();
  await revisions.getByRole("button", { name: "View revision 2" }).click();
  const changes = revisions.getByRole("list", { name: "Changes from revision 1" });
  await expect(changes.getByText("Number of vacancies: 2 → 3")).toBeVisible();
  await expect(changes.getByText("Interview rounds: — → Technical; HR")).toBeVisible();
  await revisions.getByRole("button", { name: "View revision 1" }).click();
  await revisions.getByText("All values in revision 1").click();

  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
