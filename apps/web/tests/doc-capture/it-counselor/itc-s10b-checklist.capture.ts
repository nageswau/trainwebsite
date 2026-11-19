import { readFileSync } from "node:fs";

import { test } from "@playwright/test";

import { ITC_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// IT Counselor CRM S10b: DOC-ITC-CONV-003 ticking an onboarding item (the student's IT counselor or the IT Admin ticks). Runs after itc-s10.
test("IT Counselor CRM S10b onboarding checklist", async ({ browser }) => {
  test.setTimeout(300_000);
  const leads = JSON.parse(readFileSync(process.env.DOCS_ITC_FILE!, "utf8")).leads as Record<string, string>;
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const c = await ctx.newPage();
  await signIn(c, "docs.itc.a@example.test", "test", /\/it\/counselor\/dashboard/, "/it/login");
  await c.goto(`/it/counselor/leads/${leads.arjun}`);
  await c.waitForTimeout(2500);
  const list = c.getByRole("heading", { name: "Onboarding checklist" }).first().locator("xpath=ancestor::section[1]");
  await list.getByLabel("Accept the enrolment agreement").check();
  await c.waitForTimeout(2000);
  const alerts = await c.locator('[role="alert"]').allInnerTexts();
  console.log(`VERIFY CONV-003 ticked: ${(await list.innerText()).replace(/\s+/g, " ")} alerts=${JSON.stringify(alerts)}`);
  await c.reload();
  await c.waitForTimeout(2500);
  const again = c.getByRole("heading", { name: "Onboarding checklist" }).first().locator("xpath=ancestor::section[1]");
  console.log(`VERIFY CONV-003 after reload: ${(await again.innerText()).replace(/\s+/g, " ")} checked=${await again.getByLabel("Accept the enrolment agreement").isChecked()}`);
  await shoot(c, "conversion", "14-onboarding-item-ticked.png", { root: ITC_ROOT, element: again });
});
