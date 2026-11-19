import { test } from "@playwright/test";

import { mailLink, noPrefetch, password } from "../shoot";

// IT Counselor CRM S7a (setup, no screenshots): Docs IT Lead Arjun sets his password from the welcome email in Mailpit and accepts the
// enrolment agreement, so his Docs FSP Batch 1 enrolment is active (timetable, batch notices). No payment is recorded (owner I3).
const ARJUN = "docs.itlead.arjun@example.test";

test("IT Counselor CRM S7a setup", async ({ browser }) => {
  test.setTimeout(300_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  await p.goto(await mailLink(ARJUN, 0, /https?:\/\/\S+(reset-password|set-password)\?token=[\w-]+/));
  await p.getByLabel("New password").fill(password("test"));
  await p.getByRole("button", { name: /Reset password|Set password/ }).click();
  await p.waitForURL(/\/(it\/)?login/, { timeout: 30_000 });
  await p.goto("/it/login");
  await p.getByLabel("Email").fill(ARJUN);
  await p.getByLabel("Password").fill(password("test"));
  await p.getByRole("button", { name: /Sign in/ }).click();
  await p.waitForURL(/\/it\/student\//, { timeout: 30_000 });
  await p.goto("/it/student/course");
  await p.waitForTimeout(2500);
  await p.getByRole("button", { name: "I have read and accept this agreement" }).click();
  await p.waitForTimeout(3000);
  console.log(`VERIFY S7a course: ${(await p.locator("main").innerText()).replace(/\s+/g, " ").slice(0, 900)}`);
});
