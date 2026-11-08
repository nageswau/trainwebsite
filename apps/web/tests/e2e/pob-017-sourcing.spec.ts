import { expect, test, type Page } from "@playwright/test";

// pob-017 (DEC-SCOPE-429): the recruiter builds a requirement's sourcing plan -- target profile, a Boolean string, a planned channel, targets, a passed deadline and
// themselves as source owner (AC1) -- and sees the deadline breach (AC3) and the funnel by source, whose total ties out with its rows (AC2). On a phone nothing scrolls sideways.
const RECRUITER = "placement@edusphere.local";

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("a sourcing plan saves, flags a missed deadline and counts candidates by source", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  await signIn(page, RECRUITER);
  const post = async (url: string, data: object) => {
    const response = await page.request.post(url, { data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { company } = await post("/api/v1/recruiter/companies", { name: `E2E Pob017 ${stamp} Pvt` });
  const { requirement } = await post("/api/v1/recruiter/requirements", { company_id: company.id, title: `Pob017 ${stamp}`, location: "Pune", required_skills: ["Java"] });
  await post(`/api/v1/recruiter/requirements/${requirement.id}/status`, { status: "requirement_received" });
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const linkedin = sources.items.find((s: { name: string }) => s.name === "LinkedIn");
  for (const [i, status] of ["sourced", "shortlisted"].entries()) {
    const candidate = await post("/api/v1/recruiter/candidates", { name: `E2E Src ${stamp} ${i}`, email: `pob017-${stamp}-${i}@example.com`, source_id: linkedin.id });
    await post(`/api/v1/recruiter/requirements/${requirement.id}/candidates`, { candidate_id: candidate.id, status });
  }

  await page.goto(`/recruiter/requirements/${requirement.id}`);
  const card = page.getByRole("region", { name: "Sourcing plan" });
  await expect(card.getByText("No targets set")).toBeVisible();
  await card.getByRole("button", { name: "Create plan" }).click();
  await card.getByLabel("Target profile").fill("3-5 years Java backend, Pune");
  await card.getByRole("button", { name: "Add a search string" }).click();
  await card.getByLabel("Name", { exact: true }).fill("Naukri");
  await card.getByLabel("Search string", { exact: true }).fill('"java developer" AND pune');
  await card.getByRole("checkbox", { name: "LinkedIn" }).check();
  await card.getByLabel("Profiles to find").fill("5");
  await card.getByLabel("Profiles to screen").fill("1");
  const yesterday = new Date(Date.now() - 2 * 86_400_000).toISOString().slice(0, 10);
  await card.getByLabel("Deadline").fill(yesterday);
  await card.getByLabel("Source owner").selectOption({ index: 1 });
  await card.getByRole("button", { name: "Save plan" }).click();

  await expect(card.getByText("Sourcing plan saved.")).toBeVisible();
  await expect(card.getByText("Deadline missed")).toBeVisible();
  await expect(card.getByText(/these are short: profiles to find\./)).toBeVisible();
  await expect(card.getByText("3-5 years Java backend, Pune")).toBeVisible();
  await expect(card.getByRole("button", { name: "Copy Naukri" })).toBeVisible();
  const row = card.getByRole("row", { name: /LinkedIn/ });
  await expect(row.getByRole("cell")).toHaveText(["2", "1", "1", "0", "0", "0%"]);
  await expect(card.getByRole("row", { name: /Total/ }).getByRole("cell")).toHaveText(["2", "1", "1", "0", "0", "0%"]);

  await page.reload();
  await expect(card.getByText("3-5 years Java backend, Pune")).toBeVisible(); // AC1: it saved

  await page.setViewportSize({ width: 375, height: 812 });
  await card.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
