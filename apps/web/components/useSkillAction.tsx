"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { alertFor, type SkillAlertState } from "@/components/SchoolSkillAlert";
import { send } from "@/lib/skills";

// ENH-011: one write at a time for a batch-detail section. A second click while a write is in flight is ignored (state is a render
// late, so a ref guards it). On success the section announces what changed and the server data is re-read with router.refresh(),
// which keeps every section's own client state (open forms, unsaved marks elsewhere). On failure the entry is kept.
// A success message clears itself after MESSAGE_MS, so the page does not collect stale ones (browser QA-08); the polite live region
// has announced it by then.
export const MESSAGE_MS = 8000;

export function useSkillAction() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [alert, setAlert] = useState<SkillAlertState | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const running = useRef(false);

  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => setMessage(null), MESSAGE_MS);
    return () => clearTimeout(timer);
  }, [message]);

  async function run<T>(url: string, method: "POST" | "PATCH" | "PUT", body: unknown, success: (data: T) => string, options: { fieldsShown?: boolean } = {}): Promise<T | null> {
    if (running.current) return null;
    running.current = true;
    setBusy(true);
    setAlert(null);
    setMessage(null);
    setFields({});
    const result = await send<T>(url, method, body);
    running.current = false;
    setBusy(false);
    if (!result.ok) {
      setFields(result.fields);
      setAlert(alertFor(result, undefined, options.fieldsShown));
      return null;
    }
    setMessage(success(result.data));
    router.refresh();
    return result.data;
  }

  /** Mark fields found wrong in the browser, exactly as a server 422 would be shown, without sending anything. */
  function invalid(found: Record<string, string>) {
    setMessage(null);
    setFields(found);
    setAlert(null);
  }

  return { busy, message, alert, fields, run, invalid };
}

/** The polite live region a section announces its last success in. */
export function SkillStatus({ message }: { message: string | null }) {
  return <div role="status" aria-live="polite">{message && <div className="form-message">{message}</div>}</div>;
}
