import { expect, test, type Page } from "@playwright/test";

// rec-015 (AC1-AC2; DEC-SCOPE-159 P1-P8): the placement manager makes test skills and a "Cloud" pool (AWS OR Azure) from the form; the
// seeded recruiter's candidates join it with no other action (AC1); an unknown skill is refused with suggestions; a deactivated skill is
// flagged and left out of the Find Candidates link; a deactivated pool disappears for the recruiter; the page holds at phone width.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const RECRUITER = "placement@edusphere.local";
const MANAGER = "placement.manager@edusphere.local";

async function send(page: Page, method: "post" | "patch", url: string, data: unknown) {
  const response = await page.request[method](url, { data });
  expect(response.ok(), `${url} → ${response.status()} ${await response.text()}`).toBeTruthy();
  return response.json();
}

test("talent pools: create from the form, automatic membership, unknown and deactivated skills, roles, phone width", async ({ page }) => {
  test.setTimeout(150_000);
  const stamp = Date.now();
  const n = (name: string) => `${name} ${stamp}`;
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));

  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  const categories = await (await page.request.get("/api/v1/recruiter/skill-categories?limit=100")).json();
  const category = categories.items.find((c: { name: string }) => c.name === "Programming").id;
  const skills: Record<string, string> = {};
  for (const s of ["PAWS", "PAzure", "PCobol"]) skills[s] = (await send(page, "post", "/api/v1/recruiter/skills", { name: n(s), category_id: category })).id;
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral").id;
  const candidate = async (name: string, owned: string[]) => {
    const c = await send(page, "post", "/api/v1/recruiter/candidates", { name: n(name), email: `pool${name.toLowerCase()}${stamp}@example.com`, source_id: source });
    for (const s of owned) await send(page, "post", `/api/v1/recruiter/candidates/${c.id}/skills`, { skill: n(s), level: "advanced" });
    return c;
  };
  await candidate("Asha", ["PAWS"]);
  await candidate("Ravi", ["PAzure"]);
  const late = await candidate("Kiran", ["PCobol"]);
  await page.request.post("/api/v1/auth/logout");

  // the manager creates the pool from the form; an unknown skill is refused first, with suggestions
  await signIn(page, "admin", MANAGER, "/recruiter/manager/team");
  await page.goto("/recruiter/pools");
  await expect(page.getByRole("heading", { name: "Talent Pools" })).toBeVisible();
  await page.getByRole("button", { name: "+ New pool" }).click();
  await page.getByLabel("Pool name").fill(n("Cloud"));
  await page.getByRole("textbox", { name: "Must have all of these skills", exact: true }).fill(`PAW ${stamp}`);
  await page.getByRole("button", { name: "Create pool" }).click();
  await expect(page.getByRole("alert").filter({ hasText: `No skill is called “PAW ${stamp}”` })).toBeVisible(); // the route announcer is an alert too
  await page.getByRole("button", { name: `Remove PAW ${stamp}` }).click();
  await page.getByRole("button", { name: "+ Add an “at least one of” group" }).click();
  const group = page.getByRole("textbox", { name: "And at least one of these (group 1)", exact: true }); // the chip list is labelled "…: chosen"
  await group.fill(n("PAWS"));
  await group.press("Enter");
  await group.fill(n("PAzure"));
  await page.getByRole("button", { name: "Create pool" }).click();
  await page.waitForURL("**/recruiter/pools/*");
  const poolUrl = page.url();
  await expect(page.getByRole("heading", { name: n("Cloud") })).toBeVisible();
  await expect(page.getByRole("heading", { name: "2 candidates" })).toBeVisible();
  await expect(page.getByRole("link", { name: n("Asha"), exact: true })).toBeVisible();

  // AC1: a new skill places a candidate in the pool with no other action
  await send(page, "post", `/api/v1/recruiter/candidates/${late.id}/skills`, { skill: n("PAzure"), level: "beginner" });
  await page.reload();
  await expect(page.getByRole("heading", { name: "3 candidates" })).toBeVisible();

  // P5: a deactivated skill is flagged and left out of the Find Candidates link (QA-03)
  await send(page, "patch", `/api/v1/recruiter/skills/${skills.PAzure}`, { active: false });
  await page.reload();
  await expect(page.getByText(`Some skills in this pool are no longer in the Skills Master: ${n("PAzure")}.`)).toBeVisible();
  await expect(page.getByRole("heading", { name: "1 candidate" })).toBeVisible();
  const refine = await page.getByRole("link", { name: "Refine in Find Candidates" }).getAttribute("href");
  expect(decodeURIComponent((refine ?? "").replaceAll("+", " "))).toBe(`/recruiter/find-candidates?any1=${n("PAWS")}`);
  await send(page, "patch", `/api/v1/recruiter/skills/${skills.PAzure}`, { active: true });

  // edit: deactivate the pool; focus returns to Edit pool (QA-02)
  await page.reload();
  await page.getByRole("button", { name: "Edit pool" }).click();
  await page.getByLabel(/Active/).uncheck();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Pool saved. Members are recalculated from the new rule.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit pool" })).toBeFocused();
  await expect(page.getByText("Talent pool · Inactive", { exact: false })).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  // the recruiter: no create, the inactive pool is gone; phone width holds
  await signIn(page, "it", RECRUITER, "/recruiter/dashboard");
  await page.goto("/recruiter/pools");
  await expect(page.getByRole("link", { name: "Java Developers", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "+ New pool" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: n("Cloud") })).toHaveCount(0);
  await page.goto(poolUrl);
  await expect(page.getByRole("alert").filter({ hasText: "Talent pool not found" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/recruiter/pools");
  await expect(page.getByRole("link", { name: "Java Developers", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "test-results/rec-015-pools-phone.png", fullPage: true });

  expect(failedCalls).toEqual([]);
  // the browser logs the two deliberate refusals above (the unknown skill's 422, the recruiter's 404 on the inactive pool)
  expect(consoleErrors.filter((e) => !/status of (404|422)/.test(e))).toEqual([]);
});
