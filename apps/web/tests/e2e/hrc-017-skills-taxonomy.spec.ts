import { expect, test, type Page } from "@playwright/test";

// hrc-017 (DEC-SCOPE-388; AC1, AC2): the placement manager sees the seeded non-IT Pharmacy category, adds a non-IT category, moves it to
// IT and filters the skills by domain (kept in the URL across a refresh). The seeded recruiter sets "Python ≥ Intermediate" on a
// requirement: the detail and the scoring line show it, a beginner leaves the matches while an advanced candidate stays, and the form
// offers no level for a skill outside the Skills Master. Phone width has no horizontal scroll.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function post(page: Page, url: string, data: unknown) {
  const response = await page.request.post(url, { data });
  expect(response.ok(), `${url} → ${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json();
}

test("skills taxonomy: non-IT domains, the domain filter and a required minimum level", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 400 && failedCalls.push(`${response.status()} ${response.url()}`));

  // --- the manager's Skills Master (AC1) ---
  await signIn(page, "admin", "placement.manager@edusphere.local", "/recruiter/manager/team");
  await page.goto("/recruiter/manager/skills");
  const categories = page.getByRole("region", { name: "Category list" });
  await expect(categories.locator("tr", { hasText: "Pharmacy" }).getByText("Non-IT", { exact: true })).toBeVisible();
  const name = `E2E Retail ${stamp}`;
  await page.fill("#skill-cat-name", name);
  await page.selectOption("#skill-cat-domain", "non_it");
  await page.getByRole("button", { name: "Add category" }).click();
  await expect(page.getByText(`Added category ${name}.`)).toBeVisible();
  await expect(categories.locator("tr", { hasText: name }).getByText("Non-IT", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: `Move ${name} to IT` }).click();
  await expect(page.getByText(`Moved ${name} to IT.`)).toBeVisible();
  await expect(categories.locator("tr", { hasText: name }).getByText("IT", { exact: true })).toBeVisible();

  await page.getByLabel("Search skills or aliases").fill("Pharmacovigilance");
  await page.selectOption("#skill-domain", "non_it");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.waitForURL("**domain=non_it**");
  const skills = page.getByRole("region", { name: "Skills" });
  await expect(skills.getByRole("cell", { name: "Pharmacovigilance", exact: true })).toBeVisible();
  await page.reload();
  await expect(categories.locator("tr", { hasText: "Pharmacy" })).toBeVisible(); // the filter form re-mounts once the categories load
  await expect(page.locator("#skill-domain")).toHaveValue("non_it");
  await page.selectOption("#skill-domain", "it");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.waitForURL("**domain=it**");
  await expect(page.getByText("No skills match your search.")).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  // --- the recruiter: Python ≥ Intermediate (AC2) ---
  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  const programming = (await (await page.request.get("/api/v1/recruiter/skill-categories?q=Programming&domain=it")).json()).items[0];
  expect(programming.domain).toBe("it");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral").id;
  const candidate = async (who: string, level: string) => {
    const c = await post(page, "/api/v1/recruiter/candidates", { name: `${who} ${stamp}`, email: `lvl${who.toLowerCase()}${stamp}@example.com`, source_id: source });
    await post(page, `/api/v1/recruiter/candidates/${c.id}/skills`, { skill: "Python", level });
  };
  await candidate("Beginner", "beginner");
  await candidate("Advanced", "advanced");
  const company = await post(page, "/api/v1/recruiter/companies", { name: `E2E Level ${stamp} Ltd` });
  const requirement = (await post(page, "/api/v1/recruiter/requirements", {
    company_id: company.company.id, title: `Python Developer ${stamp}`, location: "Pune", work_mode: "remote",
    required_skills: ["Python"], preferred_skills: [`Freeform ${stamp}`],
  })).requirement;

  await page.goto(`/recruiter/requirements/${requirement.id}`);
  await expect(page.getByRole("link", { name: `View profile of Beginner ${stamp}` })).toBeVisible();
  await page.getByRole("button", { name: "Adjust weights" }).click();
  await expect(page.getByLabel(`Minimum level of Freeform ${stamp} (preferred)`)).toHaveCount(0);
  await page.getByLabel("Minimum level of Python (required)").selectOption("intermediate");
  await page.getByRole("button", { name: "Save weights" }).click();
  await expect(page.getByText("Match weights saved.")).toBeVisible();
  await expect(page.getByText(/Score out of 100: Python \(Intermediate or above\)/)).toBeVisible();
  await expect(page.locator("li", { hasText: "Python · Intermediate or above" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: `View profile of Advanced ${stamp}` })).toBeVisible();
  await expect(page.getByRole("link", { name: `View profile of Beginner ${stamp}` })).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.locator("li", { hasText: "Python · Intermediate or above" }).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);

  expect(consoleErrors).toEqual([]);
  expect(failedCalls).toEqual([]);
});
