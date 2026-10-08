import { expect, test, type Page } from "@playwright/test";

// rec-006 (AC1-AC7): the demo placement manager adds a category and a skill, adds an alias, is refused a conflicting alias, relates two
// skills and deactivates one; the demo recruiter reads the Skills Master read-only, finds a skill by its alias and never sees the
// deactivated one. Needs the demo seed (python -m app.seed).

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("manager maintains the Skills Master; recruiter reads it", async ({ page }) => {
  test.setTimeout(60_000);
  const stamp = Date.now().toString(36);
  const category = `E2E Cat ${stamp}`;
  const skill = `E2E Skill ${stamp}`;
  const alias = `E2E Alias ${stamp}`;
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await signIn(page, "admin", "placement.manager@edusphere.local", "/recruiter/manager/team");
  await page.getByRole("link", { name: "Skills Master" }).first().click();
  await page.waitForURL("**/recruiter/manager/skills");
  // AC1: the seed is there -- JavaScript once, under Programming with a Frontend tag.
  await expect(page.getByRole("region", { name: "Skills" }).getByText("Programming · also Frontend")).toBeVisible();

  await page.getByLabel("Category name (required)").fill(category);
  await page.getByRole("button", { name: "Add category" }).click();
  await expect(page.getByText(`Added category ${category}.`)).toBeVisible();

  await page.getByLabel("Skill name (required)").fill(skill);
  await page.locator("#skill-new-category").selectOption({ label: category });
  await page.getByRole("group", { name: "Other categories" }).first().getByLabel("Database", { exact: true }).check();
  await page.getByRole("button", { name: "Create skill" }).click();
  await expect(page.getByText(`Created ${skill}.`)).toBeVisible();

  await page.getByLabel("Search skills or aliases").fill(skill);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("button", { name: `Manage ${skill}` }).click();
  const detail = page.getByRole("region", { name: skill });
  await detail.getByLabel("New alias").fill(alias);
  await detail.getByRole("button", { name: "Add alias" }).click();
  await expect(detail.getByText(`Added alias ${alias}.`)).toBeVisible();
  // AC3: an alias equal to another skill's name is refused with the server's sentence.
  await detail.getByLabel("New alias").fill("core java");
  await detail.getByRole("button", { name: "Add alias" }).click();
  await expect(detail.getByText("“core java” is already a skill name")).toBeVisible();
  // Related skill via the server-searched picker.
  await detail.getByRole("combobox", { name: "Related skill" }).fill("Kubern");
  await detail.getByRole("listbox", { name: "Related skill" }).getByRole("option", { name: /Kubernetes/ }).click();
  await detail.getByRole("button", { name: "Add related skill" }).click();
  await expect(detail.getByText(`Related ${skill} to Kubernetes.`)).toBeVisible();
  await expect(detail.getByRole("button", { name: "Remove related skill Kubernetes" })).toBeVisible();

  // AC2: the alias finds the skill.
  await page.getByLabel("Search skills or aliases").fill(alias.toLowerCase());
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("region", { name: "Skills" }).getByText(skill, { exact: true })).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  await page.goto(`/recruiter/skills?q=${encodeURIComponent(alias)}`);
  await expect(page.getByRole("region", { name: "Skills" }).getByText(skill, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Manage/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add category" })).toHaveCount(0);
  // A recruiter cannot open the manager page.
  await page.goto("/recruiter/manager/skills");
  await expect(page.getByText("Placement manager role required")).toBeVisible();

  // AC6: the manager deactivates the skill; the recruiter no longer sees it.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "admin", "placement.manager@edusphere.local", "/recruiter/manager/team");
  await page.goto(`/recruiter/manager/skills?q=${encodeURIComponent(skill)}`);
  await page.getByRole("button", { name: `Manage ${skill}` }).click();
  await page.getByRole("region", { name: skill }).getByRole("button", { name: `Deactivate ${skill}` }).click();
  await page.getByRole("button", { name: "Confirm deactivate" }).click();
  await expect(page.getByText(`Deactivated ${skill}.`)).toBeVisible();
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  await page.goto(`/recruiter/skills?q=${encodeURIComponent(skill)}`);
  await expect(page.getByText("No skills match your search.")).toBeVisible();
  expect(errors).toEqual([]);
});

test("the recruiter's read-only page fits a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  await page.goto("/recruiter/skills?q=java");
  await expect(page.getByRole("region", { name: "Skills" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
