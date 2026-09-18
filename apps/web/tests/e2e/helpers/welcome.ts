import type { APIRequestContext, Page } from "@playwright/test";

// ENH-003 / DEC-SCOPE-019: admin-provisioned accounts have no default password. In development/test
// the create response carries `development_welcome_token`; specs set the password with it, exactly
// as a real user would from the emailed link.
export const E2E_PASSWORD = "E2e-Welcome-Pass-1!";

export async function activateWithToken(request: APIRequestContext, token: string, password: string = E2E_PASSWORD) {
  const response = await request.post("/api/v1/auth/reset-password", { data: { token, new_password: password } });
  if (!response.ok()) throw new Error(`welcome activation failed: ${response.status()} ${await response.text()}`);
}

export async function createAndActivate(request: APIRequestContext, path: string, data: Record<string, unknown>, password: string = E2E_PASSWORD) {
  const created = await request.post(path, { data });
  if (!created.ok()) throw new Error(`create failed: ${created.status()} ${await created.text()}`);
  const body = await created.json();
  await activateWithToken(request, body.development_welcome_token, password);
  return body;
}

// Click a create button in the admin UI and, when the create succeeds, activate the account it made.
// The form itself stays under test (nothing about the click changes); only the token the API
// returns in development/test is captured from the network response, since the UI never shows it.
// A failed create (e.g. a spec that expects a 409) is returned as-is and nothing is activated.
export async function createAndActivateFromUi(page: Page, buttonSelector: string, pathEndsWith: string, password: string = E2E_PASSWORD) {
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith(pathEndsWith)),
    page.click(buttonSelector),
  ]);
  const body = await response.json().catch(() => ({}));
  if (response.ok() && body.development_welcome_token) await activateWithToken(page.request, body.development_welcome_token, password);
  return body;
}
