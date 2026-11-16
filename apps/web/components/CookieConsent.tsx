"use client";

import Script from "next/script";
import { useEffect, useState } from "react";

import { gaInlineScript } from "@/components/Analytics";
import { type Consent, CONSENT_EVENT, OPEN_SETTINGS_EVENT, readConsent, writeConsent } from "@/lib/cookieConsent";

// PUB-027 (DEC-SCOPE-443): Google Analytics loads only after the visitor accepts. Accept and Reject carry equal weight, nothing is
// pre-selected, and the footer's "Cookie settings" reopens this banner. With no GA id configured the site sets no non-essential
// cookie, so there is nothing to ask and nothing renders.
export default function CookieConsent({ gaId }: { gaId?: string }) {
  const [consent, setConsent] = useState<Consent | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const stored = readConsent();
    setConsent(stored);
    setOpen(stored === null);
    const reopen = () => setOpen(true);
    const changed = (event: Event) => setConsent((event as CustomEvent<Consent>).detail);
    window.addEventListener(OPEN_SETTINGS_EVENT, reopen);
    window.addEventListener(CONSENT_EVENT, changed);
    return () => {
      window.removeEventListener(OPEN_SETTINGS_EVENT, reopen);
      window.removeEventListener(CONSENT_EVENT, changed);
    };
  }, []);

  useEffect(() => {
    // Google's documented opt-out flag: a gtag already loaded this visit stops sending as soon as consent is withdrawn.
    if (gaId) (window as unknown as Record<string, boolean>)[`ga-disable-${gaId}`] = consent !== "granted";
  }, [gaId, consent]);

  if (!gaId) return null;

  const choose = (choice: Consent) => {
    writeConsent(choice);
    setOpen(false);
  };

  return (
    <>
      {consent === "granted" && (
        <>
          <Script src={`https://www.googletagmanager.com/gtag/js?id=${gaId}`} strategy="afterInteractive" />
          <Script id="ga" strategy="afterInteractive">{gaInlineScript(gaId)}</Script>
        </>
      )}
      {open && (
        <section className="cookie-banner" role="region" aria-label="Cookie consent">
          <div className="container cookie-banner-row">
            <p>
              We use essential cookies to keep you signed in. With your permission we also use Google Analytics cookies to see which pages
              and adverts are useful. <a href="/privacy#cookies">Read our cookie policy</a>.
            </p>
            <div className="actions">
              <button type="button" className="btn" onClick={() => choose("granted")}>Accept analytics</button>
              <button type="button" className="btn" onClick={() => choose("denied")}>Reject analytics</button>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
