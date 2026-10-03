"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { FormMessageState } from "@/components/FormMessage";
import { sendRequest, type SendOutcome } from "@/lib/apiErrors";

export const jsonInit = (method: "POST" | "PATCH", body: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

// bdm-010 (§12.2 F4/F6): every trip write shares one contract. While it runs, `busy` disables the acting button. A success
// says so and reloads the server page, so statuses and `can_*` flags come from the API, not a guess (no optimistic update).
// A 409 means the trip moved on under us: say why and reload, so the new state shows. Anything else keeps the user's input.
export function useTripWrite() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);

  async function run(url: string, init: RequestInit, success: string, after?: (data: Record<string, unknown>) => void): Promise<SendOutcome> {
    setBusy(true);
    setMessage(null);
    const outcome = await sendRequest(url, init);
    setBusy(false);
    if (outcome.ok) {
      setMessage({ text: success, failed: false });
      if (after) after(outcome.data);
      else router.refresh();
    } else {
      setMessage({ text: outcome.message, failed: true });
      if (outcome.status === 409) router.refresh();
    }
    return outcome;
  }

  return { busy, message, setMessage, run };
}
