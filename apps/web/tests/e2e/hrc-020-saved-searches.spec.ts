import { expect, test, type Page } from "@playwright/test";

// hrc-020 (DEC-SCOPE-401; AC1-AC3): a placement manager saves a search (sorted, with a city filter), clears the page, loads the saved search
// back (the same URL filters), exports it as CSV (holders of `candidates.export` only), and deletes it. A recruiter sees no export button.

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

test("saved search round trip, CSV export and delete", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));

  await signIn(page, "admin", "placement.manager@edusphere.local", "/recruiter/manager/team");
  const categories = await (await page.request.get("/api/v1/recruiter/skill-categories?limit=100")).json();
  const category = categories.items.find((c: { name: string }) => c.name === "Programming").id;
  const skill = `E2E20Kotlin ${stamp}`;
  await post(page, "/api/v1/recruiter/skills", { name: skill, category_id: category });
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral").id;
  const c = await post(page, "/api/v1/recruiter/candidates", {
    name: `Saved Search ${stamp}`, email: `saved${stamp}@example.com`, source_id: source, lawful_basis: "consent", experience_months: 36,
  });
  await post(page, `/api/v1/recruiter/candidates/${c.id}/skills`, { skill, level: "advanced" });

  const name = `Kotlin ${stamp}`;
  await page.goto(`/recruiter/find-candidates?all=${encodeURIComponent(skill)}&sort=experience`);
  await expect(page.getByRole("heading", { name: "1 candidate found" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Save this search" }).click();
  await page.getByLabel("Saved search name").fill(name);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(`Saved “${name}”.`)).toBeVisible();

  // AC1: from a clean page, loading the saved search brings the same filters and result back
  await page.goto("/recruiter/find-candidates");
  await page.getByLabel("Load a saved search").selectOption({ label: name });
  await expect(page.getByRole("heading", { name: "1 candidate found" })).toBeVisible({ timeout: 30_000 });
  const params = new URL(page.url()).searchParams;
  expect(params.getAll("all")).toEqual([skill]);
  expect(params.get("sort")).toBe("experience");

  // AC2/AC3: the manager holds the grant -- the CSV holds the candidate
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("candidates.csv");

  await page.getByRole("button", { name: "Delete" }).click();
  await page.getByRole("button", { name: "Yes, delete" }).click();
  await expect(page.getByText(`Deleted “${name}”.`)).toBeVisible();
  expect(consoleErrors).toEqual([]);
  await page.request.post("/api/v1/auth/logout");

  // a recruiter has no default export grant: no button, and the API refuses
  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  await page.goto(`/recruiter/find-candidates?all=${encodeURIComponent(skill)}`);
  await expect(page.getByRole("heading", { name: "1 candidate found" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Export CSV" })).toHaveCount(0);
  const refused = await page.request.post("/api/v1/recruiter/candidates/search/export", { data: { all: [skill] } });
  expect(refused.status()).toBe(403);
});
