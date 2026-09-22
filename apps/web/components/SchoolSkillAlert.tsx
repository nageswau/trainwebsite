"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import type { SendFailure } from "@/lib/skills";

// ENH-011: the one alert every skills screen shows for a failed action. Focus moves to it so a keyboard or screen-reader user hears
// what went wrong (the ENH-005 pattern); an expired session offers sign-in, a failed read offers a retry.
export type SkillAlertState = { text: string; expired?: boolean; retry?: () => void };

export function alertFor(failure: SendFailure, retry?: () => void): SkillAlertState {
  return { text: failure.message, expired: failure.expired, retry };
}

export default function SchoolSkillAlert({ alert }: { alert: SkillAlertState | null }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (alert) ref.current?.focus();
  }, [alert]);
  if (!alert) return null;
  return (
    <div ref={ref} tabIndex={-1} className="form-error" role="alert">
      {alert.text}
      {alert.expired && <> <Link href="/overseas/login">Sign in again</Link></>}
      {alert.retry && <> <button type="button" className="btn small secondary" onClick={alert.retry}>Try again</button></>}
    </div>
  );
}
