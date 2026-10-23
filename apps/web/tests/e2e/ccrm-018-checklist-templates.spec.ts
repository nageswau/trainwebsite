import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { pickFromList } from "./helpers/pick";

// ccrm-018 (DEC-SCOPE-248) -- the Overseas Admin creates a UK checklist template, sees a second one with the same scope refused, edits the
// first (gate mode, document order) and deactivates it. Requires the stack running with `python -m app.seed` applied. The scope carries a
// unique intake, so reruns never collide with each other or with a real template; the spec deactivates its template at the end.

test("the Overseas Admin creates, edits and deactivates a checklist template (ccrm-018)", async ({ page }) => {
  test.setTimeout(90_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const name = `E2E UK checklist ${unique}`;
  const intake = `E2E intake ${unique}`;

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/checklists");
  await expect(page.getByRole("heading", { name: "Document checklists", level: 2 })).toBeVisible();

  async function fillNew(templateName: string) {
    await page.getByRole("button", { name: "New template" }).click();
    const form = page.getByRole("form", { name: "New checklist template" });
    await form.getByLabel("Name").fill(templateName);
    await pickFromList(form.getByRole("combobox", { name: "Country" }), "GB", /^United Kingdom/);
    await form.getByLabel("Course level (optional)").selectOption("PG");
    await form.getByLabel("Intake (optional)").fill(intake);
    return form;
  }

  let form = await fillNew(name);
  await form.getByRole("button", { name: "Add document" }).click();
  await form.getByRole("listitem", { name: "Document 2" }).getByLabel("Document type").selectOption("SOP");
  await form.getByRole("button", { name: "Create template" }).click();
  await expect(page.locator("#checklists-notice")).toContainText(`Created ${name} (version 1).`);
  const card = page.locator(".card", { hasText: name });
  await expect(card).toContainText("United Kingdom · Any university · PG · " + intake);
  await expect(card).toContainText("Block until complete");

  form = await fillNew(`${name} copy`);
  await form.getByRole("button", { name: "Create template" }).click();
  await expect(form.getByRole("alert")).toContainText("An active template already covers this kind and scope");
  await form.getByRole("button", { name: "Cancel" }).click();

  await card.getByRole("button", { name: `Edit ${name}` }).click();
  form = page.getByRole("form", { name: `Edit ${name}` });
  await form.getByLabel("Warn (override with a reason)").check();
  await form.getByRole("button", { name: "Move document 2 up" }).click();
  await expect(form.getByRole("listitem", { name: "Document 1" }).getByLabel("Document type")).toHaveValue("SOP");
  await form.getByRole("button", { name: "Save changes" }).click();
  await expect(page.locator("#checklists-notice")).toContainText(`Saved ${name} (version 2).`);
  await expect(card).toContainText("Warn (override with a reason)");

  await card.getByRole("button", { name: `Edit ${name}` }).click();
  form = page.getByRole("form", { name: `Edit ${name}` });
  await form.getByRole("checkbox", { name: /^Active/ }).uncheck();
  await form.getByRole("button", { name: "Save changes" }).click();
  await expect(page.locator("#checklists-notice")).toContainText(`Saved ${name} (version 3).`);
  await expect(page.locator(".card", { hasText: name })).toHaveCount(0);
  await page.getByRole("button", { name: "Inactive", exact: true }).click();
  await expect(page.locator(".card", { hasText: name })).toContainText("Inactive");

  // The refused duplicate is an expected 409; the browser logs every failed request.
  expect(consoleErrors.filter((e) => !e.includes("409 (Conflict)"))).toEqual([]);
});
