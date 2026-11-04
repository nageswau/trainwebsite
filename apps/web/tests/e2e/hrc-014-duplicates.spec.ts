import { expect, test, type Page } from "@playwright/test";

// hrc-014 (DEC-SCOPE-377): a recruiter adds the same person twice (same name, location and college, another email) -- the placement
// manager finds the pair under Duplicate Review, merges the newer record into the older one, and the merged record points at the one
// that stays; a recruiter without `candidates.merge` is refused. Seeded demo accounts; the candidates are created per run.
async function signIn(page: Page, email: string, division = "it") {
  expect((await page.request.post("/api/v1/auth/login", { data: { email, password: "Demo@123", division } })).ok()).toBeTruthy();
}

test("a probable duplicate is reviewed and merged into the older record", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await signIn(page, "placement@edusphere.local");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { active: boolean }) => s.active).id;
  const add = async (data: object) => {
    const response = await page.request.post("/api/v1/recruiter/candidates", { data: { source_id: source, ...data } });
    expect(response.status(), await response.text()).toBe(201);
    return (await response.json()) as { id: string; candidate_code: string; name: string };
  };
  const name = `E2E Meera ${stamp}`;
  const older = await add({ name, email: `hrc014-a-${stamp}@example.com`, location: "Pune", college: "NIT Trichy" });
  const newer = await add({ name: name.toUpperCase(), email: `hrc014-b-${stamp}@example.com`, location: "pune", college: "nit trichy", current_company: "Acme" });

  await page.goto("/recruiter/candidates/duplicates"); // D3: no grant -- the API's refusal is shown
  await expect(page.getByRole("alert").filter({ hasText: "cannot review or merge duplicate candidates" })).toBeVisible(); // not the route announcer

  await signIn(page, "placement.manager@edusphere.local", "global");
  await page.goto("/recruiter/candidates");
  await page.getByRole("link", { name: "Duplicate Review" }).click();
  await expect(page.getByRole("heading", { name: "Duplicate review", level: 2 })).toBeVisible();
  const review = page.getByRole("link", { name: `Review and merge ${older.name} and ${newer.name}` });
  await expect(review).toBeVisible();
  await expect(page.getByRole("row").filter({ has: review }).getByText("Same name, location and college")).toBeVisible();
  await review.click();

  await expect(page.getByRole("heading", { name: `Merge ${newer.candidate_code} into ${older.candidate_code}` })).toBeVisible();
  await expect(page.getByRole("table", { name: "Compare the two candidates" })).toBeVisible();
  await page.getByLabel("Reason (optional)").fill("Same person, two emails");
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: `Merge ${newer.candidate_code} into ${older.candidate_code}` }).click();

  await page.waitForURL(`**/recruiter/candidates/${older.id}*`);
  await expect(page.getByText(`${newer.candidate_code} was merged into this candidate.`)).toBeVisible();
  await expect(page.getByText("Acme")).toBeVisible(); // the empty current company was filled from the duplicate (D4)

  await page.goto(`/recruiter/candidates/${newer.id}`);
  await expect(page.getByRole("link", { name: older.candidate_code })).toBeVisible(); // D8
  await expect(page.getByRole("button", { name: "Restore" })).toHaveCount(0);

  await page.goto("/recruiter/candidates/duplicates");
  await page.getByRole("button", { name: "Merged" }).click();
  await expect(page.getByRole("link", { name: older.name, exact: true })).toBeVisible();
});
