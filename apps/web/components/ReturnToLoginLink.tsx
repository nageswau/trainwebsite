"use client";

import { useEffect, useState } from "react";

import { safeNextPath } from "@/lib/safeNext";

// AGN-008 QA8-07 follow-up (owner, 2026-10-02): a session cookie the server no longer accepts (expired, revoked by a password
// change or a deactivation) passes the middleware, so the "Access unavailable" card is what the user sees. The card is rendered on
// the server, which does not know the page's address; the browser does, so the return address is added here -- through the same
// same-origin check the login page applies before following `next`. Until it runs (and on the home or login page) the link is the
// plain login page.
export default function ReturnToLoginLink({ loginHref }: { loginHref: string }) {
  const [href, setHref] = useState(loginHref);

  useEffect(() => {
    const here = safeNextPath(window.location.pathname + window.location.search);
    if (here && here !== "/" && !here.startsWith(loginHref)) setHref(`${loginHref}?next=${encodeURIComponent(here)}`);
  }, [loginHref]);

  return (
    <a className="btn" href={href}>
      Return to login
    </a>
  );
}
