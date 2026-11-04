// hrc-023 (DEC-SCOPE-389 W1): the visit's campaign (UTM) parameters. The first page of the visit that carries any of the five standard
// keys wins (first touch) and is kept for the browser tab, so a visitor who lands on /it/careers?utm_source=x and then registers keeps
// it. The server trims, caps and drops anything else; this file only collects.
export const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"] as const;
export type Utm = Partial<Record<(typeof UTM_KEYS)[number], string>>;
const STORAGE_KEY = "edusphere_utm";

export function utmFrom(search: string): Utm | null {
  const params = new URLSearchParams(search);
  const found: Utm = {};
  for (const key of UTM_KEYS) {
    const value = params.get(key)?.trim();
    if (value) found[key] = value;
  }
  return Object.keys(found).length ? found : null;
}

function stored(): Utm | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Utm) : null;
  } catch {
    return null; // storage blocked or a tampered value: no campaign rather than an error
  }
}

/** Keeps the current URL's UTM unless the visit already has one. */
export function captureUtm(search: string = window.location.search): void {
  const found = utmFrom(search);
  if (!found || stored()) return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(found));
  } catch {
    // storage blocked: the URL still carries it on this page
  }
}

/** The visit's UTM for a form submission: the stored first touch, else the current URL's. */
export function readUtm(search: string = window.location.search): Utm | null {
  return stored() ?? utmFrom(search);
}
