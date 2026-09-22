"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { alertFor, type SkillAlertState } from "@/components/SchoolSkillAlert";
import { send } from "@/lib/skills";

// ENH-011: one write at a time for a batch-detail section. A second click while a write is in flight is ignored (state is a render
// late, so a ref guards it). On success the section announces what changed and the server data is re-read with router.refresh(),
// which keeps every section's own client state (open forms, unsaved marks elsewhere). On failure the entry is kept.
export function useSkillAction() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [alert, setAlert] = useState<SkillAlertState | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const running = useRef(false);

  async function run<T>(url: string, method: "POST" | "PATCH" | "PUT", body: unknown, success: (data: T) => string): Promise<T | null> {
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
      setAlert(alertFor(result));
      return null;
    }
    setMessage(success(result.data));
    router.refresh();
    return result.data;
  }

  return { busy, message, alert, fields, run };
}

/** The polite live region a section announces its last success in. */
export function SkillStatus({ message }: { message: string | null }) {
  return <div role="status" aria-live="polite">{message && <div className="form-message">{message}</div>}</div>;
}
