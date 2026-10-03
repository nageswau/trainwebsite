"use client";

import { useRouter } from "next/navigation";
import { useContext, useEffect, useId, useState } from "react";

import type { FormMessageState } from "@/components/FormMessage";
import { NOT_COMPLETED, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";
import { TripLiveContext, isTrip } from "@/lib/tripLive";

export const jsonInit = (method: "POST" | "PATCH", body: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

const WRITE_STARTED = "bdm-trip-write";

// bdm-010 (§12.2 F4/F6): every trip write shares one contract. While it runs, `busy` disables the acting button.
// - Success says so. Inside a trip page (TripLiveContext) the response -- the full updated trip -- is applied directly (QA10-16);
//   elsewhere the server page is re-rendered. Statuses and `can_*` flags always come from the API, never a guess.
// - A 409 means the trip moved on under us: say why and re-read it, so the new state shows.
// - A server error or a dropped connection says the request did not complete (QA10-06); anything else keeps the user's input.
// - Focus moves to the result region (`resultProps`) after every outcome, so it never falls to <body> when the pressed button
//   disappears or is disabled (review I1, QA10-06).
// - Only the latest result on the page is shown: starting a write clears every other panel's message (QA10-09).
export function useTripWrite() {
  const router = useRouter();
  const live = useContext(TripLiveContext);
  const resultId = useId();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);

  useEffect(() => {
    const clear = (event: Event) => {
      if ((event as CustomEvent<string>).detail !== resultId) setMessage(null);
    };
    window.addEventListener(WRITE_STARTED, clear);
    return () => window.removeEventListener(WRITE_STARTED, clear);
  }, [resultId]);

  function announce(text: string) {
    setMessage({ text, failed: false });
    refocus(resultId);
  }

  async function run(url: string, init: RequestInit, success: string, after?: (data: Record<string, unknown>) => void): Promise<SendOutcome> {
    window.dispatchEvent(new CustomEvent(WRITE_STARTED, { detail: resultId }));
    setBusy(true);
    setMessage(null);
    const outcome = await sendRequest(url, init);
    setBusy(false);
    if (outcome.ok) {
      setMessage({ text: success, failed: false });
      if (after) after(outcome.data);
      else if (live && isTrip(outcome.data)) live.apply(outcome.data);
      else router.refresh();
    } else {
      const unreachable = outcome.status === undefined || outcome.status >= 500;
      setMessage({ text: unreachable ? NOT_COMPLETED : outcome.message, failed: true });
      if (outcome.status === 409) {
        if (live) await live.reload();
        else router.refresh();
      }
    }
    refocus(resultId);
    return outcome;
  }

  return { busy, message, setMessage, announce, run, resultProps: { id: resultId, tabIndex: -1 } };
}
