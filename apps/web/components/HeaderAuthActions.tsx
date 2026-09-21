"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ROLE_DASHBOARD_PATH } from "@/lib/navigation";

type Session = { role: string; dashboardHref: string } | null | "loading";

// AUTH-002: the public site's header only ever showed a generic "Login" action,
// regardless of whether the visitor already had a session -- an authenticated actor's
// nav didn't reflect their actual state. This checks session state once client-side
// (the access token is HttpOnly, so this is the only way a client component can know)
// and swaps in the role-appropriate action. It never grants access itself -- every
// destination it links to is still independently authorized server-side (FND-002).
export default function HeaderAuthActions({ loginHref }: { loginHref: string }) {
  const router = useRouter();
  const [session, setSession] = useState<Session>("loading");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/auth/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((user) => {
        if (cancelled) return;
        setSession(user ? { role: user.role, dashboardHref: ROLE_DASHBOARD_PATH[user.role] || "/" } : null);
      })
      .catch(() => !cancelled && setSession(null));
    return () => {
      cancelled = true;
    };
  }, []);

  async function logout() {
    await fetch("/api/v1/auth/logout", { method: "POST" });
    setSession(null);
    router.push("/");
    router.refresh();
  }

  if (session === "loading") {
    // Reserve the same layout space as the signed-out state so nothing shifts once
    // the check resolves; renders no action a visitor could mistake for a real one.
    return <span className="btn" aria-hidden="true" style={{ visibility: "hidden" }}>Login</span>;
  }

  if (session === null) {
    return <Link className="btn" href={loginHref}>Login</Link>;
  }

  return (
    <>
      <Link className="btn secondary" href={session.dashboardHref}>Dashboard</Link>
      <Link className="btn secondary" href="/account/privacy">Privacy</Link>
      <button className="btn" onClick={logout}>Logout</button>
    </>
  );
}
