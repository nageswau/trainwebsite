"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { type LoadFailure, SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";

// ENH-018: why a feedback list could not be shown, shared by the school and admin lists. It takes focus when it appears so the
// failure is announced. An expired session (401) is not retryable, so it offers sign-in instead of "Try again" (QA-018-14).
export default function LoadFailureAlert({ failure, onRetry }: { failure: NonNullable<LoadFailure>; onRetry: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => ref.current?.focus(), [failure]);
  return (
    <div ref={ref} tabIndex={-1} className="form-error" role="alert">
      {failure === "expired" ? (
        <p style={{ margin: 0 }}>{SESSION_EXPIRED} <Link href={SIGN_IN_PATH}>Sign in again</Link></p>
      ) : (
        <>
          <p style={{ margin: 0 }}>Could not load activity feedback.</p>
          <button type="button" className="btn small secondary" style={{ marginTop: 8 }} onClick={onRetry}>Try again</button>
        </>
      )}
    </div>
  );
}
