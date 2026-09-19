// ENH-003 / DEC-SCOPE-019: shared wording and request helper for the first-time set-password link.
// Never mentions a password value -- admins no longer know or choose one.
type Tone = "success" | "warning" | "error";
export type Feedback = { text: string; tone: Tone };
type WelcomeDelivery = { email_status?: string };

// Reuses the existing message classes; `form-warning` (controls.css) is the amber sibling used when
// the account WAS created but the email was not delivered -- a partial success, not an error.
export const toneClass: Record<Tone, string> = { success: "form-message", warning: "form-warning", error: "form-error" };

export function welcomeLinkFeedback(subject: string, data: WelcomeDelivery): Feedback {
  if (data.email_status === "sent") {
    return { text: `${subject} A set-password link was emailed and is valid for 72 hours.`, tone: "success" };
  }
  const why = data.email_status === "not_configured" ? "email is not configured on this server" : "the email could not be sent";
  return {
    text: `${subject} The email was not delivered (${why}). Re-send the link from the Users page or dashboard once email works, or ask the user to use "Forgot your password?" on the sign-in page.`,
    tone: "warning",
  };
}

export function errorText(detail: unknown, fallback: string): string {
  return typeof detail === "string" ? detail : fallback;
}

export async function requestWelcomeLink(userId: string): Promise<{ ok: boolean; data: WelcomeDelivery & { detail?: unknown } }> {
  try {
    const response = await fetch(`/api/v1/admin/users/${userId}/welcome-links`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, data };
  } catch {
    // Re-send commits the new token before it answers, so a lost response is an unknown outcome, not "not sent".
    return { ok: false, data: { detail: "Network error -- it is not known whether the link was sent. Check the account's status before re-sending." } };
  }
}
