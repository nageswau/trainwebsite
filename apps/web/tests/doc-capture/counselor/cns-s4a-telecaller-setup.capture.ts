import { test } from "@playwright/test";

import { mailLink, noPrefetch, password } from "../shoot";

// Counselor CRM S4 set-up (not documented): the Docs Telecaller (created in S2) sets their password from the welcome email.
test("Counselor CRM S4a Docs Telecaller password", async ({ browser }) => {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  await p.goto(await mailLink("docs.telecaller@example.test"));
  await p.getByLabel("New password").fill(password("test"));
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForURL(/\/login/);
  console.log(`VERIFY telecaller password set; sign-in page ${new URL(p.url()).pathname}`);
});
