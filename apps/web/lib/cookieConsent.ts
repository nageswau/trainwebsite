// PUB-027 (DEC-SCOPE-443): the visitor's analytics-cookie choice (UK PECR reg. 6: consent before non-essential cookies).
// The choice lives in a first-party cookie so it survives reloads; the cookie itself is strictly necessary (it records the choice).

export type Consent = "granted" | "denied";

export const CONSENT_COOKIE = "edusphere_consent";
export const CONSENT_MAX_AGE = 180 * 24 * 60 * 60; // 6 months, then the visitor is asked again
export const CONSENT_EVENT = "edusphere:consent"; // dispatched when the choice changes
export const OPEN_SETTINGS_EVENT = "edusphere:cookie-settings"; // the footer's "Cookie settings" reopens the banner

export function readConsent(): Consent | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${CONSENT_COOKIE}=`));
  const value = match?.slice(CONSENT_COOKIE.length + 1);
  return value === "granted" || value === "denied" ? value : null;
}

export function writeConsent(consent: Consent): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${CONSENT_COOKIE}=${consent}; Max-Age=${CONSENT_MAX_AGE}; Path=/; SameSite=Lax${secure}`;
  if (consent === "denied") removeAnalyticsCookies();
  window.dispatchEvent(new CustomEvent<Consent>(CONSENT_EVENT, { detail: consent }));
}

export function openCookieSettings(): void {
  window.dispatchEvent(new Event(OPEN_SETTINGS_EVENT));
}

/** Google Analytics sets `_ga` and `_ga_<id>` on the site's registrable domain; expire them for every domain they may sit on. */
export function removeAnalyticsCookies(): void {
  const names = document.cookie.split("; ").map((part) => part.split("=")[0]).filter((name) => name === "_ga" || name.startsWith("_ga_"));
  const host = window.location.hostname;
  const labels = host.split(".");
  const domains = ["", ...labels.slice(0, -1).map((_, i) => `; Domain=.${labels.slice(i).join(".")}`)];
  for (const name of names) for (const domain of domains) document.cookie = `${name}=; Max-Age=0; Path=/${domain}`;
}
