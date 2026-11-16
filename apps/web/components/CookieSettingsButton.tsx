"use client";

import { openCookieSettings } from "@/lib/cookieConsent";

// PUB-027: withdrawing consent must be as easy as giving it, so the footer offers the banner again on every public page.
export default function CookieSettingsButton() {
  return <button type="button" className="link-button" onClick={openCookieSettings}>Cookie settings</button>;
}
