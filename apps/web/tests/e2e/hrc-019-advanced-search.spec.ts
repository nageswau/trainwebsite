import { expect, test, type Page } from "@playwright/test";

// hrc-019 (DEC-SCOPE-399; AC2, AC3, S11): the recruiter narrows a skill search by degree (a collapsed group opened from its summary),
// sees one removable chip per filter, sorts by experience (kept on refresh), reads each card's "why matched", and removes the degree chip.

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

test("advanced search: degree filter, chips, sort, why matched", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));

  await signIn(page, "admin", "placement.manager@edusphere.local", "/recruiter/manager/team");
  const categories = await (await page.request.get("/api/v1/recruiter/skill-categories?limit=100")).json();
  const category = categories.items.find((c: { name: string }) => c.name === "Programming").id;
  const skill = `E2E19Java ${stamp}`;
  await post(page, "/api/v1/recruiter/skills", { name: skill, category_id: category });
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral").id;
  const candidate = async (name: string, degree: string, years: number) => {
    const c = await post(page, "/api/v1/recruiter/candidates", {
      name: `${name} ${stamp}`, email: `adv${name.toLowerCase()}${stamp}@example.com`, source_id: source, lawful_basis: "consent",
      education: [{ degree, institution: "JNTU" }], experience_months: years * 12,
    });
    await post(page, `/api/v1/recruiter/candidates/${c.id}/skills`, { skill, level: "advanced" });
  };
  await candidate("Anil", "B.Tech", 2);
  await candidate("Bhavna", "B.Tech", 6);
  await candidate("Charan", "MBA", 4);

  await page.goto("/recruiter/find-candidates");
  const all = page.getByRole("textbox", { name: "Must have all of these skills" });
  await all.fill(skill);
  await all.press("Enter");
  await page.getByRole("button", { name: "Search candidates" }).click();
  await expect(page.getByRole("heading", { name: "3 candidates found" })).toBeVisible();

  // a collapsed group opens from its summary
  await page.locator("summary", { hasText: "Education" }).click();
  await page.getByLabel("Degree", { exact: true }).fill("B.Tech");
  await page.getByRole("button", { name: "Search candidates" }).click();
  await expect(page.getByRole("heading", { name: "2 candidates found" })).toBeVisible();
  const chips = page.getByRole("list", { name: "Active filters" });
  await expect(chips.getByRole("listitem")).toHaveText(["Degree: B.Tech×"]);

  // AC3: sort by experience, most first; the URL keeps it across a refresh
  await page.getByLabel("Sort by").selectOption("experience");
  await expect(page).toHaveURL(/sort=experience/);
  await page.reload();
  const cards = page.getByRole("region", { name: "Search results" }).locator("li.action-card h3");
  await expect(cards).toHaveText([new RegExp(`Bhavna ${stamp}`), new RegExp(`Anil ${stamp}`)]);
  await expect(page.getByLabel("Sort by")).toHaveValue("experience");

  // S11: why matched
  await expect(page.getByRole("listitem", { name: new RegExp(`Bhavna ${stamp}`) }).getByText(`Matches: ${skill}`)).toBeVisible();

  // AC2: removing the degree chip keeps the skill and the sort
  await chips.getByRole("button", { name: "Remove Degree: B.Tech" }).click();
  await expect(page.getByRole("heading", { name: "3 candidates found" })).toBeVisible();
  await expect(page).toHaveURL(/sort=experience/);
  await expect(page).not.toHaveURL(/degree=/);
  await expect(cards.first()).toHaveText(new RegExp(`Bhavna ${stamp}`));

  expect(consoleErrors.filter((e) => !e.includes("favicon"))).toEqual([]);
});
