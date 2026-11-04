import { expect, test, type Page } from "@playwright/test";

// hrc-018 (DEC-SCOPE-390; AC1-AC4): the super admin's match weights card (must total 100), then a requirement with all six factors:
// Asha meets every one (100%) and each factor explains itself; Ravi has the required skill only. Making Location a hard filter drops
// Ravi. The disclaimer shows; a recruiter has no weights card; nothing scrolls sideways on a phone. The weights go back to the defaults.

const SUPER = "superadmin@edusphere.local";
const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";
const DEFAULTS = { skills: 40, experience: 20, qualification: 15, location: 10, role: 10, salary: 5 };

async function signIn(page: Page, email: string, portal: string) {
  await page.goto(portal);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function post(page: Page, url: string, data: unknown) {
  const response = await page.request.post(url, { data });
  expect(response.ok(), `${url} → ${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json();
}

test("match weights total 100, six explained factors, a location hard filter, phone width", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const n = (name: string) => `${name} ${stamp}`;
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));

  // AC1: the super admin's weights card offers Save only at a total of 100.
  await signIn(page, SUPER, "/admin/login");
  try {
    await page.goto("/recruiter/requirements");
    await page.getByText("Match weights", { exact: true }).click();
    const card = page.getByRole("form", { name: "Match weights" });
    await expect(card.getByText("Total 100 of 100.")).toBeVisible();
    await card.getByLabel("Skills").fill("45");
    await expect(card.getByText("Total 105 of 100 — the weights must add up to 100.")).toBeVisible();
    await expect(card.getByRole("button", { name: "Save weights" })).toBeDisabled();
    await card.getByLabel("Role").fill("5");
    await card.getByRole("button", { name: "Save weights" }).click();
    await expect(card.getByText("Match weights saved. Every requirement's matches now use them.")).toBeVisible();
    await page.reload();
    await expect(page.getByText(/Skills 45 · Experience 20 · Qualification 15 · Location 10 · Role 5 · Salary & availability 5/)).toBeVisible();
    await page.getByText("Match weights", { exact: true }).click();
    await card.getByRole("button", { name: "Use the defaults" }).click();
    await card.getByRole("button", { name: "Save weights" }).click();
    await expect(card.getByText("Match weights saved. Every requirement's matches now use them.")).toBeVisible();

    // Test skills (the placement manager owns the Skills Master).
    await page.request.post("/api/v1/auth/logout");
    await signIn(page, MANAGER, "/admin/login");
    const categories = await (await page.request.get("/api/v1/recruiter/skill-categories?limit=100")).json();
    const category = categories.items.find((c: { name: string }) => c.name === "Programming").id;
    for (const s of ["EJava", "EAWS"]) await post(page, "/api/v1/recruiter/skills", { name: n(s), category_id: category });
    await page.request.post("/api/v1/auth/logout");

    // The recruiter: two candidates and a requirement every factor applies to.
    await signIn(page, RECRUITER, "/it/login");
    await page.goto("/recruiter/requirements");
    await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
    await expect(page.getByText("Match weights", { exact: true })).toHaveCount(0); // E3: only super_admin
    const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
    const source = sources.items.find((s: { name: string }) => s.name === "Referral").id;
    const candidate = async (name: string, fields: Record<string, unknown>, skills: string[]) => {
      const c = await post(page, "/api/v1/recruiter/candidates", { name: n(name), email: `engine${name.toLowerCase()}${stamp}@example.com`, source_id: source, ...fields });
      for (const s of skills) await post(page, `/api/v1/recruiter/candidates/${c.id}/skills`, { skill: n(s), level: "advanced" });
    };
    await candidate("Asha", { location: "Pune", experience_months: 50, relevant_experience_months: 36, qualification: "MCA", preferred_role: "Java Developer",
      expected_salary: 800000, notice_days: 30 }, ["EJava", "EAWS"]);
    await candidate("Ravi", { location: "Delhi", experience_months: 12, qualification: "BCom", expected_salary: 1200000 }, ["EJava"]);
    const companies = await (await page.request.get("/api/v1/recruiter/companies?limit=1")).json();
    const company = companies.items[0]?.id ?? (await post(page, "/api/v1/recruiter/companies", { name: `E2E Engine ${stamp} Ltd` })).company.id;
    const requirement = (await post(page, "/api/v1/recruiter/requirements", {
      company_id: company, title: n("Java Developer"), location: "Pune", qualification: "B.Tech or MCA", experience_min_months: 24,
      experience_max_months: 60, salary_max: 1000000, required_skills: [n("EJava")], preferred_skills: [n("EAWS")],
    })).requirement;

    await page.goto(`/recruiter/requirements/${requirement.id}`);
    const section = page.getByRole("region", { name: /^Matching candidates/ });
    await expect(section.getByRole("heading", { name: "Matching candidates (2)" })).toBeVisible();
    await expect(section.getByText(/Score out of 100: .*Experience 20 · Qualification 15 · Location \(Pune\) 10 · Role 10 · Salary & availability 5\. Candidates must have every required skill\./)).toBeVisible();
    await expect(section.getByText(/It is not a guarantee of suitability, an interview or an offer\./)).toBeVisible();
    const rows = section.getByRole("list", { name: "Matching candidates" }).getByRole("listitem").filter({ has: page.getByRole("link", { name: /View profile/ }) });
    await expect(rows.nth(0)).toContainText(n("Asha"));
    await expect(rows.nth(0)).toContainText("100% match");
    const why = section.getByRole("list", { name: `Why ${n("Asha")} matches` });
    await expect(why).toContainText("Matches 1 of 1 required skills · 1 of 1 preferred");
    await expect(why).toContainText("3 yrs relevant (needs 2–5 yrs)");
    await expect(why).toContainText("MCA matches the qualification");
    await expect(why).toContainText("In or prefers Pune");
    await expect(why).toContainText("Wants a Java Developer role");
    await expect(why).toContainText("Expected ₹8L within budget (up to ₹10L)");
    await expect(rows.nth(1)).toContainText(n("Ravi"));
    await expect(rows.nth(1)).toContainText("27% match");
    const ravi = section.getByRole("list", { name: `Why ${n("Ravi")} matches` });
    await expect(ravi).toContainText(`0 of 1 preferred (missing ${n("EAWS")})`);
    await expect(ravi).toContainText("Not in or preferring Pune");
    await expect(ravi).toContainText("Expected ₹12L above budget (up to ₹10L)");

    // AC2 (E6): Location as a hard filter drops Ravi; the rule line says so.
    await section.getByRole("button", { name: "Adjust weights" }).click();
    await expect(section.getByRole("checkbox", { name: "Minimum experience" })).toBeEnabled();
    await section.getByRole("checkbox", { name: "Location" }).check();
    await section.getByRole("button", { name: "Save weights" }).click();
    await expect(page.getByText("Match weights saved.")).toBeVisible();
    await expect(section.getByRole("heading", { name: "Matching candidates (1)" })).toBeVisible();
    await expect(section).not.toContainText(n("Ravi"));
    await expect(section.getByText(/Candidates must have every required skill and meet: location\./)).toBeVisible();
    await page.reload();
    await expect(page.getByRole("region", { name: /^Matching candidates/ }).getByRole("heading", { name: "Matching candidates (1)" })).toBeVisible();

    // Phone width: no sideways scroll.
    await page.setViewportSize({ width: 375, height: 812 });
    await expect(section.getByRole("list", { name: `Why ${n("Asha")} matches` })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  } finally {
    // The weights are shared by every test: put the defaults back as the super admin.
    await page.request.post("/api/v1/auth/logout");
    await signIn(page, SUPER, "/admin/login");
    const reset = await page.request.put("/api/v1/recruiter/match-settings", { data: { weights: DEFAULTS } });
    expect(reset.ok()).toBeTruthy();
  }
  expect(consoleErrors).toEqual([]);
  expect(failedCalls).toEqual([]);
});
