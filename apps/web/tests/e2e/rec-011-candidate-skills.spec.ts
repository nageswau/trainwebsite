import { expect, test, type Page } from "@playwright/test";

// rec-011 (AC1-AC5): a recruiter adds Java (Advanced, 36 months, 2026, resume) from the Skills Master, the same skill by its alias J2EE is
// refused, and marking it verified records who; HR reads the skills but has no write controls.

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function pickSkill(page: Page, text: string, option: RegExp) {
  const picker = page.getByRole("combobox", { name: /^Skill/ });
  await picker.fill(text);
  await page.getByRole("option", { name: option }).click();
}

test("a recruiter adds a skill, is stopped on a duplicate alias, verifies it; HR reads only", async ({ page }) => {
  test.setTimeout(90_000);
  const stamp = Date.now();
  const name = `Skill Test ${stamp}`;
  await signIn(page, "placement@edusphere.local", "/recruiter/dashboard");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral");
  const created = await page.request.post("/api/v1/recruiter/candidates", { data: { name, email: `skills${stamp}@example.com`, source_id: source.id } });
  expect(created.status()).toBe(201);
  const candidate = await created.json();

  await page.goto(`/recruiter/candidates/${candidate.id}`);
  const card = page.getByRole("region", { name: "Skills" });
  await expect(card.getByText("No skills added yet.")).toBeVisible();

  // AC1: Java, Advanced, 36 months, last used 2026, from the resume -- stored claimed.
  await card.getByRole("button", { name: "Add skill" }).click();
  await pickSkill(page, "Java", /^Java — /);
  await card.getByLabel(/^Level/).selectOption("advanced");
  await card.getByLabel(/^Experience/).fill("36");
  await card.getByLabel(/^Last used/).fill("2026");
  await card.getByRole("button", { name: "Add", exact: true }).click();
  await expect(card.getByText("Added Java.")).toBeVisible();
  const row = card.getByRole("row", { name: /Java/ });
  await expect(row).toContainText("Advanced");
  await expect(row).toContainText("3 yr");
  await expect(row).toContainText("2026");
  await expect(row).toContainText("Resume");
  await expect(row).toContainText("Claimed");

  // AC2: the same skill by its alias is refused with the server's sentence; the entry is kept.
  await card.getByRole("button", { name: "Add skill" }).click();
  await pickSkill(page, "J2EE", /^Java — /);
  await card.getByLabel(/^Level/).selectOption("expert");
  await card.getByRole("button", { name: "Add", exact: true }).click();
  await expect(card.getByRole("alert")).toHaveText("Java is already on this candidate's skills");
  await card.getByRole("button", { name: "Cancel" }).click();

  // AC3: verified records who.
  await card.getByRole("button", { name: "Mark verified: Java" }).click();
  await expect(card.getByText("Java marked verified.")).toBeVisible();
  await expect(row).toContainText("Verified");
  await expect(row).toContainText("by Kiran Placement");
  await page.request.post("/api/v1/auth/logout");

  // AC5: HR reads the skills only.
  await signIn(page, "hr@edusphere.local", "/it/hr/dashboard");
  await page.goto(`/recruiter/candidates/${candidate.id}`);
  const hrCard = page.getByRole("region", { name: "Skills" });
  await expect(hrCard.getByRole("row", { name: /Java/ })).toContainText("Verified");
  await expect(hrCard.getByRole("button")).toHaveCount(0);
});
